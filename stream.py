import os
import time
import signal
import subprocess
import threading


# ============================================================
# CONFIG
# ============================================================

YOUTUBE_URL = "https://www.youtube.com/live/7DHNbnPMNiM"

RESTREAM_STREAM_KEY = (
    "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9"
)

RESTREAM_RTMP = (
    f"rtmp://live.restream.io/live/{RESTREAM_STREAM_KEY}"
)

QUALITY = "best"

RECONNECT_DELAY = 5
MAX_RECONNECT_DELAY = 30

SOURCE_RESOLVE_TIMEOUT = 120
FFMPEG_START_GRACE = 15
STALL_TIMEOUT = 90


# ============================================================
# YT-DLP
# ============================================================

FORMAT_SELECTOR = (
    "best"
    "[protocol^=m3u8]"
    "[vcodec!=none]"
    "[acodec!=none]"
    "/"
    "best"
    "[vcodec!=none]"
    "[acodec!=none]"
)

YTDLP_PLAYER_CLIENTS = "web_safari,web,tv_simply,tv"


# ============================================================
# AUDIO
# ============================================================

AUDIO_BITRATE = "128k"
AUDIO_RATE = "44100"
AUDIO_CHANNELS = "2"


# ============================================================
# GLOBALS
# ============================================================

ffmpeg_process = None
shutdown_requested = False

last_progress_time = 0.0
last_progress_value = -1

progress_lock = threading.Lock()


# ============================================================
# LOG
# ============================================================

def log(message=""):
    print(message, flush=True)


# ============================================================
# SIGNAL
# ============================================================

def handle_signal(signum, frame):

    global shutdown_requested

    shutdown_requested = True

    log("")
    log("[SYSTEM] Shutdown signal received.")


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


# ============================================================
# SAFE SLEEP
# ============================================================

def safe_sleep(seconds):

    end = time.monotonic() + seconds

    while (
        time.monotonic() < end
        and not shutdown_requested
    ):
        time.sleep(1)


# ============================================================
# STOP FFMPEG
# ============================================================

def stop_ffmpeg():

    global ffmpeg_process

    if ffmpeg_process is None:
        return

    try:

        if ffmpeg_process.poll() is None:

            log("[SYSTEM] Stopping FFmpeg...")

            try:
                ffmpeg_process.terminate()
            except Exception:
                pass

            try:
                ffmpeg_process.wait(timeout=5)

            except subprocess.TimeoutExpired:

                log("[SYSTEM] Killing FFmpeg...")

                try:
                    ffmpeg_process.kill()
                except Exception:
                    pass

                try:
                    ffmpeg_process.wait(timeout=5)
                except Exception:
                    pass

    except Exception as e:

        log(
            f"[SYSTEM] FFmpeg stop error: "
            f"{type(e).__name__}: {e}"
        )

    finally:

        ffmpeg_process = None


# ============================================================
# GET FRESH YOUTUBE URL
# ============================================================

def resolve_youtube_url():

    log("[SYSTEM] Resolving fresh YouTube stream URL...")
    log("[SYSTEM] Extractor: yt-dlp")
    log("[SYSTEM] Cookies: OFF")

    command = [

        "yt-dlp",

        "--ignore-config",
        "--no-playlist",
        "--no-warnings",
        "--no-update",

        "--get-url",

        "--format",
        FORMAT_SELECTOR,

        "--extractor-args",
        f"youtube:player_client={YTDLP_PLAYER_CLIENTS}",

        "--js-runtimes",
        "deno",

        "--retries",
        "10",

        "--fragment-retries",
        "infinite",

        "--retry-sleep",
        "fragment:exp=1:10",

        "--socket-timeout",
        "30",

        YOUTUBE_URL
    ]

    try:

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=SOURCE_RESOLVE_TIMEOUT,
            check=False
        )

    except subprocess.TimeoutExpired:

        log("[ERROR] yt-dlp URL resolution timed out.")

        return None

    except Exception as e:

        log(
            f"[ERROR] yt-dlp failed to start: "
            f"{type(e).__name__}: {e}"
        )

        return None

    stderr_text = (
        result.stderr.strip()
        if result.stderr
        else ""
    )

    if stderr_text:

        for line in stderr_text.splitlines():

            line = line.strip()

            if (
                "ERROR" in line
                or "WARNING" in line
                or "LOGIN" in line
                or "403" in line
                or "bot" in line.lower()
            ):

                log(f"[YTDLP] {line}")

    if result.returncode != 0:

        log(
            f"[ERROR] yt-dlp returned exit code "
            f"{result.returncode}"
        )

        return None

    urls = []

    for line in result.stdout.splitlines():

        line = line.strip()

        if (
            line.startswith("http://")
            or line.startswith("https://")
        ):

            urls.append(line)

    if not urls:

        log(
            "[ERROR] yt-dlp did not return "
            "a playback URL."
        )

        return None

    m3u8_urls = [
        url for url in urls
        if ".m3u8" in url
    ]

    if m3u8_urls:

        playback_url = m3u8_urls[0]

    else:

        playback_url = urls[0]

    log("[SYSTEM] Fresh YouTube playback URL obtained.")

    return playback_url


