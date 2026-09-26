import os
import subprocess
import time
import signal
import sys


# =========================================================
# SETTINGS
# =========================================================

YOUTUBE_URL = "https://www.youtube.com/live/7DHNbnPMNiM"

# ضع المفتاح في Railway Variables باسم:
# RESTREAM_STREAM_KEY
RESTREAM_STREAM_KEY = os.environ.get("RESTREAM_STREAM_KEY")

if not RESTREAM_STREAM_KEY:
    raise RuntimeError("RESTREAM_STREAM_KEY is not set.")

RESTREAM_RTMP = (
    f"rtmp://live.restream.io/live/{RESTREAM_STREAM_KEY}"
)

# ملف كوكيز YouTube
COOKIES_FILE = os.environ.get(
    "YOUTUBE_COOKIES_FILE",
    "YOUTUBE_COOKIES"
)

# ---------------------------------------------------------
# RECONNECT
# ---------------------------------------------------------

RECONNECT_DELAY = 10

# ---------------------------------------------------------
# STREAMLINK
# ---------------------------------------------------------

HLS_LIVE_EDGE = 3
RINGBUFFER_SIZE = "256M"

RETRY_STREAMS = 5
RETRY_MAX = 0

STREAM_SEGMENT_ATTEMPTS = 8
STREAM_SEGMENT_TIMEOUT = 20
STREAM_TIMEOUT = 60


# =========================================================
# DISPLAY
# =========================================================

print("=" * 60)
print("          YouTube 24/7 -> Restream -> TikTok")
print("=" * 60)

print(f"YouTube       : {YOUTUBE_URL}")
print("Destination   : Restream")
print("Video         : COPY")
print("Video Encode  : OFF")
print("Crop          : OFF")
print("Resize        : OFF")
print("FPS Convert   : OFF")
print("Audio         : AAC 128k")
print("Auto-Reconnect: ON")
print("Source Retry  : UNLIMITED")
print("Status        : STARTING")
print("=" * 60)


# =========================================================
# PROCESS CONTROL
# =========================================================

streamlink_process = None
ffmpeg_process = None


def stop_process(process, name="process"):

    if process is None:
        return

    try:

        if process.poll() is None:

            print(f"[SYSTEM] Stopping {name}...")

            process.terminate()

            try:
                process.wait(timeout=8)

            except subprocess.TimeoutExpired:

                print(f"[SYSTEM] Killing {name}...")

                process.kill()
                process.wait(timeout=5)

    except Exception as e:

        print(
            f"[WARNING] Could not stop {name}: "
            f"{type(e).__name__}: {e}"
        )


def cleanup():

    global streamlink_process
    global ffmpeg_process

    stop_process(ffmpeg_process, "FFmpeg")
    stop_process(streamlink_process, "Streamlink")

    ffmpeg_process = None
    streamlink_process = None


def signal_handler(sig, frame):

    print("\n[SYSTEM] Shutdown requested...")

    cleanup()

    sys.exit(0)


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


# =========================================================
# STREAMLINK COMMAND
# =========================================================

def build_streamlink_command():

    command = [

        "streamlink",

        # Output stream to stdout
        "--stdout",

        # -------------------------------------------------
        # HLS stability
        # -------------------------------------------------

        "--hls-live-edge",
        str(HLS_LIVE_EDGE),

        "--ringbuffer-size",
        RINGBUFFER_SIZE,

        # -------------------------------------------------
        # Keep waiting for the YouTube LIVE
        # -------------------------------------------------

        "--retry-streams",
        str(RETRY_STREAMS),

        "--retry-max",
        str(RETRY_MAX),

        "--retry-open",
        "5",

        # -------------------------------------------------
        # Segment stability
        # -------------------------------------------------

        "--stream-segment-attempts",
        str(STREAM_SEGMENT_ATTEMPTS),

        "--stream-segment-timeout",
        str(STREAM_SEGMENT_TIMEOUT),

        "--stream-timeout",
        str(STREAM_TIMEOUT),

        # -------------------------------------------------
        # HTTP timeout
        # -------------------------------------------------

        "--http-timeout",
        "30",
    ]

    # =====================================================
    # YOUTUBE COOKIES
    # =====================================================

    if os.path.isfile(COOKIES_FILE):

        print(
            f"[SYSTEM] YouTube cookies enabled: "
            f"{COOKIES_FILE}"
        )

        command += [
            "--http-cookies-file",
            COOKIES_FILE
        ]

    else:

        print(
            "[WARNING] YouTube cookies file not found."
        )

        print(
            "[WARNING] Continuing without cookies."
        )

    # =====================================================
    # URL + QUALITY
    # =====================================================

    command += [

        YOUTUBE_URL,

        "best"
    ]

    return command


# =========================================================
# FFMPEG COMMAND
# =========================================================

