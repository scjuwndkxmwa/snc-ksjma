import os
import sys
import time
import signal
import subprocess
import base64
import tempfile


# ============================================================
# CONFIG
# ============================================================

YOUTUBE_URL = "https://www.youtube.com/live/7DHNbnPMNiM"

# ============================================================
# RESTREAM
# ============================================================

RESTREAM_STREAM_KEY = (
    "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9"
)

RESTREAM_RTMP = (
    f"rtmp://live.restream.io/live/{RESTREAM_STREAM_KEY}"
)

# ============================================================
# STREAM
# ============================================================

QUALITY = "best"

# لا نريد buffer ضخم يستهلك Railway RAM
RINGBUFFER_SIZE = "32M"

# عدد قليل من القطع أمام البث لتقليل التأخير
HLS_LIVE_EDGE = "3"

# إعادة المحاولة بلا نهاية
RETRY_STREAMS = "5"
RETRY_MAX = "0"

# HLS
SEGMENT_ATTEMPTS = "5"
SEGMENT_THREADS = "1"
SEGMENT_TIMEOUT = "20"

STREAM_TIMEOUT = "60"

PLAYLIST_RELOAD_ATTEMPTS = "8"

# ============================================================
# AUDIO
# ============================================================

AUDIO_BITRATE = "128k"
AUDIO_RATE = "44100"
AUDIO_CHANNELS = "2"


# ============================================================
# RECONNECT
# ============================================================

RECONNECT_DELAY = 5
MAX_RECONNECT_DELAY = 60


# ============================================================
# GLOBALS
# ============================================================

streamlink_process = None
ffmpeg_process = None

shutdown_requested = False

cookies_file = None


# ============================================================
# LOG
# ============================================================

def log(text=""):
    print(text, flush=True)


# ============================================================
# SIGNAL
# ============================================================

def handle_signal(signum, frame):

    global shutdown_requested

    shutdown_requested = True

    log("")
    log("[SYSTEM] Shutdown requested...")


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


# ============================================================
# COOKIES
# ============================================================

def prepare_youtube_cookies():

    global cookies_file

    encoded = os.environ.get("YOUTUBE_COOKIES_B64", "").strip()

    if not encoded:

        log("[SYSTEM] YouTube Cookies: OFF")
        return None

    try:

        decoded = base64.b64decode(
            encoded,
            validate=True
        )

        if not decoded:

            raise ValueError("Cookie data is empty.")

        path = "/tmp/youtube_cookies.txt"

        with open(path, "wb") as f:
            f.write(decoded)

        # Basic validation
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            first_lines = f.read(4096)

        if (
            "# Netscape HTTP Cookie File" not in first_lines
            and
            "# HTTP Cookie File" not in first_lines
        ):

            log(
                "[WARNING] Cookie file does not look like "
                "a Netscape cookies.txt file."
            )

        cookies_file = path

        log("[SYSTEM] YouTube Cookies: ON")
        log("[SYSTEM] Cookie file prepared.")

        return path

    except Exception as e:

        log(
            "[ERROR] Could not decode "
            f"YOUTUBE_COOKIES_B64: {e}"
        )

        return None


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
            f"[SYSTEM] Error stopping "
            f"{name}: {e}"
        )


# ============================================================
# STOP ALL
# ============================================================

def stop_all():

    global streamlink_process
    global ffmpeg_process

    # FFmpeg first
    if ffmpeg_process is not None:

        stop_process(
            ffmpeg_process,
            "FFmpeg"
        )

    ffmpeg_process = None

    # Streamlink second
    if streamlink_process is not None:

        stop_process(
            streamlink_process,
            "Streamlink"
        )

    streamlink_process = None


# ============================================================
# STREAMLINK COMMAND
# ============================================================

