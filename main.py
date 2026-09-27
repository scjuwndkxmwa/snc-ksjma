import os
import sys
import time
import signal
import subprocess
import tempfile
import base64
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

# ------------------------------------------------------------
# YouTube cookies
#
# Recommended Railway variable:
#
# YOUTUBE_COOKIES
#
# Put the complete Netscape cookies.txt content in it.
#
# Optional:
# YOUTUBE_COOKIES_B64
#
# ------------------------------------------------------------

YOUTUBE_COOKIES = os.environ.get("YOUTUBE_COOKIES", "").strip()
YOUTUBE_COOKIES_B64 = os.environ.get(
    "YOUTUBE_COOKIES_B64", ""
).strip()


# ============================================================
# RELAY SETTINGS
# ============================================================

RECONNECT_DELAY = 8
MAX_RECONNECT_DELAY = 60

AUDIO_BITRATE = "128k"
AUDIO_RATE = "44100"
AUDIO_CHANNELS = "2"


# Keep memory low.
# Do NOT create huge Python/FFmpeg buffers.
THREAD_QUEUE_SIZE = "512"


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
# FIND EXECUTABLE
# ============================================================

def executable(name):
    return name


# ============================================================
# COOKIES
# ============================================================

def prepare_cookies():

    global cookies_file

    # --------------------------------------------------------
    # Already have a file path
    # --------------------------------------------------------

    cookie_path = os.environ.get("YOUTUBE_COOKIES_FILE", "").strip()

    if cookie_path:

        path = Path(cookie_path)

        if path.exists() and path.is_file():

            log(f"[SYSTEM] Cookies file: {path}")

            cookies_file = str(path)

            return cookies_file

        log(
            "[WARNING] YOUTUBE_COOKIES_FILE was set "
            "but the file does not exist."
        )

    # --------------------------------------------------------
    # Base64 cookies
    # --------------------------------------------------------

    if YOUTUBE_COOKIES_B64:

        try:

            decoded = base64.b64decode(
                YOUTUBE_COOKIES_B64
            ).decode("utf-8", errors="replace")

            if "youtube.com" in decoded:

                fd, path = tempfile.mkstemp(
                    prefix="youtube_",
                    suffix=".txt"
                )

                with os.fdopen(
                    fd,
                    "w",
                    encoding="utf-8",
                    newline="\n"
                ) as f:

                    f.write(decoded)

                cookies_file = path

                log("[SYSTEM] YouTube cookies: ENABLED (base64)")

                return cookies_file

        except Exception as e:

            log(
                f"[WARNING] Could not decode "
                f"YOUTUBE_COOKIES_B64: {e}"
            )

    # --------------------------------------------------------
    # Raw Netscape cookies
    # --------------------------------------------------------

    if YOUTUBE_COOKIES:

        content = YOUTUBE_COOKIES

        if (
            "# Netscape HTTP Cookie File" not in content
            and "# HTTP Cookie File" not in content
        ):

            log(
                "[WARNING] YOUTUBE_COOKIES does not appear "
                "to be a Netscape cookies file."
            )

        try:

            fd, path = tempfile.mkstemp(
                prefix="youtube_",
                suffix=".txt"
            )

            with os.fdopen(
                fd,
                "w",
                encoding="utf-8",
                newline="\n"
            ) as f:

                f.write(content)

            cookies_file = path

            log("[SYSTEM] YouTube cookies: ENABLED")

            return cookies_file

        except Exception as e:

            log(
                f"[WARNING] Could not create cookies file: {e}"
            )

    log("[SYSTEM] YouTube cookies: OFF")

    return None


# ============================================================
# YT-DLP COMMON OPTIONS
# ============================================================

def yt_dlp_base_command():

    command = [
        "yt-dlp",

        "--no-warnings",

        "--ignore-errors",

        "--no-playlist",

        # ----------------------------------------------------
        # Select either:
        #
        # video+audio
        # OR
        # best video + best audio
        #
        # This avoids forcing "best" only.
        # ----------------------------------------------------

        "--format",
        "bv*+ba/b",

        # ----------------------------------------------------
        # Prefer HLS when available for live streams.
        # ----------------------------------------------------

        "--extractor-args",
        "youtube:player_client=web_safari",

        # ----------------------------------------------------
        # Live stream
        # ----------------------------------------------------

        "--live-from-start",

    ]

    if cookies_file:

        command.extend([
            "--cookies",
            cookies_file
        ])

    return command


# ============================================================
# GET FRESH YOUTUBE URL(S)
# ============================================================

