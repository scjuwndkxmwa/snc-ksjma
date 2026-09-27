import os
import sys
import time
import signal
import subprocess
import tempfile
import base64


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

# ============================================================
# RAILWAY VARIABLES
# ============================================================

YOUTUBE_COOKIES = os.getenv("YOUTUBE_COOKIES", "").strip()

YOUTUBE_COOKIES_B64 = os.getenv(
    "YOUTUBE_COOKIES_B64",
    ""
).strip()

YOUTUBE_USER_AGENT = os.getenv(
    "YOUTUBE_USER_AGENT",
    ""
).strip()


# ============================================================
# SETTINGS
# ============================================================

AUDIO_BITRATE = "128k"
AUDIO_RATE = "44100"
AUDIO_CHANNELS = "2"

RECONNECT_DELAY = 10
MAX_RECONNECT_DELAY = 60

YT_TIMEOUT = 90

shutdown_requested = False
ffmpeg_process = None
cookies_file = None


# ============================================================
# LOG
# ============================================================

def log(text=""):
    print(text, flush=True)


# ============================================================
# SIGNAL HANDLER
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
# CLEANUP
# ============================================================

def cleanup():

    global ffmpeg_process
    global cookies_file

    if ffmpeg_process is not None:

        try:

            if ffmpeg_process.poll() is None:

                log("[SYSTEM] Stopping FFmpeg...")

                ffmpeg_process.terminate()

                try:
                    ffmpeg_process.wait(timeout=8)

                except subprocess.TimeoutExpired:

                    log("[SYSTEM] Killing FFmpeg...")

                    try:
                        ffmpeg_process.kill()
                    except Exception:
                        pass

                    try:
                        ffmpeg_process.wait(timeout=3)
                    except Exception:
                        pass

        except Exception:
            pass

        ffmpeg_process = None

    if cookies_file:

        try:
            if os.path.exists(cookies_file):
                os.remove(cookies_file)
        except Exception:
            pass

        cookies_file = None


# ============================================================
# PREPARE COOKIES
# ============================================================

def prepare_cookies():

    global cookies_file

    # --------------------------------------------------------
    # BASE64 FIRST
    # --------------------------------------------------------

    if YOUTUBE_COOKIES_B64:

        log("[SYSTEM] YouTube cookies: BASE64 mode")

        try:

            decoded = base64.b64decode(
                YOUTUBE_COOKIES_B64
            ).decode(
                "utf-8",
                errors="replace"
            )

        except Exception as e:

            raise RuntimeError(
                f"Invalid YOUTUBE_COOKIES_B64: {e}"
            )

        cookies_file = write_cookie_file(decoded)

        return cookies_file

    # --------------------------------------------------------
    # RAW COOKIES
    # --------------------------------------------------------

    if YOUTUBE_COOKIES:

        log("[SYSTEM] YouTube cookies: ON")

        cookies_file = write_cookie_file(
            YOUTUBE_COOKIES
        )

        return cookies_file

    # --------------------------------------------------------
    # NO COOKIES
    # --------------------------------------------------------

    raise RuntimeError(
        "\n"
        "YOUTUBE_COOKIES is EMPTY.\n"
        "\n"
        "Add YOUTUBE_COOKIES to Railway Variables.\n"
        "\n"
        "The value must be the COMPLETE Netscape cookies.txt "
        "content.\n"
        "\n"
        "Example first line:\n"
        "# Netscape HTTP Cookie File\n"
    )


# ============================================================
# WRITE + VALIDATE COOKIES
# ============================================================