def build_streamlink_command():

    command = [

        "streamlink",

        "--loglevel",
        "info",

        # ----------------------------------------------------
        # RETRIES
        # ----------------------------------------------------

        "--retry-streams",
        RETRY_STREAMS,

        "--retry-max",
        RETRY_MAX,

        "--retry-open",
        "5",

        # ----------------------------------------------------
        # BUFFER
        # ----------------------------------------------------

        "--ringbuffer-size",
        RINGBUFFER_SIZE,

        # ----------------------------------------------------
        # HLS
        # ----------------------------------------------------

        "--hls-live-edge",
        HLS_LIVE_EDGE,

        "--hls-playlist-reload-attempts",
        PLAYLIST_RELOAD_ATTEMPTS,

        # ----------------------------------------------------
        # SEGMENTS
        # ----------------------------------------------------

        "--stream-segment-attempts",
        SEGMENT_ATTEMPTS,

        "--stream-segment-threads",
        SEGMENT_THREADS,

        "--stream-segment-timeout",
        SEGMENT_TIMEOUT,

        "--stream-timeout",
        STREAM_TIMEOUT,

        # ----------------------------------------------------
        # OUTPUT
        # ----------------------------------------------------

        "--stdout",

        YOUTUBE_URL,

        QUALITY
    ]

    # --------------------------------------------------------
    # COOKIES
    # --------------------------------------------------------

    if cookies_file:

        command.insert(
            command.index("--stdout"),
            "--http-cookies-file"
        )

        command.insert(
            command.index("--stdout"),
            cookies_file
        )

    return command


# ============================================================
# FFMPEG COMMAND
# ============================================================

def build_ffmpeg_command():

    return [

        "ffmpeg",

        "-hide_banner",

        "-loglevel",
        "warning",

        "-stats",

        # ----------------------------------------------------
        # INPUT BUFFER
        # ----------------------------------------------------

        "-thread_queue_size",
        "256",

        "-i",
        "-",

        # ----------------------------------------------------
        # VIDEO
        # ----------------------------------------------------

        "-map",
        "0:v:0",

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

        "-af",
        "aresample="
        "async=1000:"
        "min_hard_comp=0.100:"
        "first_pts=0",

        # ----------------------------------------------------
        # TIMESTAMPS
        # ----------------------------------------------------

        "-fflags",
        "+genpts+discardcorrupt",

        "-err_detect",
        "ignore_err",

        # مهم مع إعادة الاتصال
        "-max_interleave_delta",
        "0",

        # ----------------------------------------------------
        # OUTPUT
        # ----------------------------------------------------

        "-f",
        "flv",

        RESTREAM_RTMP
    ]


# ============================================================
# START SESSION
# ============================================================

def start_session():

    global streamlink_process
    global ffmpeg_process

    stop_all()

    log("")
    log("=" * 60)
    log("[SYSTEM] Starting relay session")
    log("=" * 60)

    # ========================================================
    # STREAMLINK
    # ========================================================

    command = build_streamlink_command()

    log("[SYSTEM] Starting Streamlink...")
    log(f"[SYSTEM] Quality: {QUALITY.upper()}")
    log("[SYSTEM] Video: COPY")
    log("[SYSTEM] Video Encode: OFF")
    log(f"[SYSTEM] Audio: AAC {AUDIO_BITRATE}")
    log("[SYSTEM] Memory Mode: LOW")

    if cookies_file:
        log("[SYSTEM] YouTube Cookies: ON")
    else:
        log("[SYSTEM] YouTube Cookies: OFF")

    log("[SYSTEM] Waiting for YouTube stream...")

    try:

        streamlink_process = subprocess.Popen(

            command,

            stdout=subprocess.PIPE,

            stderr=None,

            stdin=subprocess.DEVNULL,

            bufsize=0
        )

    except Exception as e:

        log(
            f"[ERROR] Could not start "
            f"Streamlink: {e}"
        )

        streamlink_process = None

        return False

    # --------------------------------------------------------
    # Give Streamlink time to initialize
    # --------------------------------------------------------

    time.sleep(3)

    if streamlink_process.poll() is not None:

        code = streamlink_process.returncode

        log(
            "[ERROR] Streamlink exited "
            f"(exit code: {code})"
        )

        streamlink_process = None

        return False

    log("[SYSTEM] Streamlink process is alive.")

    # ========================================================
    # FFMPEG
    # ========================================================

    ffmpeg_command = build_ffmpeg_command()

    log("[SYSTEM] Starting FFmpeg...")
    log("[SYSTEM] Video: COPY")
    log("[SYSTEM] Video Encode: OFF")
    log(f"[SYSTEM] Audio: AAC {AUDIO_BITRATE}")
    log("[SYSTEM] Sending YouTube -> Restream...")

    try:

        ffmpeg_process = subprocess.Popen(

            ffmpeg_command,

            stdin=streamlink_process.stdout,

            stdout=subprocess.DEVNULL,

            stderr=None,

            bufsize=0
        )

    except Exception as e:

        log(
            f"[ERROR] Could not start "
            f"FFmpeg: {e}"
        )

        stop_all()

        return False

    # Parent doesn't need this descriptor anymore
    try:

        if streamlink_process.stdout:
            streamlink_process.stdout.close()

    except Exception:
        pass

    time.sleep(4)

    # ========================================================
    # CHECK
    # ========================================================

    if ffmpeg_process.poll() is not None:

        code = ffmpeg_process.returncode

        log(
            "[ERROR] FFmpeg exited "
            f"(exit code: {code})"
        )

        stop_all()

        return False

    log("[SYSTEM] YouTube -> FFmpeg: CONNECTED")
    log("[SYSTEM] FFmpeg -> Restream: CONNECTED")
    log("[SYSTEM] Stream is RUNNING.")

    return True