def get_youtube_urls():

    log("")
    log("============================================================")
    log("[SYSTEM] Resolving fresh YouTube stream URL...")
    log("============================================================")

    command = yt_dlp_base_command()

    command.extend([
        "--get-url",
        YOUTUBE_URL
    ])

    try:

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60
        )

    except subprocess.TimeoutExpired:

        log("[ERROR] yt-dlp timed out.")

        return []

    except Exception as e:

        log(f"[ERROR] yt-dlp execution failed: {e}")

        return []

    stdout = result.stdout.strip()

    stderr = result.stderr.strip()

    if result.returncode != 0:

        log("[ERROR] yt-dlp failed:")

        if stderr:
            log(stderr[-5000:])

        return []

    if not stdout:

        log("[ERROR] yt-dlp returned no stream URL.")

        if stderr:
            log(stderr[-3000:])

        return []

    # --------------------------------------------------------
    # URLs are line separated.
    #
    # With bv*+ba/b:
    #
    #   1 URL = combined stream
    #
    #   2 URLs = video + audio
    #
    # --------------------------------------------------------

    urls = [
        line.strip()
        for line in stdout.splitlines()
        if line.strip().startswith(("http://", "https://"))
    ]

    # Remove accidental duplicates.
    unique_urls = []

    for url in urls:

        if url not in unique_urls:
            unique_urls.append(url)

    if not unique_urls:

        log("[ERROR] No valid HTTP/HLS URL found.")

        return []

    log(
        f"[SYSTEM] Fresh YouTube URL(s) obtained: "
        f"{len(unique_urls)}"
    )

    return unique_urls


# ============================================================
# FFMPEG COMMAND
# ============================================================

def build_ffmpeg_command(urls):

    command = [
        "ffmpeg",

        "-hide_banner",

        "-loglevel",
        "warning",

        "-stats",

        # ----------------------------------------------------
        # Low memory / low latency
        # ----------------------------------------------------

        "-thread_queue_size",
        THREAD_QUEUE_SIZE,
    ]

    # --------------------------------------------------------
    # INPUTS
    # --------------------------------------------------------

    for url in urls:

        command.extend([

            "-reconnect",
            "1",

            "-reconnect_at_eof",
            "1",

            "-reconnect_streamed",
            "1",

            "-reconnect_on_network_error",
            "1",

            "-reconnect_delay_max",
            "10",

            "-reconnect_max_retries",
            "-1",

            "-rw_timeout",
            "30000000",

            "-http_persistent",
            "1",

            "-i",
            url
        ])

    # --------------------------------------------------------
    # STREAM MAPPING
    # --------------------------------------------------------

    if len(urls) == 1:

        # One combined stream.

        command.extend([

            "-map",
            "0:v:0",

            "-map",
            "0:a:0?",

        ])

    else:

        # Separate video + audio.

        command.extend([

            "-map",
            "0:v:0",

            "-map",
            "1:a:0",

        ])

    # --------------------------------------------------------
    # VIDEO
    #
    # NO VIDEO RE-ENCODING
    # --------------------------------------------------------

    command.extend([

        "-c:v",
        "copy",

    ])

    # --------------------------------------------------------
    # AUDIO
    #
    # Audio is re-encoded to AAC.
    # --------------------------------------------------------

    command.extend([

        "-c:a",
        "aac",

        "-b:a",
        AUDIO_BITRATE,

        "-ar",
        AUDIO_RATE,

        "-ac",
        AUDIO_CHANNELS,

        "-af",
        "aresample=async=1000:first_pts=0",

    ])

    # --------------------------------------------------------
    # TIMESTAMP HANDLING
    # --------------------------------------------------------

    command.extend([

        "-fflags",
        "+genpts+discardcorrupt",

        "-err_detect",
        "ignore_err",

        "-avoid_negative_ts",
        "disabled",

        "-max_interleave_delta",
        "0",

    ])

    # --------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------

    command.extend([

        "-f",
        "flv",

        RESTREAM_RTMP

    ])

    return command


# ============================================================
# START FFMPEG
# ============================================================

def start_ffmpeg(urls):

    global ffmpeg_process

    command = build_ffmpeg_command(urls)

    log("")
    log("============================================================")
    log("[SYSTEM] Starting FFmpeg")
    log("============================================================")

    log("[SYSTEM] Video: COPY")
    log("[SYSTEM] Video Encode: OFF")
    log(f"[SYSTEM] Audio: AAC {AUDIO_BITRATE}")
    log("[SYSTEM] Memory Mode: LOW")
    log("[SYSTEM] Sending YouTube -> Restream...")

    try:

        ffmpeg_process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=None,
            stdin=subprocess.DEVNULL,
            bufsize=0
        )

    except Exception as e:

        log(f"[ERROR] Could not start FFmpeg: {e}")

        ffmpeg_process = None

        return False

    time.sleep(3)

    if ffmpeg_process.poll() is not None:

        code = ffmpeg_process.returncode

        log(
            f"[ERROR] FFmpeg exited immediately "
            f"(exit code: {code})"
        )

        ffmpeg_process = None

        return False

    log("[SYSTEM] YouTube -> FFmpeg: CONNECTED")
    log("[SYSTEM] FFmpeg -> Restream: CONNECTED")
    log("[SYSTEM] FFmpeg process is alive.")
    log("[SYSTEM] Stream is RUNNING.")

    return True


