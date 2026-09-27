import os
import time
import signal
import subprocess
import tempfile
from pathlib import Path


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

YOUTUBE_COOKIES = os.environ.get("YOUTUBE_COOKIES", "")

QUALITY = "best"

RECONNECT_DELAY = 5
MAX_RECONNECT_DELAY = 60

AUDIO_BITRATE = "128k"
AUDIO_RATE = "44100"
AUDIO_CHANNELS = "2"

FFMPEG_INPUT_QUEUE = "256"

RW_TIMEOUT = "30000000"


# ============================================================
# GLOBALS
# ============================================================

ffmpeg_process = None
shutdown_requested = False
cookies_file = None


# ============================================================
# LOG
# ============================================================

def log(message=""):
    print(message, flush=True)


# ============================================================
# SIGNALS
# ============================================================

def handle_signal(signum, frame):

    global shutdown_requested

    shutdown_requested = True

    log("")
    log("============================================================")
    log("[SYSTEM] Shutdown requested...")
    log("============================================================")


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


# ============================================================
# COOKIES
# ============================================================

def prepare_cookies():

    global cookies_file

    if not YOUTUBE_COOKIES.strip():

        log("[SYSTEM] YouTube Cookies: OFF")
        return None

    try:

        fd, path = tempfile.mkstemp(
            prefix="youtube_",
            suffix=".txt"
        )

        os.close(fd)

        Path(path).write_text(
            YOUTUBE_COOKIES,
            encoding="utf-8"
        )

        cookies_file = path

        log("[SYSTEM] YouTube Cookies: ON")

        return path

    except Exception as e:

        log(
            "[ERROR] Could not create YouTube cookies file: "
            f"{type(e).__name__}: {e}"
        )

        return None


# ============================================================
# CLEAN COOKIES
# ============================================================

def cleanup_cookies():

    global cookies_file

    if cookies_file:

        try:
            Path(cookies_file).unlink(
                missing_ok=True
            )
        except Exception:
            pass

        cookies_file = None


# ============================================================
# COOKIE HEADER
# ============================================================

def build_cookie_header():

    if not cookies_file:
        return ""

    try:

        cookie_pairs = []

        with open(
            cookies_file,
            "r",
            encoding="utf-8",
            errors="ignore"
        ) as f:

            for line in f:

                line = line.strip()

                if not line:
                    continue

                if line.startswith("#"):
                    continue

                parts = line.split("\t")

                if len(parts) < 7:
                    continue

                name = parts[5]
                value = parts[6]

                if name and value:

                    cookie_pairs.append(
                        f"{name}={value}"
                    )

        return "; ".join(cookie_pairs)

    except Exception:

        return ""


# ============================================================
# GET FRESH YOUTUBE HLS URL
# ============================================================

def get_fresh_hls_url():

    command = [
        "yt-dlp",

        "--no-warnings",
        "--quiet",
        "--no-progress",
        "--no-playlist",

        "--format",
        "best",

        "--get-url",

        "--retries",
        "3",

        "--fragment-retries",
        "3",

        "--socket-timeout",
        "20",

        "--extractor-retries",
        "3",

        YOUTUBE_URL
    ]

    if cookies_file:

        command.insert(
            -1,
            "--cookies"
        )

        command.insert(
            -1,
            cookies_file
        )

    try:

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=45
        )

    except subprocess.TimeoutExpired:

        log("[ERROR] yt-dlp timeout.")
        return None

    except FileNotFoundError:

        log(
            "[ERROR] yt-dlp was not found."
        )

        return None

    except Exception as e:

        log(
            f"[ERROR] yt-dlp failed to execute: "
            f"{type(e).__name__}: {e}"
        )

        return None


    if result.returncode != 0:

        error_text = result.stderr.strip()

        log("[ERROR] yt-dlp failed:")

        if error_text:
            log(error_text[-3000:])

        return None


    output = result.stdout.strip()

    if not output:

        log(
            "[ERROR] yt-dlp returned no stream URL."
        )

        return None


    lines = [
        x.strip()
        for x in output.splitlines()
        if x.strip()
    ]

    if not lines:
        return None


    url = lines[-1]


    if not (
        url.startswith("http://")
        or url.startswith("https://")
    ):

        log(
            "[ERROR] Invalid YouTube HLS URL."
        )

        return None


    return url