def build_ffmpeg_command():

    return [

        "ffmpeg",

        "-hide_banner",

        "-loglevel",
        "warning",

        "-stats",

        # -------------------------------------------------
        # INPUT BUFFER
        # -------------------------------------------------

        "-thread_queue_size",
        "1024",

        # -------------------------------------------------
        # TIMESTAMP HANDLING
        # -------------------------------------------------

        "-fflags",
        "+genpts+discardcorrupt",

        "-err_detect",
        "ignore_err",

        # -------------------------------------------------
        # INPUT
        # -------------------------------------------------

        "-i",
        "-",

        # =================================================
        # VIDEO
        # COPY - NO ENCODING
        # =================================================

        "-map",
        "0:v:0",

        "-c:v",
        "copy",

        # =================================================
        # AUDIO
        # AAC ENCODE
        # =================================================

        "-map",
        "0:a:0?",

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        "-ar",
        "44100",

        "-ac",
        "2",

        # -------------------------------------------------
        # AUDIO TIMESTAMP CORRECTION
        # -------------------------------------------------

        "-af",
        "aresample="
        "async=1000:"
        "min_hard_comp=0.100000:"
        "first_pts=0",

        # -------------------------------------------------
        # FLV
        # -------------------------------------------------

        "-flvflags",
        "no_duration_filesize",

        "-f",
        "flv",

        RESTREAM_RTMP
    ]


# =========================================================
# START STREAM
# =========================================================

def start_stream():

    global streamlink_process
    global ffmpeg_process

    streamlink_command = build_streamlink_command()
    ffmpeg_command = build_ffmpeg_command()

    print("\n[SYSTEM] Starting Streamlink...")
    print("[SYSTEM] Waiting for YouTube LIVE...")

    streamlink_process = subprocess.Popen(

        streamlink_command,

        stdout=subprocess.PIPE,

        stderr=sys.stderr,

        bufsize=0
    )

    # -----------------------------------------------------
    # Give Streamlink a moment to initialize
    # -----------------------------------------------------

    time.sleep(2)

    if streamlink_process.poll() is not None:

        print(
            "[ERROR] Streamlink stopped "
            "before FFmpeg started."
        )

        return False

    print("[SYSTEM] YouTube source process active.")
    print("[SYSTEM] Starting FFmpeg...")

    print("[SYSTEM] Video: COPY")
    print("[SYSTEM] Video Encode: OFF")

    print("[SYSTEM] Audio: AAC 128k")

    print("[SYSTEM] Sending stream to Restream...")

    ffmpeg_process = subprocess.Popen(

        ffmpeg_command,

        stdin=streamlink_process.stdout,

        stdout=subprocess.DEVNULL,

        stderr=sys.stderr
    )

    # -----------------------------------------------------
    # Parent must close its copy of stdout
    # -----------------------------------------------------

    if streamlink_process.stdout:

        streamlink_process.stdout.close()

    print("[SYSTEM] Stream is RUNNING.")

    return True


# =========================================================
# MONITOR
# =========================================================

def monitor_stream():

    global streamlink_process
    global ffmpeg_process

    while True:

        # -------------------------------------------------
        # FFmpeg status
        # -------------------------------------------------

        if ffmpeg_process is None:

            return False

        ffmpeg_status = ffmpeg_process.poll()

        if ffmpeg_status is not None:

            print(
                f"[SYSTEM] FFmpeg stopped "
                f"(exit code: {ffmpeg_status})"
            )

            return False

        # -------------------------------------------------
        # Streamlink status
        # -------------------------------------------------

        if streamlink_process is None:

            return False

        streamlink_status = streamlink_process.poll()

        if streamlink_status is not None:

            print(
                f"[SYSTEM] Streamlink stopped "
                f"(exit code: {streamlink_status})"
            )

            return False

        # -------------------------------------------------
        # Everything is still running
        # -------------------------------------------------

        time.sleep(5)


# =========================================================
# MAIN LOOP
# =========================================================

def run_stream():

    while True:

        try:

            cleanup()

            print("\n")
            print("=" * 60)
            print("             STARTING STREAM SESSION")
            print("=" * 60)

            started = start_stream()

            if not started:

                cleanup()

                print(
                    f"[SYSTEM] Retry in "
                    f"{RECONNECT_DELAY} seconds..."
                )

                time.sleep(RECONNECT_DELAY)

                continue

            # -------------------------------------------------
            # Monitor until one process stops
            # -------------------------------------------------

            monitor_stream()

        except Exception as e:

            print(
                f"[ERROR] {type(e).__name__}: {e}"
            )

        finally:

            cleanup()

        print("\n")
        print("=" * 60)
        print("[SYSTEM] Stream ended or connection lost.")
        print(
            f"[SYSTEM] Auto-reconnect in "
            f"{RECONNECT_DELAY} seconds..."
        )
        print("=" * 60)

        time.sleep(RECONNECT_DELAY)


# =========================================================
# START
# =========================================================

try:

    print("[SYSTEM] Starting 24/7 relay...")

    run_stream()

except KeyboardInterrupt:

    print("\n[SYSTEM] Keyboard interrupt.")

finally:

    cleanup()
