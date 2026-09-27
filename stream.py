import os
import sys
import time
import signal
import subprocess
import tempfile


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

# ============================================================
# RECONNECT
# ============================================================

RECONNECT_DELAY = 5

MAX_RECONNECT_DELAY = 30

# ============================================================
# MEMORY
# ============================================================

# Keep this small.
# Do NOT use 512M or huge buffers.
RINGBUFFER_SIZE = "16M"

THREAD_QUEUE_SIZE = "512"

# ============================================================
# STREAMLINK
# ============================================================

HLS_LIVE_EDGE = "2"

RETRY_STREAMS = "10"

# 0 = unlimited
RETRY_MAX = "0"

SEGMENT_ATTEMPTS = "5"

SEGMENT_THREADS = "1"

SEGMENT_TIMEOUT = "15"

STREAM_TIMEOUT = "30"

PLAYLIST_RELOAD_ATTEMPTS = "5"

# ============================================================
# AUDIO
# ============================================================

AUDIO_BITRATE = "128k"

AUDIO_RATE = "44100"

AUDIO_CHANNELS = "2"


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
    log("============================================================")
    log("[SYSTEM] Shutdown requested...")
    log("============================================================")


signal.signal(signal.SIGINT, handle_signal)

signal.signal(signal.SIGTERM, handle_signal)


# ============================================================
# CREATE COOKIES FILE
# ============================================================

def prepare_cookies():

    global cookies_file

    cookies_data = os.environ.get("YOUTUBE_COOKIES", "").strip()

    if not cookies_data:

        log("[SYSTEM] YouTube Cookies: OFF")

        return None

    try:

        fd, path = tempfile.mkstemp(
            prefix="youtube_",
            suffix=".txt"
        )

        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:

            f.write(cookies_data)

            if not cookies_data.endswith("\n"):
                f.write("\n")

        cookies_file = path

        log("[SYSTEM] YouTube Cookies: ON")

        log("[SYSTEM] Cookies file prepared.")

        return path

    except Exception as e:

        log(
            f"[ERROR] Could not create YouTube cookies file: {e}"
        )

        return None


# ============================================================
# CLEAN COOKIES
# ============================================================

def remove_cookies():

    global cookies_file

    if not cookies_file:
        return

    try:

        if os.path.exists(cookies_file):
            os.remove(cookies_file)

    except Exception:
        pass

    cookies_file = None


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
            f"[SYSTEM] Error stopping {name}: {e}"
        )


# ============================================================
# STOP EVERYTHING
# ============================================================

