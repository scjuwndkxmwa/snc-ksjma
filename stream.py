import os
import sys
import time
import signal
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

RECONNECT_DELAY = 5

# ============================================================
# STREAMLINK SETTINGS
# ============================================================

RINGBUFFER_SIZE = "64M"

HLS_LIVE_EDGE = "3"

RETRY_STREAMS = "10"
RETRY_MAX = "0"

SEGMENT_ATTEMPTS = "8"
SEGMENT_THREADS = "2"
SEGMENT_TIMEOUT = "15"

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

    # Railway may send SIGTERM while replacing a deployment.
    # Do not call sys.exit() here.
    shutdown_requested = True

    log("")
    log("[SYSTEM] Shutdown signal received.")


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


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

        log(f"[SYSTEM] Error stopping {name}: {e}")


# ============================================================
# STOP EVERYTHING
# ============================================================

def stop_all():

    global streamlink_process
    global ffmpeg_process

    if ffmpeg_process is not None:
        stop_process(ffmpeg_process, "FFmpeg")

    ffmpeg_process = None

    if streamlink_process is not None:
        stop_process(streamlink_process, "Streamlink")

    streamlink_process = None


# ============================================================
# STREAMLINK COMMAND
# ============================================================

def build_streamlink_command():

    return [
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

        "--stdout",

        YOUTUBE_URL,

        QUALITY
    ]


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

        "-thread_queue_size",
        "1024",

        "-i",
        "-",

        # ====================================================
        # VIDEO COPY
        # ====================================================

        "-map",
        "0:v:0",

        "-c:v",
        "copy",

        # ====================================================
        # AUDIO AAC
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

    # --------------------------------------------------------
    # STREAMLINK
    # --------------------------------------------------------

    streamlink_command = build_streamlink_command()

    log("[SYSTEM] Starting Streamlink...")
    log("[SYSTEM] Cookies: OFF")
    log(f"[SYSTEM] Quality: {QUALITY.upper()}")
    log("[SYSTEM] Video source: COPY")
    log("[SYSTEM] Waiting for YouTube stream data...")

    try:

        streamlink_process = subprocess.Popen(
            streamlink_command,
            stdout=subprocess.PIPE,
            stderr=None,
            bufsize=0
        )

    except Exception as e:

        log(f"[ERROR] Could not start Streamlink: {e}")

        streamlink_process = None

        return False

    time.sleep(2)

    if streamlink_process.poll() is not None:

        code = streamlink_process.returncode

        log(
            f"[ERROR] Streamlink exited immediately "
            f"(exit code: {code})."
        )

        streamlink_process = None

        return False

    log("[SYSTEM] Streamlink process is alive.")

    # --------------------------------------------------------
    # FFMPEG
    # --------------------------------------------------------

    ffmpeg_command = build_ffmpeg_command()

    log("[SYSTEM] Starting FFmpeg pipeline...")
    log("[SYSTEM] Starting FFmpeg...")
    log("[SYSTEM] Video: COPY")
    log("[SYSTEM] Video Encode: OFF")
    log(f"[SYSTEM] Audio: AAC {AUDIO_BITRATE}")
    log("[SYSTEM] Sending stream to Restream...")

    try:

        ffmpeg_process = subprocess.Popen(
            ffmpeg_command,
            stdin=streamlink_process.stdout,
            stdout=subprocess.DEVNULL,
            stderr=None,
            bufsize=0
        )

    except Exception as e:

        log(f"[ERROR] Could not start FFmpeg: {e}")

        stop_all()

        return False

    # Parent no longer needs this descriptor.
    try:

        if streamlink_process.stdout:
            streamlink_process.stdout.close()

    except Exception:
        pass

    time.sleep(3)

    # --------------------------------------------------------
    # CHECK FFMPEG
    # --------------------------------------------------------

    if ffmpeg_process.poll() is not None:

        code = ffmpeg_process.returncode

        log(
            f"[ERROR] FFmpeg exited immediately "
            f"(exit code: {code})."
        )

        stop_all()

        return False

    log("[SYSTEM] YouTube stream detected.")
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

        # ----------------------------------------------------
        # STREAMLINK
        # ----------------------------------------------------

        if streamlink_process is None:

            log("[SYSTEM] Streamlink process missing.")

            return False

        streamlink_code = streamlink_process.poll()

        if streamlink_code is not None:

            log("")
            log(
                "[SYSTEM] Streamlink stopped "
                f"(exit code: {streamlink_code})."
            )

            return False

        # ----------------------------------------------------
        # FFMPEG
        # ----------------------------------------------------

        if ffmpeg_process is None:

            log("[SYSTEM] FFmpeg process missing.")

            return False

        ffmpeg_code = ffmpeg_process.poll()

        if ffmpeg_code is not None:

            log("")
            log(
                "[SYSTEM] FFmpeg stopped "
                f"(exit code: {ffmpeg_code})."
            )

            return False

        # ----------------------------------------------------
        # HEARTBEAT
        # ----------------------------------------------------

        if time.time() - last_status >= 60:

            log("[SYSTEM] Relay is still RUNNING.")
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
    log(f"YouTube        : {YOUTUBE_URL}")
    log("Destination    : Restream")
    log("Cookies        : OFF")
    log("Video          : COPY")
    log("Video Encode   : OFF")
    log("Crop           : OFF")
    log("Resize         : OFF")
    log("FPS Convert    : OFF")
    log(f"Audio          : AAC {AUDIO_BITRATE}")
    log("Auto-Reconnect : ON")
    log("Status         : STARTING")
    log("============================================================")

    log("[SYSTEM] Starting 24/7 relay...")

    while not shutdown_requested:

        # ----------------------------------------------------
        # START
        # ----------------------------------------------------

        success = start_session()

        if shutdown_requested:
            break

        if not success:

            log("")
            log(
                f"[SYSTEM] Starting/reconnecting in "
                f"{RECONNECT_DELAY} seconds..."
            )

            stop_all()

            time.sleep(RECONNECT_DELAY)

            continue

        # ----------------------------------------------------
        # MONITOR
        # ----------------------------------------------------

        monitor_ok = monitor_session()

        if shutdown_requested:
            break

        # ----------------------------------------------------
        # RECONNECT
        # ----------------------------------------------------

        log("")
        log("============================================================")
        log("[SYSTEM] Relay session ended.")
        log(
            f"[SYSTEM] Reconnecting in "
            f"{RECONNECT_DELAY} seconds..."
        )
        log("============================================================")

        stop_all()

        time.sleep(RECONNECT_DELAY)

    # --------------------------------------------------------
    # ONLY REACHED WHEN RAILWAY ACTUALLY TERMINATES PROCESS
    # --------------------------------------------------------

    log("[SYSTEM] Stopping processes...")
    stop_all()

    log("[SYSTEM] Process terminated by platform.")


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        shutdown_requested = True

        log("[SYSTEM] Keyboard interrupt.")

        stop_all()

    except Exception as e:

        log("")
        log("============================================================")
        log("[SYSTEM] UNEXPECTED ERROR")
        log(f"[SYSTEM] {type(e).__name__}: {e}")
        log("============================================================")

        stop_all()

        # Keep the container alive and retry.
        while True:

            try:

                if shutdown_requested:
                    break

                log(
                    f"[SYSTEM] Recovering in "
                    f"{RECONNECT_DELAY} seconds..."
                )

                time.sleep(RECONNECT_DELAY)

                main()

            except KeyboardInterrupt:

                break

            except Exception as retry_error:

                log(
                    f"[SYSTEM] Recovery error: "
                    f"{type(retry_error).__name__}: "
                    f"{retry_error}"
                )

                stop_all()

                time.sleep(RECONNECT_DELAY)

    finally:

        stop_all()