# ============================================================
# FFMPEG COMMAND
# ============================================================

def build_ffmpeg_command(hls_url):

    command = [

        "ffmpeg",

        "-hide_banner",

        "-loglevel",
        "warning",

        "-stats",

        # ----------------------------------------------------
        # NETWORK / INPUT
        # ----------------------------------------------------

        "-thread_queue_size",
        FFMPEG_INPUT_QUEUE,

        "-rw_timeout",
        RW_TIMEOUT,

        "-reconnect",
        "1",

        "-reconnect_streamed",
        "1",

        "-reconnect_at_eof",
        "1",

        "-reconnect_delay_max",
        "10",

        "-i",
        hls_url,

        # ----------------------------------------------------
        # VIDEO COPY
        # ----------------------------------------------------

        "-map",
        "0:v:0?",

        "-c:v",
        "copy",

        # ----------------------------------------------------
        # AUDIO
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

        # ----------------------------------------------------
        # TIMESTAMPS
        # ----------------------------------------------------

        "-fflags",
        "+genpts+discardcorrupt",

        "-avoid_negative_ts",
        "make_zero",

        # ----------------------------------------------------
        # FLV
        # ----------------------------------------------------

        "-flvflags",
        "no_duration_filesize",

        "-flush_packets",
        "1",

        "-f",
        "flv",

        RESTREAM_RTMP
    ]


    if cookies_file:

        cookie_header = build_cookie_header()

        if cookie_header:

            index = command.index("-i")

            command.insert(
                index,
                "-headers"
            )

            command.insert(
                index + 1,
                f"Cookie: {cookie_header}\r\n"
            )


    return command


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

                ffmpeg_process.wait(
                    timeout=5
                )

            except subprocess.TimeoutExpired:

                log("[SYSTEM] Killing FFmpeg...")

                try:
                    ffmpeg_process.kill()
                except Exception:
                    pass

                try:
                    ffmpeg_process.wait(
                        timeout=3
                    )
                except Exception:
                    pass

    except Exception as e:

        log(
            f"[SYSTEM] FFmpeg stop error: {e}"
        )

    ffmpeg_process = None


# ============================================================
# START FFMPEG
# ============================================================

def start_ffmpeg(hls_url):

    global ffmpeg_process

    stop_ffmpeg()

    command = build_ffmpeg_command(
        hls_url
    )

    log("")
    log("============================================================")
    log("[SYSTEM] Starting FFmpeg")
    log("============================================================")
    log("[SYSTEM] Video: COPY")
    log("[SYSTEM] Video Encode: OFF")
    log(f"[SYSTEM] Audio: AAC {AUDIO_BITRATE}")
    log("[SYSTEM] Crop: OFF")
    log("[SYSTEM] Resize: OFF")
    log("[SYSTEM] FPS Convert: OFF")
    log("[SYSTEM] Sending YouTube -> Restream...")


    try:

        ffmpeg_process = subprocess.Popen(
            command,

            stdin=subprocess.DEVNULL,

            stdout=subprocess.DEVNULL,

            stderr=None,

            bufsize=0
        )

    except FileNotFoundError:

        log(
            "[ERROR] FFmpeg was not found."
        )

        ffmpeg_process = None

        return False

    except Exception as e:

        log(
            f"[ERROR] Could not start FFmpeg: "
            f"{type(e).__name__}: {e}"
        )

        ffmpeg_process = None

        return False


    time.sleep(3)


    if ffmpeg_process.poll() is not None:

        code = ffmpeg_process.returncode

        log(
            f"[ERROR] FFmpeg exited immediately "
            f"(exit code: {code})."
        )

        ffmpeg_process = None

        return False


    log("[SYSTEM] YouTube -> FFmpeg: CONNECTED")
    log("[SYSTEM] FFmpeg -> Restream: CONNECTED")
    log("[SYSTEM] FFmpeg process is alive.")
    log("[SYSTEM] Stream is RUNNING.")

    return True