# ============================================================
# MONITOR
# ============================================================

def monitor_session():

    global streamlink_process
    global ffmpeg_process

    last_heartbeat = time.time()

    while not shutdown_requested:

        time.sleep(3)

        # ----------------------------------------------------
        # STREAMLINK
        # ----------------------------------------------------

        if streamlink_process is None:

            log("[ERROR] Streamlink process missing.")

            return False

        streamlink_code = (
            streamlink_process.poll()
        )

        if streamlink_code is not None:

            log(
                "[SYSTEM] Streamlink stopped "
                f"(exit code: {streamlink_code})"
            )

            return False

        # ----------------------------------------------------
        # FFMPEG
        # ----------------------------------------------------

        if ffmpeg_process is None:

            log("[ERROR] FFmpeg process missing.")

            return False

        ffmpeg_code = (
            ffmpeg_process.poll()
        )

        if ffmpeg_code is not None:

            log(
                "[SYSTEM] FFmpeg stopped "
                f"(exit code: {ffmpeg_code})"
            )

            return False

        # ----------------------------------------------------
        # HEARTBEAT
        # ----------------------------------------------------

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
# MAIN
# ============================================================

def main():

    global shutdown_requested

    log("=" * 60)
    log("       YouTube 24/7 -> Restream -> TikTok")
    log("=" * 60)

    log(f"YouTube        : {YOUTUBE_URL}")
    log("Destination    : Restream")
    log("Extractor      : Streamlink")

    if cookies_file:
        log("Cookies        : ON")
    else:
        log("Cookies        : OFF")

    log("Quality        : BEST")
    log("Video          : COPY")
    log("Video Encode   : OFF")
    log("Crop           : OFF")
    log("Resize         : OFF")
    log("FPS Convert    : OFF")
    log(f"Audio          : AAC {AUDIO_BITRATE}")
    log("Memory Mode    : LOW")
    log("Auto-Reconnect : ON")
    log("Status         : STARTING")
    log("=" * 60)

    log("[SYSTEM] Starting 24/7 relay...")

    reconnect_delay = RECONNECT_DELAY

    while not shutdown_requested:

        # ====================================================
        # START
        # ====================================================

        success = start_session()

        if shutdown_requested:
            break

        if not success:

            stop_all()

            log("")
            log(
                "[SYSTEM] Stream ended or "
                "connection lost."
            )

            log(
                f"[SYSTEM] Reconnecting in "
                f"{reconnect_delay} seconds..."
            )

            time.sleep(reconnect_delay)

            reconnect_delay = min(
                reconnect_delay * 2,
                MAX_RECONNECT_DELAY
            )

            continue

        # ====================================================
        # SUCCESS
        # ====================================================

        # بمجرد نجاح الاتصال نرجع زمن
        # إعادة الاتصال إلى 5 ثواني.
        reconnect_delay = RECONNECT_DELAY

        # ====================================================
        # MONITOR
        # ====================================================

        monitor_session()

        if shutdown_requested:
            break

        # ====================================================
        # RECONNECT
        # ====================================================

        log("")
        log("=" * 60)
        log("[SYSTEM] Stream ended or connection lost.")
        log(
            f"[SYSTEM] Reconnecting in "
            f"{reconnect_delay} seconds..."
        )
        log("=" * 60)

        stop_all()

        time.sleep(reconnect_delay)


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    try:

        # Prepare cookies BEFORE starting Streamlink
        prepare_youtube_cookies()

        main()

    except KeyboardInterrupt:

        shutdown_requested = True

        log("[SYSTEM] Keyboard interrupt.")

    except Exception as e:

        log("")
        log("=" * 60)
        log("[SYSTEM] UNEXPECTED ERROR")
        log(
            f"[SYSTEM] {type(e).__name__}: {e}"
        )
        log("=" * 60)

    finally:

        stop_all()

        log("[SYSTEM] Relay stopped.")