def stop_all():

    global streamlink_process
    global ffmpeg_process

    if ffmpeg_process is not None:

        stop_process(
            ffmpeg_process,
            "FFmpeg"
        )

    ffmpeg_process = None

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

        "--retry-streams",
        RETRY_STREAMS,

        "--retry-max",
        RETRY_MAX,

        "--retry-open",
        "5",

        "--ringbuffer-size",
        RINGBUFFER_SIZE,

        "--stream-segment-attempts",
        SEGMENT_ATTEMPTS,

        "--stream-segment-threads",
        SEGMENT_THREADS,

        "--stream-segment-timeout",
        SEGMENT_TIMEOUT,

        "--stream-timeout",
        STREAM_TIMEOUT,

        "--hls-live-edge",
        HLS_LIVE_EDGE,

        "--hls-playlist-reload-attempts",
        PLAYLIST_RELOAD_ATTEMPTS,

    ]

    # --------------------------------------------------------
    # COOKIES
    # --------------------------------------------------------

    if cookies_file:

        command.extend([
            "--http-cookie",
            cookies_file
        ])

    # --------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------

    command.extend([

        "--stdout",

        YOUTUBE_URL,

        QUALITY
    ])

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

        # ====================================================
        # LOW MEMORY PIPE
        # ====================================================

        "-thread_queue_size",
        THREAD_QUEUE_SIZE,

        "-i",
        "-",

        # ====================================================
        # VIDEO
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

        "-avoid_negative_ts",
        "make_zero",

        # ====================================================
        # OUTPUT
        # ====================================================

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
    log("============================================================")
    log("[SYSTEM] Starting relay session")
    log("============================================================")

    # ========================================================
    # STREAMLINK
    # ========================================================

    command = build_streamlink_command()

    log("[SYSTEM] Starting Streamlink...")
    log(
        f"[SYSTEM] Cookies: "
        f"{'ON' if cookies_file else 'OFF'}"
    )

    log(f"[SYSTEM] Quality: {QUALITY.upper()}")

    log("[SYSTEM] Video source: COPY")

    log("[SYSTEM] Audio: AAC 128k")

    log("[SYSTEM] Memory mode: LOW")

    log("[SYSTEM] Waiting for YouTube stream...")

    try:

        streamlink_process = subprocess.Popen(

            command,

            stdout=subprocess.PIPE,

            stderr=None,

            bufsize=0
        )

    except Exception as e:

        log(
            f"[ERROR] Could not start Streamlink: {e}"
        )

        streamlink_process = None

        return False

    # ========================================================
    # GIVE STREAMLINK TIME
    # ========================================================

    time.sleep(3)

    if streamlink_process.poll() is not None:

        code = streamlink_process.returncode

        log(
            "[ERROR] Streamlink exited immediately "
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

    log("[SYSTEM] Audio: AAC 128k")

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
            f"[ERROR] Could not start FFmpeg: {e}"
        )

        stop_all()

        return False

    # ========================================================
    # CLOSE PARENT COPY
    # ========================================================

    try:

        if streamlink_process.stdout:

            streamlink_process.stdout.close()

    except Exception:
        pass

    # ========================================================
    # CHECK
    # ========================================================

    time.sleep(3)

    if ffmpeg_process.poll() is not None:

        code = ffmpeg_process.returncode

        log(
            "[ERROR] FFmpeg exited immediately "
            f"(exit code: {code})"
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

def monitor_session():

    global streamlink_process
    global ffmpeg_process

    last_status = time.time()

    while not shutdown_requested:

        time.sleep(2)

        # ====================================================
        # STREAMLINK
        # ====================================================

        if streamlink_process is None:

            log("[SYSTEM] Streamlink process missing.")

            return False

        streamlink_code = (
            streamlink_process.poll()
        )

        if streamlink_code is not None:

            log("")

            log(
                "[SYSTEM] Streamlink stopped "
                f"(exit code: {streamlink_code})"
            )

            return False

        # ====================================================
        # FFMPEG
        # ====================================================

        if ffmpeg_process is None:

            log("[SYSTEM] FFmpeg process missing.")

            return False

        ffmpeg_code = (
            ffmpeg_process.poll()
        )

        if ffmpeg_code is not None:

            log("")

            log(
                "[SYSTEM] FFmpeg stopped "
                f"(exit code: {ffmpeg_code})"
            )

            return False

        # ====================================================
        # HEARTBEAT
        # ====================================================

        if time.time() - last_status >= 60:

            log(
                "[SYSTEM] Relay is still RUNNING."
            )

            last_status = time.time()

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

    log("Destination    : Restream")

    log(
        "Cookies        : "
        f"{'ON' if cookies_file else 'OFF'}"
    )

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

    reconnect_delay = RECONNECT_DELAY

    while not shutdown_requested:

        # ====================================================
        # START
        # ====================================================

        success = start_session()

        if shutdown_requested:
            break

        if not success:

            log("")

            log(
                "[SYSTEM] Stream ended or connection lost."
            )

            log(
                f"[SYSTEM] Reconnecting in "
                f"{reconnect_delay} seconds..."
            )

            stop_all()

            time.sleep(reconnect_delay)

            reconnect_delay = min(
                reconnect_delay + 2,
                MAX_RECONNECT_DELAY
            )

            continue

        # ====================================================
        # SUCCESS
        # ====================================================

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

        log(
            "[SYSTEM] Stream ended or connection lost."
        )

        stop_all()

        log(
            f"[SYSTEM] Reconnecting in "
            f"{reconnect_delay} seconds..."
        )

        time.sleep(reconnect_delay)


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    try:

        # ----------------------------------------------------
        # PREPARE COOKIES FIRST
        # ----------------------------------------------------

        prepare_cookies()

        # ----------------------------------------------------
        # START
        # ----------------------------------------------------

        main()

    except KeyboardInterrupt:

        shutdown_requested = True

        log("[SYSTEM] Keyboard interrupt.")

    except Exception as e:

        log("")
        log("============================================================")
        log("[SYSTEM] UNEXPECTED ERROR")
        log(
            f"[SYSTEM] {type(e).__name__}: {e}"
        )
        log("============================================================")

    finally:

        stop_all()

        remove_cookies()

        log("[SYSTEM] Relay stopped.")
