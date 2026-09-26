import os
import subprocess
import time
import signal
import sys


# =========================================================
# SETTINGS
# =========================================================

YOUTUBE_URL = "https://www.youtube.com/live/7DHNbnPMNiM"

RESTREAM_STREAM_KEY = (
    "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9"
)

RESTREAM_RTMP = (
    "rtmp://live.restream.io/live/"
    + RESTREAM_STREAM_KEY
)

# الوقت بين محاولات إعادة الاتصال
RECONNECT_DELAY = 5

# انتظار إضافي بعد سقوط Streamlink بسبب مشكلة في مصدر YouTube
SOURCE_RETRY_DELAY = 5

# وقت السماح لـ Streamlink بالبدء قبل تشغيل FFmpeg
STREAM_START_DELAY = 4


# =========================================================
# DISPLAY
# =========================================================

print("=" * 60)
print("       YouTube 24/7 -> Restream -> TikTok")
print("=" * 60)

print(f"YouTube        : {YOUTUBE_URL}")
print("Destination    : Restream")
print("Cookies        : OFF")
print("Video          : COPY")
print("Video Encode   : OFF")
print("Crop           : OFF")
print("Resize         : OFF")
print("FPS Convert    : OFF")
print("Audio          : AAC 128k")
print("Auto-Reconnect : ON")
print("Status         : STARTING")
print("=" * 60)


# =========================================================
# PROCESS VARIABLES
# =========================================================

streamlink_process = None
ffmpeg_process = None

shutdown_requested = False


# =========================================================
# PROCESS CONTROL
# =========================================================

def stop_process(process, name):

    if process is None:
        return

    try:

        if process.poll() is None:

            print(f"[SYSTEM] Stopping {name}...")

            process.terminate()

            try:

                process.wait(timeout=5)

            except subprocess.TimeoutExpired:

                print(f"[SYSTEM] {name} did not stop. Killing...")

                process.kill()

                try:
                    process.wait(timeout=3)
                except Exception:
                    pass

    except Exception as e:

        print(f"[SYSTEM] Error stopping {name}: {e}")


def cleanup():

    global streamlink_process
    global ffmpeg_process

    stop_process(ffmpeg_process, "FFmpeg")
    stop_process(streamlink_process, "Streamlink")

    ffmpeg_process = None
    streamlink_process = None


# =========================================================
# SIGNAL HANDLER
# =========================================================

def signal_handler(sig, frame):

    global shutdown_requested

    shutdown_requested = True

    print("\n[SYSTEM] Shutdown requested...")

    cleanup()

    sys.exit(0)


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


# =========================================================
# STREAMLINK COMMAND
# =========================================================

def build_streamlink_command():

    return [

        "streamlink",

        "--stdout",

        # -------------------------------------------------
        # HLS
        # -------------------------------------------------

        "--hls-live-edge",
        "2",

        "--ringbuffer-size",
        "512M",

        # -------------------------------------------------
        # RETRY
        # -------------------------------------------------

        "--retry-streams",
        "10",

        "--retry-max",
        "50",

        "--stream-segment-attempts",
        "10",

        "--stream-segment-timeout",
        "30",

        "--stream-timeout",
        "60",

        # -------------------------------------------------
        # SOURCE
        # -------------------------------------------------

        YOUTUBE_URL,

        # Best available quality
        "best"
    ]


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
        "2048",

        # -------------------------------------------------
        # TIMESTAMP / CORRUPTED PACKETS
        # -------------------------------------------------

        "-fflags",
        "+genpts+discardcorrupt",

        "-err_detect",
        "ignore_err",

        # -------------------------------------------------
        # INPUT FROM STREAMLINK
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
        # AAC ENCODE ONLY
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

        "-af",
        "aresample=async=1000:min_hard_comp=0.100000:first_pts=0",

        # =================================================
        # OUTPUT TIMING
        # =================================================

        "-fps_mode",
        "passthrough",

        "-flush_packets",
        "1",

        # =================================================
        # FLV / RTMP
        # =================================================

        "-flvflags",
        "no_duration_filesize",

        "-f",
        "flv",

        RESTREAM_RTMP
    ]


# =========================================================
# START STREAMLINK
# =========================================================

def start_streamlink():

    global streamlink_process

    command = build_streamlink_command()

    print("[SYSTEM] Starting Streamlink...")
    print("[SYSTEM] Cookies: OFF")
    print("[SYSTEM] Waiting for YouTube stream data...")

    try:

        streamlink_process = subprocess.Popen(

            command,

            stdout=subprocess.PIPE,

            stderr=sys.stderr,

            bufsize=0
        )

        return True

    except Exception as e:

        print(
            f"[ERROR] Could not start Streamlink: "
            f"{type(e).__name__}: {e}"
        )

       
