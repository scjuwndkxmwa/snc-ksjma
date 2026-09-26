import os
import sys
import time
import signal
import subprocess


# ============================================================
# CONFIG
# ============================================================

YOUTUBE_URL = "https://www.youtube.com/live/7DHNbnPMNiM"

# Restream stream key
RESTREAM_STREAM_KEY = "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9"

# Restream official RTMP ingest
RESTREAM_RTMP = (
    f"rtmp://live.restream.io/live/{RESTREAM_STREAM_KEY}"
)

QUALITY = "best"

RECONNECT_DELAY = 5

# Streamlink stability
RETRY_STREAMS_DELAY = 10
RETRY_MAX = 0

RINGBUFFER_SIZE = "64M"

SEGMENT_ATTEMPTS = 8
SEGMENT_THREADS = 2
SEGMENT_TIMEOUT = 15

STREAM_TIMEOUT = 60

# Audio
AUDIO_BITRATE = "128k"
AUDIO_RATE = "44100"
AUDIO_CHANNELS = "2"


# ============================================================
# PROCESS CONTROL
# ============================================================

streamlink_process = None
ffmpeg_process = None
stopping = False


def log(message):
    print(message, flush=True)


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


def stop_all():
    global streamlink_process
    global ffmpeg_process

    stop_process(ffmpeg_process, "FFmpeg")
    ffmpeg_process = None

    stop_process(streamlink_process, "Streamlink")
    streamlink_process = None


def shutdown(signum=None, frame=None):
    global stopping

    if stopping:
        return

    stopping = True

    log("")
    log("[SYSTEM] Shutdown requested...")

    stop_all()

    log("[SYSTEM] Shutdown complete.")
    sys.exit(0)


signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)


# ============================================================
# DISPLAY
# ============================================================

def print_header():
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


# ============================================================
# STREAMLINK
# ============================================================

def build_streamlink_command():

    command = [
        "streamlink",

        # Do NOT use --no-version-check.
        # Modern Streamlink already has automatic version
        # checking disabled by default.

        "--loglevel",
        "info",

        "--retry-streams",
        str(RETRY_STREAMS_DELAY),

        "--retry-max",
        str(RETRY_MAX),

        "--retry-open",
        "5",

        "--ringbuffer-size",
        RINGBUFFER_SIZE,

        "--stream-segment-attempts",
        str(SEGMENT_ATTEMPTS),

        "--stream-segment-threads",
        str(SEGMENT_THREADS),

        "--stream-segment-timeout",
        str(SEGMENT_TIMEOUT),

        "--stream-timeout",
        str(STREAM_TIMEOUT),

        "--hls-live-edge",
        "3",

        "--hls-playlist-reload-attempts",
        "5",

        "--stdout",

        YOUTUBE_URL,

        QUALITY,
    ]

    return command


# ============================================================
# FFMPEG
# ============================================================

def build_ffmpeg_command():

    command = [
        "ffmpeg",

        "-hide_banner",

        "-loglevel",
        "warning",

        "-stats",

        # Read from Streamlink stdin
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

        # Helps keep audio timestamps sane
        "-af",
        "aresample=async=1000:min_hard_comp=0.100:first_pts=0",

        # ----------------------------------------------------
        # TIMESTAMP / CORRUPTED PACKETS
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

        "-f",
        "flv",

        RESTREAM_RTMP,
    ]

    return command


# ============================================================
# START SESSION
# ============================================================