def write_cookie_file(content):

    content = content.replace(
        "\r\n",
        "\n"
    ).replace(
        "\r",
        "\n"
    )

    content = content.strip() + "\n"

    valid_header = (
        "# Netscape HTTP Cookie File"
        in content
        or
        "# HTTP Cookie File"
        in content
    )

    if not valid_header:

        raise RuntimeError(
            "\n"
            "Invalid YOUTUBE_COOKIES format.\n"
            "\n"
            "The cookie content must be a Netscape/Mozilla "
            "cookies.txt file.\n"
            "\n"
            "Expected first line:\n"
            "# Netscape HTTP Cookie File\n"
        )

    # --------------------------------------------------------
    # Make sure YouTube cookies exist.
    # --------------------------------------------------------

    youtube_lines = []

    for line in content.splitlines():

        if line.startswith(".youtube.com") \
                or line.startswith("youtube.com"):

            youtube_lines.append(line)

    if not youtube_lines:

        raise RuntimeError(
            "\n"
            "Cookies file was received, but no youtube.com "
            "cookies were found.\n"
            "\n"
            "Export fresh YouTube cookies and put the COMPLETE "
            "file into YOUTUBE_COOKIES.\n"
        )

    # --------------------------------------------------------
    # Create temporary file.
    # --------------------------------------------------------

    fd, path = tempfile.mkstemp(
        prefix="youtube_",
        suffix=".txt"
    )

    try:

        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
            newline="\n"
        ) as f:

            f.write(content)

    except Exception:

        try:
            os.remove(path)
        except Exception:
            pass

        raise

    log(
        f"[SYSTEM] YouTube cookie entries detected: "
        f"{len(youtube_lines)}"
    )

    log("[SYSTEM] YouTube cookies file ready.")

    return path


# ============================================================
# YT-DLP COMMAND
# ============================================================

def build_ytdlp_command():

    command = [

        "yt-dlp",

        "--no-playlist",

        "--no-warnings",

        "--ignore-errors",

        # ----------------------------------------------------
        # Do NOT force "best".
        #
        # Allow:
        # video + audio
        #
        # or:
        #
        # best combined fallback
        # ----------------------------------------------------

        "-f",
        "bv*+ba/b",

        # ----------------------------------------------------
        # Live stream
        # ----------------------------------------------------

        "--live-from-start",

        # ----------------------------------------------------
        # We need the actual playback URL(s)
        # ----------------------------------------------------

        "--get-url",

        YOUTUBE_URL
    ]

    # --------------------------------------------------------
    # COOKIES
    # --------------------------------------------------------

    command.extend([
        "--cookies",
        cookies_file
    ])

    # --------------------------------------------------------
    # USER AGENT
    # --------------------------------------------------------

    if YOUTUBE_USER_AGENT:

        command.extend([
            "--user-agent",
            YOUTUBE_USER_AGENT
        ])

    return command


# ============================================================
# GET YOUTUBE URL
# ============================================================

def get_youtube_urls():

    log("")
    log("============================================================")
    log("[SYSTEM] Resolving fresh YouTube stream URL...")
    log("============================================================")

    command = build_ytdlp_command()

    try:

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=YT_TIMEOUT
        )

    except subprocess.TimeoutExpired:

        log(
            "[ERROR] yt-dlp timed out."
        )

        return []

    except FileNotFoundError:

        log(
            "[ERROR] yt-dlp is not installed."
        )

        return []

    except Exception as e:

        log(
            f"[ERROR] yt-dlp execution error: {e}"
        )

        return []

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()

    # --------------------------------------------------------
    # ERROR
    # --------------------------------------------------------

    if result.returncode != 0:

        log("[ERROR] yt-dlp failed:")

        if stderr:

            log(
                stderr[-8000:]
            )

        return []

    # --------------------------------------------------------
    # EXTRACT URLS
    # --------------------------------------------------------

    urls = []

    for line in stdout.splitlines():

        line = line.strip()

        if line.startswith("http://") \
                or line.startswith("https://"):

            if line not in urls:

                urls.append(line)

    # --------------------------------------------------------
    # NO URL
    # --------------------------------------------------------

    if not urls:

        log(
            "[ERROR] yt-dlp returned no playback URL."
        )

        if stderr:

            log(
                stderr[-4000:]
            )

        return []

    log(
        f"[SYSTEM] Fresh YouTube URL(s) obtained: "
        f"{len(urls)}"
    )

    return urls


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

    ]

    # ========================================================
    # INPUTS
    # ========================================================

    for url in urls:

        command.extend([

            # ------------------------------------------------
            # HTTP reconnect
            # ------------------------------------------------

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

            # ------------------------------------------------
            # Network timeout
            # ------------------------------------------------

            "-rw_timeout",
            "30000000",

            # ------------------------------------------------
            # Input
            # ------------------------------------------------

            "-i",
            url
        ])

    # ========================================================
    # MAP
    # ========================================================

    if len(urls) == 1:

        command.extend([

            "-map",
            "0:v:0",

            "-map",
            "0:a:0?"

        ])

    else:

        command.extend([

            "-map",
            "0:v:0",

            "-map",
            "1:a:0?"

        ])

    # ========================================================
    # VIDEO COPY
    # ========================================================

    command.extend([

        "-c:v",
        "copy"

    ])

    # ========================================================
    # AUDIO
    # ========================================================

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
        "aresample=async=1000:first_pts=0"

    ])

    # ========================================================
    # TIMESTAMPS
    # ========================================================

    command.extend([

        "-fflags",
        "+genpts+discardcorrupt",

        "-err_detect",
        "ignore_err",

        "-avoid_negative_ts",
        "disabled",

        "-max_interleave_delta",
        "0"

    ])

    # ========================================================
    # FLV OUTPUT
    # ========================================================

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
    log("[SYSTEM] HLS/HTTP Reconnect: ON")
    log("[SYSTEM] Sending YouTube -> Restream...")

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
            f"[ERROR] Could not start FFmpeg: {e}"
        )

        ffmpeg_process = None

        return False

    # --------------------------------------------------------
    # Give FFmpeg time to connect.
    # --------------------------------------------------------

    time.sleep(5)

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
# MONITOR
# ============================================================

