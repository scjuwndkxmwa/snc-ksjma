import os
import sys
import time
import signal
import subprocess
import gc


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

COOKIES_FILE = os.environ.get(
    "YOUTUBE_COOKIES_FILE",
    "/app/cookies.txt"
)

RECONNECT_DELAY = 5
MAX_RECONNECT_DELAY = 30

YT_DLP_TIMEOUT = 90

FFMPEG_START_WAIT = 5

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

session_number = 0


# ============================================================
# LOG
# ============================================================

def log(text=""):
    print(text, flush=True)


# ============================================================
# SIGNALS
# ============================================================

def handle_signal(signum, frame):

    global shutdown_requested

    shutdown_requested = True

    log("")
    log("[SYSTEM] Shutdown requested...")


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


# ============================================================
# CLEAN MEMORY
# ============================================================

def clean_memory():

    gc.collect()


# ============================================================
# STOP PROCESS
# ============================================================

def stop_process(process, name):

    if process is None:
        return

    try:

        if process.poll() is None:

            log(f"[SYSTEM] Stopping {name}...")

            try:
                process.terminate()
            except Exception:
                pass

            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:

                log(f"[SYSTEM] Killing {name}...")

                try:
                    process.kill()
                except Exception:
                    pass

                try:
                    process.wait(timeout=3)
                except Exception:
                    pass

    except Exception as e:

        log(
            f"[SYSTEM] Error stopping {name}: "
            f"{type(e).__name__}: {e}"
        )


# ============================================================
# STOP ALL
# ============================================================

def stop_all():

    global ffmpeg_process

    if ffmpeg_process is not None:

        stop_process(
            ffmpeg_process,
            "FFmpeg"
        )

    ffmpeg_process = None

    clean_memory()


# ============================================================
# YT-DLP COMMAND
# ============================================================

def build_ytdlp_command():

    command = [

        "yt-dlp",

        "--no-warnings",

        "--no-playlist",

        "--skip-download",

        "--get-url",

        "--format",
        QUALITY,

        "--retries",
        "10",

        "--fragment-retries",
        "10",

        "--retry-sleep",
        "exp=2:10",

        "--socket-timeout",
        "30",

        "--force-ipv4",

    ]

    # --------------------------------------------------------
    # COOKIES
    # --------------------------------------------------------

    if os.path.isfile(COOKIES_FILE):

        command.extend([
            "--cookies",
            COOKIES_FILE
        ])

        log("[SYSTEM] YouTube Cookies: ON")

    else:

        log("[SYSTEM] YouTube Cookies: OFF")

    command.append(YOUTUBE_URL)

    return command


# ============================================================
# GET FRESH HLS URL
# ============================================================

def get_fresh_url():

    log("")
    log("[SYSTEM] Resolving fresh YouTube stream URL...")

    command = build_ytdlp_command()

    try:

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=YT_DLP_TIMEOUT
        )

    except subprocess.TimeoutExpired:

        log("[ERROR] yt-dlp timed out.")

        return None

    except Exception as e:

        log(
            f"[ERROR] yt-dlp execution error: "
            f"{type(e).__name__}: {e}"
        )

        return None

    if result.returncode != 0:

        error_text = result.stderr.strip()

        log("[ERROR] yt-dlp failed:")

        if error_text:
            log(error_text[-4000:])

        return None

    urls = []

    for line in result.stdout.splitlines():

        line = line.strip()

        if not line:
            continue

        if line.startswith("http://") or line.startswith("https://"):

            urls.append(line)

    if not urls:

        log("[ERROR] yt-dlp returned no stream URL.")

        return None

    # Prefer HLS.
    for url in urls:

        if ".m3u8" in url.lower():

            log("[SYSTEM] Fresh HLS URL obtained.")

            return url

    # Fallback.
    log("[SYSTEM] Fresh YouTube URL obtained.")

    return urls[-1]


# ============================================================
# FFMPEG COMMAND
# ============================================================