def start_session():

    global streamlink_process
    global ffmpeg_process

    stop_all()

    log("============================================================")
    log("[SYSTEM] Starting relay session")
    log("============================================================")

    # --------------------------------------------------------
    # START STREAMLINK
    # --------------------------------------------------------

    streamlink_cmd = build_streamlink_command()

    log("[SYSTEM] Starting Streamlink...")
    log("[SYSTEM] Cookies: OFF")
    log(f"[SYSTEM] Quality: {QUALITY.upper()}")
    log("[SYSTEM] Video source will be copied.")
    log("[SYSTEM] Waiting for YouTube stream data...")

    streamlink_process = subprocess.Popen(
        streamlink_cmd,
        stdout=subprocess.PIPE,
        stderr=None,
        bufsize=0,
    )

    time.sleep(1)

    if streamlink_process.poll() is not None:
        code = streamlink_process.returncode

        log(
            f"[SYSTEM] Streamlink exited immediately "
            f"(exit code: {code})."
        )

        return False

    log("[SYSTEM] Streamlink process is alive.")

    # --------------------------------------------------------
    # START FFMPEG
    # --------------------------------------------------------

    ffmpeg_cmd = build_ffmpeg_command()

    log("[SYSTEM] Starting FFmpeg pipeline...")
    log("[SYSTEM] Starting FFmpeg...")
    log("[SYSTEM] Video: COPY")
    log("[SYSTEM] Video Encode: OFF")
    log(f"[SYSTEM] Audio: AAC {AUDIO_BITRATE}")
    log("[SYSTEM] Sending stream to Restream...")

    ffmpeg_process = subprocess.Popen(
        ffmpeg_cmd,
        stdin=streamlink_process.stdout,
        stdout=subprocess.DEVNULL,
        stderr=None,
        bufsize=0,
    )

    # Important:
    # Once stdout is handed to FFmpeg, Streamlink must not keep
    # another reference to it in Python.
    if streamlink_process.stdout:
        streamlink_process.stdout.close()

    time.sleep(2)

    if ffmpeg_process.poll() is not None:
        code = ffmpeg_process.returncode

        log(
            f"[SYSTEM] FFmpeg stopped immediately "
            f"(exit code: {code})."
        )

        stop_all()
        return False

    log("[SYSTEM] Stream is RUNNING.")

    return True


# ============================================================
# MAIN LOOP
# ============================================================

def main():

    global stopping

    print_header()

    log("[SYSTEM] Starting 24/7 relay...")
    log("")

    while not stopping:

        success = start_session()

        if not success:

            if stopping:
                break

            log("")
            log(
                f"[SYSTEM] Session failed. "
                f"Retrying in {RECONNECT_DELAY} seconds..."
            )

            stop_all()

            time.sleep(RECONNECT_DELAY)
            continue

        # ----------------------------------------------------
        # MONITOR BOTH PROCESSES
        # ----------------------------------------------------

        while not stopping:

            time.sleep(2)

            if streamlink_process is None:
                break

            if ffmpeg_process is None:
                break

            streamlink_code = streamlink_process.poll()
            ffmpeg_code = ffmpeg_process.poll()

            # Streamlink died
            if streamlink_code is not None:

                log("")
                log(
                    "[SYSTEM] Streamlink stopped "
                    f"(exit code: {streamlink_code})."
                )

                stop_process(ffmpeg_process, "FFmpeg")

                ffmpeg_process = None
                streamlink_process = None

                break

            # FFmpeg died
            if ffmpeg_code is not None:

                log("")
                log(
                    "[SYSTEM] FFmpeg stopped "
                    f"(exit code: {ffmpeg_code})."
                )

                stop_process(streamlink_process, "Streamlink")

                streamlink_process = None
                ffmpeg_process = None

                break

        if stopping:
            break

        # ----------------------------------------------------
        # RECONNECT
        # ----------------------------------------------------

        log("")
        log("============================================================")
        log(
            f"[SYSTEM] Reconnecting in "
            f"{RECONNECT_DELAY} seconds..."
        )
        log("============================================================")

        stop_all()

        time.sleep(RECONNECT_DELAY)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:
        main()

    except KeyboardInterrupt:
        shutdown()

    except Exception as e:
        log("")
        log("============================================================")
        log("[SYSTEM] FATAL ERROR")
        log(f"[SYSTEM] {type(e).__name__}: {e}")
        log("============================================================")

        stop_all()

        time.sleep(RECONNECT_DELAY)

        # Keep container alive and retry instead of dying
        try:
            main()
        except Exception:
            shutdown()