def monitor():

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
                f"(exit code: {code})"
            )

            return False

        if time.time() - heartbeat >= 60:

            log(
                "[SYSTEM] Relay is still RUNNING."
            )

            heartbeat = time.time()

    return False


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
        "Cookies        : CHECKING"
    )

    log(
        "Quality        : BEST AVAILABLE"
    )

    log(
        "Video          : COPY"
    )

    log(
        "Video Encode   : OFF"
    )

    log(
        "Crop           : OFF"
    )

    log(
        "Resize         : OFF"
    )

    log(
        "FPS Convert    : OFF"
    )

    log(
        f"Audio          : AAC {AUDIO_BITRATE}"
    )

    log(
        "HLS Reconnect  : ON"
    )

    log(
        "Auto-Reconnect : ON"
    )

    log(
        "Memory Mode    : LOW"
    )

    log(
        "============================================================"
    )

    # --------------------------------------------------------
    # COOKIES ARE REQUIRED
    # --------------------------------------------------------

    prepare_cookies()

    log(
        "[SYSTEM] YouTube cookies: ON"
    )

    log(
        "[SYSTEM] Starting 24/7 relay..."
    )

    reconnect_delay = RECONNECT_DELAY

    session_number = 0

    while not shutdown_requested:

        session_number += 1

        log("")
        log("============================================================")
        log(
            f"[SYSTEM] Starting relay session #{session_number}"
        )
        log("============================================================")

        urls = get_youtube_urls()

        if shutdown_requested:
            break

        if not urls:

            cleanup()

            log(
                f"[SYSTEM] Reconnecting in "
                f"{reconnect_delay} seconds..."
            )

            for _ in range(reconnect_delay):

                if shutdown_requested:
                    break

                time.sleep(1)

            reconnect_delay = min(
                reconnect_delay * 2,
                MAX_RECONNECT_DELAY
            )

            continue

        # ----------------------------------------------------
        # Start FFmpeg
        # ----------------------------------------------------

        if start_ffmpeg(urls):

            # We successfully reached FFmpeg.
            reconnect_delay = RECONNECT_DELAY

            monitor()

        # ----------------------------------------------------
        # Cleanup
        # ----------------------------------------------------

        cleanup()

        if shutdown_requested:
            break

        log("")
        log("============================================================")
        log(
            "[SYSTEM] Stream ended or connection lost."
        )
        log(
            f"[SYSTEM] Reconnecting in "
            f"{reconnect_delay} seconds..."
        )
        log("============================================================")

        for _ in range(reconnect_delay):

            if shutdown_requested:
                break

            time.sleep(1)

        reconnect_delay = min(
            reconnect_delay * 2,
            MAX_RECONNECT_DELAY
        )

    # --------------------------------------------------------
    # FINAL CLEANUP
    # --------------------------------------------------------

    cleanup()

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

        cleanup()

    except Exception as e:

        log("")
        log("============================================================")
        log("[SYSTEM] FATAL ERROR")
        log(
            f"[SYSTEM] {type(e).__name__}: {e}"
        )
        log("============================================================")

        cleanup()

        sys.exit(1)

    finally:

        cleanup()
