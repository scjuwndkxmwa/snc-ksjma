import os
import sys
import time
import signal
import base64
import tempfile
import subprocess


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

RECONNECT_DELAY = 10

# ============================================================
# STREAMLINK
# ============================================================

RINGBUFFER_SIZE = "32M"
HLS_LIVE_EDGE = "2"

RETRY_STREAMS = "5"
RETRY_MAX = "0"

SEGMENT_ATTEMPTS = "5"
SEGMENT_THREADS = "1"
SEGMENT_TIMEOUT = "20"

STREAM_TIMEOUT = "60"

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
    log("[SYSTEM] Shutdown requested...")


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


# ============================================================
# CREATE COOKIES FILE
# ============================================================

def prepare_cookies():

    global cookies_file

    cookies_b64 = os.environ.get("YOUTUBE_COOKIES_B64", "").strip()

    if not cookies_b64:
        log("[SYSTEM] YouTube Cookies: OFF")
        return None

    try:

        data = base64.b64decode(cookies_b64)

        fd, path = tempfile.mkstemp(
            prefix="youtube_",
            suffix=".txt"
        )

        with os.fdopen(fd, "wb") as f:
            f.write(data)

        cookies_file = path

        log("[SYSTEM] YouTube Cookies: ON")

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
        "5",

    ]

    # --------------------------------------------------------
    # COOKIES
    # --------------------------------------------------------

    if cookies_file:

        command.extend([
            "--http-cookies-file",
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

        # ----------------------------------------------------
        # INPUT
        # ----------------------------------------------------

        "-thread_queue_size",
        "512",

        "-i",
        "-",

        # ----------------------------------------------------
        # VIDEO COPY
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
        "aresample=async=1000:min_hard_comp=0.100:first_pts=0",

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
        # FLV
        # ----------------------------------------------------

        "-flvflags",
        "no_duration_filesize",

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

    # --------------------------------------------------------
    # STREAMLINK
    # --------------------------------------------------------

    command = build_streamlink_command()

    log("[SYSTEM] Starting Streamlink...")
    log(f"[SYSTEM] Quality: {QUALITY.upper()}")
    log("[SYSTEM] Video: COPY")
    log("[SYSTEM] Video Encode: OFF")
    log(f"[SYSTEM] Audio: AAC {AUDIO_BITRATE}")
    log("[SYSTEM] Memory Mode: LOW")

    try:

        streamlink_process = subprocess.Popen(

            command,

            stdout=subprocess.PIPE,

            stderr=None,

            bufsize=0

        )

    except Exception as e:

        log(
            f"[ERROR] Could not start "
            f"Streamlink: {e}"
        )

        streamlink_process = None

        return False

    time.sleep(3)

    if streamlink_process.poll() is not None:

        log(
            "[ERROR] Streamlink exited "
            f"(code {streamlink_process.returncode})"
        )

        streamlink_process = None

        return False

    log("[SYSTEM] Streamlink process is alive.")

    # --------------------------------------------------------
    # FFMPEG
    # --------------------------------------------------------

    ffmpeg_command = build_ffmpeg_command()

    log("[SYSTEM] Starting FFmpeg...")
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

    # Parent no longer needs the pipe.

    try:

        if streamlink_process.stdout:
            streamlink_process.stdout.close()

    except Exception:
        pass

    time.sleep(3)

    if ffmpeg_process.poll() is not None:

        log(
            "[ERROR] FFmpeg exited "
            f"(code {ffmpeg_process.returncode})"
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

        time.sleep(2)

        # ----------------------------------------------------
        # STREAMLINK
        # ----------------------------------------------------

        if streamlink_process is None:

            log("[SYSTEM] Streamlink missing.")

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

        # ----------------------------------------------------
        # FFMPEG
        # ----------------------------------------------------

        if ffmpeg_process is None:

            log("[SYSTEM] FFmpeg missing.")

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

    log("")
    log("============================================================")
    log("       YouTube 24/7 -> Restream -> TikTok")
    log("============================================================")

    log(
        f"YouTube        : {YOUTUBE_URL}"
    )

    log("Destination    : Restream")
    log("Extractor      : Streamlink")
    log("Video          : COPY")
    log("Video Encode   : OFF")
    log("Crop           : OFF")
    log("Resize         : OFF")
    log("FPS Convert    : OFF")
    log(
        f"Audio          : AAC {AUDIO_BITRATE}"
    )
    log("Memory Mode    : LOW")
    log("Auto-Reconnect : ON")
    log("============================================================")

    prepare_cookies()

    log("[SYSTEM] Starting 24/7 relay...")

    failure_count = 0

    while not shutdown_requested:

        success = start_session()

        if shutdown_requested:
            break

        if success:

            failure_count = 0

            monitor_session()

        else:

            failure_count += 1

        if shutdown_requested:
            break

        stop_all()

        # ----------------------------------------------------
        # BACKOFF
        # ----------------------------------------------------

        delay = min(
            RECONNECT_DELAY * (2 ** min(failure_count, 4)),
            60
        )

        log("")
        log("============================================================")
        log("[SYSTEM] Stream ended or connection lost.")
        log(
            f"[SYSTEM] Reconnecting in {delay} seconds..."
        )
        log("============================================================")

        time.sleep(delay)

    log("[SYSTEM] Relay stopped.")

    stop_all()


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

        log("")
        log("============================================================")
        log("[SYSTEM] FATAL ERROR")
        log(
            f"[SYSTEM] {type(e).__name__}: {e}"
        )
        log("============================================================")

        stop_all()

        time.sleep(5)

    finally:

        stop_all()

        if cookies_file:

            try:
                os.remove(cookies_file)
            except Exception:
                pass