# ============================================================
# STOP FFMPEG
# ============================================================

def stop_ffmpeg():

    global ffmpeg_process

    process = ffmpeg_process

    ffmpeg_process = None

    if process is None:
        return

    try:

        if process.poll() is None:

            log("[SYSTEM] Stopping FFmpeg...")

            process.terminate()

            try:

                process.wait(timeout=8)

            except subprocess.TimeoutExpired:

                log("[SYSTEM] Killing FFmpeg...")

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
            f"[WARNING] FFmpeg stop error: {e}"
        )


# ============================================================
# MONITOR
# ============================================================

def monitor():

    global ffmpeg_process

    heartbeat = time.time()

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

        # ----------------------------------------------------
        # Heartbeat
        # ----------------------------------------------------

        if time.time() - heartbeat >= 60:

            log("[SYSTEM] Relay is still RUNNING.")

            heartbeat = time.time()

    return False


# ============================================================
# SESSION
# ============================================================

def run_session():

    urls = get_youtube_urls()

    if not urls:

        log("[SYSTEM] No YouTube stream URL.")

        return False

    if shutdown_requested:
        return False

    return start_ffmpeg(urls) and monitor()


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
    log("Quality        : BEST AVAILABLE")
    log("Video          : COPY")
    log("Video Encode   : OFF")
    log("Crop           : OFF")
    log("Resize         : OFF")
    log("FPS Convert    : OFF")
    log(f"Audio          : AAC {AUDIO_BITRATE}")
    log("HLS Reconnect  : ON")
    log("Stall Recovery : ON")
    log("Memory Mode    : LOW")
    log("Auto-Reconnect : ON")
    log("Status         : STARTING")

    log("============================================================")

    prepare_cookies()

    log("")
    log("[SYSTEM] Starting 24/7 relay...")
    log("============================================================")

    delay = RECONNECT_DELAY
    session_number = 0

    while not shutdown_requested:

        session_number += 1

        log("")
        log("============================================================")
        log(
            f"[SYSTEM] Starting relay session #{session_number}"
        )
        log("============================================================")

        try:

            run_session()

        except Exception as e:

            log("")
            log(
                f"[ERROR] Session exception: "
                f"{type(e).__name__}: {e}"
            )

        if shutdown_requested:
            break

        stop_ffmpeg()

        log("")
        log("============================================================")
        log("[SYSTEM] Stream ended or connection lost.")
        log(
            f"[SYSTEM] Reconnecting in {delay} seconds..."
        )
        log("============================================================")

        # ----------------------------------------------------
        # Exponential reconnect:
        #
        # 8 -> 16 -> 32 -> 60
        #
        # Prevents hammering YouTube if its live endpoint
        # temporarily refuses requests.
        # ----------------------------------------------------

        end_time = time.time() + delay

        while (
            time.time() < end_time
            and not shutdown_requested
        ):

            time.sleep(1)

        delay = min(
            delay * 2,
            MAX_RECONNECT_DELAY
        )

        # ----------------------------------------------------
        # Once a session successfully runs, reset delay.
        #
        # This prevents a normal temporary disconnect from
        # permanently increasing the reconnect interval.
        # ----------------------------------------------------

        # A successful process reaching monitor means we had
        # an active FFmpeg session.
        #
        # Reset after every normal reconnect attempt.
        if delay >= MAX_RECONNECT_DELAY:

            delay = RECONNECT_DELAY

    # --------------------------------------------------------
    # Shutdown
    # --------------------------------------------------------

    stop_ffmpeg()

    if cookies_file:

        try:
            os.unlink(cookies_file)
        except Exception:
            pass

    log("")
    log("============================================================")
    log("[SYSTEM] Relay stopped.")
    log("============================================================")


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        shutdown_requested = True

        stop_ffmpeg()

    except Exception as e:

        log("")
        log("============================================================")
        log("[SYSTEM] FATAL ERROR")
        log(
            f"[SYSTEM] {type(e).__name__}: {e}"
        )
        log("============================================================")

        stop_ffmpeg()

        sys.exit(1)