def build_ffmpeg_command(source_url):

    return [

        "ffmpeg",

        "-hide_banner",

        "-loglevel",
        "warning",

        "-stats",

        # ====================================================
        # NETWORK RECONNECT
        # ====================================================

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
        "10",

        # ====================================================
        # INPUT
        # ====================================================

        "-i",
        source_url,

        # ====================================================
        # VIDEO COPY
        # ====================================================

        "-map",
        "0:v:0",

        "-c:v",
        "copy",

        # ====================================================
        # AUDIO
        # ====================================================

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
        "aresample=async=1000:min_hard_comp=0.100:first_pts=0",

        # ====================================================
        # TIMESTAMPS
        # ====================================================

        "-fflags",
        "+genpts+discardcorrupt",

        "-err_detect",
        "ignore_err",

        # ====================================================
        # RTMP OUTPUT
        # ====================================================

        "-flvflags",
        "no_duration_filesize",

        "-f",
        "flv",

        RESTREAM_RTMP
    ]


# ============================================================
# START FFMPEG
# ============================================================

def start_ffmpeg(source_url):

    global ffmpeg_process

    stop_all()

    clean_memory()

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

    command = build_ffmpeg_command(source_url)

    try:

        ffmpeg_process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=None,
            bufsize=0
        )

    except Exception as e:

        log(
            f"[ERROR] Could not start FFmpeg: "
            f"{type(e).__name__}: {e}"
        )

        ffmpeg_process = None

        return False

    time.sleep(FFMPEG_START_WAIT)

    if ffmpeg_process.poll() is not None:

        code = ffmpeg_process.returncode

        log(
            f"[ERROR] FFmpeg stopped immediately "
            f"(exit code: {code})."
        )

        stop_all()

        return False

    log("[SYSTEM] YouTube -> FFmpeg: CONNECTED")
    log("[SYSTEM] FFmpeg -> Restream: CONNECTED")
    log("[SYSTEM] FFmpeg process is alive.")
    log("[SYSTEM] Stream is RUNNING.")

    return True


# ============================================================
# MONITOR
# ============================================================

def monitor():

    global ffmpeg_process

    last_heartbeat = time.time()

    while not shutdown_requested:

        time.sleep(5)

        if ffmpeg_process is None:

            return False

        code = ffmpeg_process.poll()

        if code is not None:

            log("")
            log(
                f"[SYSTEM] FFmpeg stopped "
                f"(exit code: {code})."
            )

            return False

        if time.time() - last_heartbeat >= 60:

            log("[SYSTEM] Relay is still RUNNING.")

            last_heartbeat = time.time()

    return False


# ============================================================
# SAFE SLEEP
# ============================================================

def safe_sleep(seconds):

    end = time.time() + seconds

    while (
        time.time() < end
        and not shutdown_requested
    ):

        time.sleep(1)


# ============================================================
# SESSION
# ============================================================

def run_session():

    global session_number

    session_number += 1

    log("")
    log("============================================================")
    log(
        f"[SYSTEM] Starting relay session #{session_number}"
    )
    log("============================================================")

    source_url = get_fresh_url()

    if not source_url:

        log("[SYSTEM] No YouTube stream URL.")

        return False

    if not start_ffmpeg(source_url):

        return False

    monitor()

    stop_all()

    clean_memory()

    return False


# ============================================================
# MAIN
# ============================================================

def main():

    global shutdown_requested

    log("============================================================")
    log("       YouTube 24/7 -> Restream -> TikTok")
    log("============================================================")

    log(f"YouTube        : {YOUTUBE_URL}")
    log("Destination    : Restream")
    log("Extractor      : yt-dlp")
    log("Video          : COPY")
    log("Video Encode   : OFF")
    log("Audio          : AAC 128k")
    log("HLS Reconnect  : ON")
    log("Auto-Reconnect : ON")
    log("Memory Mode    : LOW")
    log("============================================================")

    delay = RECONNECT_DELAY

    while not shutdown_requested:

        try:

            run_session()

        except Exception as e:

            log("")
            log("[ERROR] Session exception:")
            log(
                f"{type(e).__name__}: {e}"
            )

        if shutdown_requested:
            break

        stop_all()

        log("")
        log("============================================================")
        log(
            f"[SYSTEM] Reconnecting in {delay} seconds..."
        )
        log("============================================================")

        safe_sleep(delay)

        delay = min(
            delay + 2,
            MAX_RECONNECT_DELAY
        )

    stop_all()

    log("[SYSTEM] Relay stopped.")


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        shutdown_requested = True

        stop_all()

    except Exception as e:

        log(
            f"[FATAL] {type(e).__name__}: {e}"
        )

        stop_all()

    finally:

        stop_all()
        clean_memory()