# ============================================================
# FFMPEG PROGRESS
# ============================================================

def read_ffmpeg_progress(process):

    global last_progress_time
    global last_progress_value

    try:

        while not shutdown_requested:

            line = process.stderr.readline()

            if not line:
                break

            line = line.decode(
                "utf-8",
                errors="replace"
            ).strip()

            if not line:
                continue

            if line.startswith("out_time_ms="):

                try:

                    value = int(
                        line.split("=", 1)[1]
                    )

                    with progress_lock:

                        if value > last_progress_value:

                            last_progress_value = value
                            last_progress_time = (
                                time.monotonic()
                            )

                except Exception:
                    pass

                continue

            if (
                "Error" in line
                or "error" in line
                or "Failed" in line
                or "failed" in line
                or "403" in line
                or "Connection" in line
                or "Broken pipe" in line
            ):

                log(f"[FFMPEG] {line}")

    except Exception:
        pass


# ============================================================
# FFMPEG COMMAND
# ============================================================

def build_ffmpeg_command(playback_url):

    return [

        "ffmpeg",

        "-hide_banner",
        "-loglevel",
        "warning",
        "-nostats",

        "-stats_period",
        "30",

        "-progress",
        "pipe:2",

        # ----------------------------------------------------
        # RECONNECT
        # ----------------------------------------------------

        "-reconnect",
        "1",

        "-reconnect_at_eof",
        "1",

        "-reconnect_streamed",
        "1",

        "-reconnect_on_network_error",
        "1",

        "-reconnect_on_http_error",
        "4xx,5xx",

        "-reconnect_delay_max",
        "5",

        "-reconnect_max_retries",
        "20",

        "-rw_timeout",
        "30000000",

        # ----------------------------------------------------
        # INPUT
        # ----------------------------------------------------

        "-thread_queue_size",
        "2048",

        "-i",
        playback_url,

        # ----------------------------------------------------
        # VIDEO COPY
        # ----------------------------------------------------

        "-map",
        "0:v:0",

        "-c:v",
        "copy",

        "-fps_mode",
        "passthrough",

        # ----------------------------------------------------
        # AUDIO AAC
        # ----------------------------------------------------

        "-map",
        "0:a:0?",

        "-c:a",
        "aac",

        "-b:a",
        AUDIO_BITRATE,

        "-ar",
        AUDIO_RATE,

        "-ac",
        AUDIO_CHANNELS,

        "-af",
        (
            "aresample="
            "async=1000:"
            "min_hard_comp=0.100:"
            "first_pts=0"
        ),

        # ----------------------------------------------------
        # TIMESTAMPS
        # ----------------------------------------------------

        "-fflags",
        "+genpts+discardcorrupt",

        "-err_detect",
        "ignore_err",

        "-avoid_negative_ts",
        "make_zero",

        # ----------------------------------------------------
        # OUTPUT
        # ----------------------------------------------------

        "-flvflags",
        "no_duration_filesize",

        "-f",
        "flv",

        RESTREAM_RTMP
    ]


# ============================================================
# START FFMPEG
# ============================================================