# ============================================================
# MONITOR
# ============================================================

def monitor_ffmpeg():

    global ffmpeg_process

    last_heartbeat = time.time()

    while not shutdown_requested:

        time.sleep(2)

        if ffmpeg_process is None:

            return False

        code = ffmpeg_process.poll()

        if code is not None:

            log("")
            log(
                "[SYSTEM] FFmpeg stopped "
                f"(exit code: {code})."
            )

            return False


        if (
            time.time() - last_heartbeat
            >= 60
        ):

            log(
                "[SYSTEM] Relay is still RUNNING."
            )

            last_heartbeat = time.time()


    return False


# ============================================================
# RUN SESSION
# ============================================================

def run_session():

    log("")
    log("============================================================")
    log("[SYSTEM] Resolving fresh YouTube HLS URL...")
    log("============================================================")


    hls_url = get_fresh_hls_url()


    if not hls_url:

        log(
            "[SYSTEM] No YouTube stream URL."
        )

        return False


    log(
        "[SYSTEM] Fresh YouTube HLS URL obtained."
    )


    if not start_ffmpeg(hls_url):

        return False


    return monitor_ffmpeg()


# ============================================================
# MAIN
# ============================================================

def main():

    global shutdown_requested

    log("============================================================")
    log("       YouTube 24/7 -> Restream -> TikTok")
    log("============================================================")

    log(
        f"YouTube        : {YOUTUBE_URL}"
    )

    log(
        "Destination    : Restream"
    )

    log(
        "Extractor      : yt-dlp"
    )

    log(
        "Cookies        : "
        + ("ON" if YOUTUBE_COOKIES else "OFF")
    )

    log("Quality        : BEST")
    log("Video          : COPY")
    log("Video Encode   : OFF")
    log("Crop           : OFF")
    log("Resize         : OFF")
    log("FPS Convert    : OFF")
    log("Audio          : AAC 128k")
    log("Memory Mode    : LOW")
    log("Auto-Reconnect : ON")
    log("Status         : STARTING")

    log("============================================================")
    log("[SYSTEM] Starting 24/7 relay...")
    log("============================================================")


    reconnect_delay = RECONNECT_DELAY


    while not shutdown_requested:

        try:

            success = run_session()

        except Exception as e:

            success = False

            log("")
            log("============================================================")
            log("[ERROR] Session exception")
            log(
                f"[ERROR] {type(e).__name__}: {e}"
            )
            log("============================================================")


        if shutdown_requested:
            break


        stop_ffmpeg()


        log("")
        log("============================================================")
        log("[SYSTEM] Stream ended or connection lost.")
        log(
            f"[SYSTEM] Reconnecting in "
            f"{reconnect_delay} seconds..."
        )
        log("============================================================")


        time.sleep(
            reconnect_delay
        )


        if success:

            reconnect_delay = RECONNECT_DELAY

        else:

            reconnect_delay = min(
                reconnect_delay * 2,
                MAX_RECONNECT_DELAY
            )


    stop_ffmpeg()

    log("[SYSTEM] Relay stopped.")


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    try:

        prepare_cookies()

        main()

    except KeyboardInterrupt:

        shutdown_requested = True

    except Exception as e:

        log(
            f"[SYSTEM] Fatal error: "
            f"{type(e).__name__}: {e}"
        )

    finally:

        stop_ffmpeg()

        cleanup_cookies()

        log("[SYSTEM] Cleanup complete.")