def start_ffmpeg(playback_url):

    global ffmpeg_process
    global last_progress_time
    global last_progress_value

    command = build_ffmpeg_command(playback_url)

    log("[SYSTEM] Starting FFmpeg...")
    log("[SYSTEM] Video: COPY")
    log("[SYSTEM] Video Encode: OFF")
    log("[SYSTEM] Audio: AAC 128k")
    log("[SYSTEM] Sending YouTube -> Restream...")

    try:

        ffmpeg_process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            bufsize=0
        )

    except Exception as e:

        log(
            f"[ERROR] Could not start FFmpeg: "
            f"{type(e).__name__}: {e}"
        )

        ffmpeg_process = None

        return False

    with progress_lock:

        last_progress_time = time.monotonic()
        last_progress_value = -1

    reader = threading.Thread(
        target=read_ffmpeg_progress,
        args=(ffmpeg_process,),
        daemon=True
    )

    reader.start()

    time.sleep(3)

    if ffmpeg_process.poll() is not None:

        code = ffmpeg_process.returncode

        log(
            f"[ERROR] FFmpeg exited immediately "
            f"(exit code: {code})."
        )

        stop_ffmpeg()

        return False

    log("[SYSTEM] FFmpeg process is alive.")

    return True


# ============================================================
# MONITOR
# ============================================================

def monitor_ffmpeg():

    global ffmpeg_process

    start_time = time.monotonic()
    last_report = time.monotonic()

    while not shutdown_requested:

        time.sleep(2)

        if ffmpeg_process is None:
            return False

        return_code = ffmpeg_process.poll()

        if return_code is not None:

            log("")
            log(
                f"[SYSTEM] FFmpeg stopped "
                f"(exit code: {return_code})."
            )

            return False

        with progress_lock:

            progress_age = (
                time.monotonic()
                - last_progress_time
            )

        if (
            time.monotonic() - start_time
            > FFMPEG_START_GRACE
        ):

            if progress_age > STALL_TIMEOUT:

                log("")
                log("[SYSTEM] FFmpeg appears stalled.")

                log(
                    f"[SYSTEM] No output progress for "
                    f"{int(progress_age)} seconds."
                )

                return False

        if time.monotonic() - last_report >= 60:

            log("[SYSTEM] Relay is still RUNNING.")

            last_report = time.monotonic()

    return False


# ============================================================
# RUN SESSION
# ============================================================

def run_session():

    playback_url = resolve_youtube_url()

    if not playback_url:

        return False

    if not start_ffmpeg(playback_url):

        return False

    log("[SYSTEM] YouTube -> FFmpeg: CONNECTED")
    log("[SYSTEM] FFmpeg -> Restream: CONNECTED")
    log("[SYSTEM] Stream is RUNNING.")

    monitor_ffmpeg()

    return False


# ============================================================
# MAIN
# ============================================================

def main():

    global shutdown_requested

    log("")
    log("=" * 60)
    log("       YouTube 24/7 -> Restream -> TikTok")
    log("=" * 60)

    log(f"YouTube        : {YOUTUBE_URL}")
    log("Extractor      : yt-dlp")
    log("Destination    : Restream")
    log("Cookies        : OFF")
    log("Quality        : BEST")
    log("Video          : COPY")
    log("Video Encode   : OFF")
    log("Crop           : OFF")
    log("Resize         : OFF")
    log("FPS Convert    : OFF")
    log("Audio          : AAC 128k")
    log("Auto-Reconnect : ON")
    log("Fresh HLS URL  : ON")
    log("Stall Recovery : ON")
    log("Status         : STARTING")

    log("=" * 60)

    failures = 0

    while not shutdown_requested:

        stop_ffmpeg()

        try:

            log("")
            log("=" * 60)
            log("[SYSTEM] Starting relay session")
            log("=" * 60)

            run_session()

            if shutdown_requested:
                break

            failures += 1

        except Exception as e:

            failures += 1

            log(
                f"[ERROR] Session exception: "
                f"{type(e).__name__}: {e}"
            )

        finally:

            stop_ffmpeg()

        if shutdown_requested:
            break

        delay = min(
            RECONNECT_DELAY * max(1, failures),
            MAX_RECONNECT_DELAY
        )

        log("")
        log("=" * 60)
        log("[SYSTEM] Stream ended or connection lost.")
        log(
            f"[SYSTEM] Reconnecting in {delay} seconds..."
        )
        log("[SYSTEM] A fresh YouTube URL will be requested.")
        log("=" * 60)

        safe_sleep(delay)

        # Reset backoff after a longer successful run
        if failures >= 3:
            failures = 3

    stop_ffmpeg()

    log("[SYSTEM] Relay stopped.")


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        shutdown_requested = True
        stop_ffmpeg()

    finally:

        stop_ffmpeg()
