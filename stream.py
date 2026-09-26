import os
import subprocess
import time
import signal
import sys

# ============================================================
# YouTube LIVE 24/7 -> Restream -> TikTok
# ============================================================

YOUTUBE_URL = "https://www.youtube.com/watch?v=Dkhgp_G81GQ"

RESTREAM_RTMP = "rtmp://live.restream.io/live"
RESTREAM_KEY = "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9"

RESTREAM_URL = f"{RESTREAM_RTMP}/{RESTREAM_KEY}"

RECONNECT_DELAY = 10


# ============================================================
# Streamlink
# ============================================================

STREAMLINK_CMD = [
    "streamlink",

    "--hls-live-edge", "3",

    "--retry-streams", "5",
    "--retry-max", "0",

    "--retry-open", "5",

    "--stream-segment-attempts", "5",
    "--stream-segment-timeout", "15",
    "--stream-timeout", "60",

    "--stream-segment-threads", "2",

    "--stdout",

    YOUTUBE_URL,
    "best"
]


# ============================================================
# FFmpeg
# ============================================================

FFMPEG_CMD = [
    "ffmpeg",

    "-hide_banner",
    "-loglevel", "warning",
    "-stats",

    # Generate stable timestamps and ignore corrupted packets
    "-fflags", "+genpts+discardcorrupt",
    "-err_detect", "ignore_err",

    "-thread_queue_size", "1024",

    # Input from Streamlink
    "-i", "-",

    # ========================================================
    # VIDEO - COPY
    # ========================================================

    "-map", "0:v:0",
    "-c:v", "copy",

    # ========================================================
    # AUDIO - AAC
    # ========================================================

    "-map", "0:a:0?",
    "-c:a", "aac",
    "-b:a", "128k",
    "-ar", "44100",
    "-ac", "2",

    "-af",
    "aresample=async=1000:min_hard_comp=0.100000:first_pts=0",

    # ========================================================
    # Keep original video timing
    # ========================================================

    "-fps_mode", "passthrough",

    "-flush_packets", "1",

    "-flvflags", "no_duration_filesize",

    # ========================================================
    # Output
    # ========================================================

    "-f", "flv",

    RESTREAM_URL
]


streamlink_process = None
ffmpeg_process = None


# ============================================================
# Process control
# ============================================================

def stop_process(process):
    if process is not None and process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=5)

        except Exception:
            try:
                process.kill()
                process.wait(timeout=3)
            except Exception:
                pass


def cleanup():
    global streamlink_process
    global ffmpeg_process

    stop_process(ffmpeg_process)
    stop_process(streamlink_process)

    ffmpeg_process = None
    streamlink_process = None


def signal_handler(sig, frame):
    print("\n[SYSTEM] Shutdown requested...")
    cleanup()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ============================================================
# Startup
# ============================================================

print("==============================================")
print("       YouTube 24/7 -> Restream -> TikTok")
print("==============================================")
print(f"YouTube     : {YOUTUBE_URL}")
print("Video       : COPY")
print("Video Encode: OFF")
print("Crop        : OFF")
print("Resize      : OFF")
print("FPS Convert : OFF")
print("Audio       : AAC 128k")
print("Destination : Restream")
print("Auto-Reconnect: ON")
print("Status      : RUNNING")
print("==============================================\n")


# ============================================================
# Main loop
# ============================================================

while True:

    try:

        cleanup()

        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            "Starting YouTube LIVE connection..."
        )

        # ----------------------------------------------------
        # Start Streamlink
        # ----------------------------------------------------

        streamlink_process = subprocess.Popen(
            STREAMLINK_CMD,
            stdout=subprocess.PIPE,
            stderr=None,
            bufsize=0
        )

        time.sleep(5)

        # ----------------------------------------------------
        # Check Streamlink
        # ----------------------------------------------------

        if streamlink_process.poll() is not None:

            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                "YouTube stream unavailable."
            )

            cleanup()

            print(
                f"[SYSTEM] Retrying in "
                f"{RECONNECT_DELAY} seconds..."
            )

            time.sleep(RECONNECT_DELAY)
            continue

        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            "YouTube LIVE connected!"
        )

        print("[SYSTEM] Starting FFmpeg...")
        print("[SYSTEM] Video: COPY")
        print("[SYSTEM] Audio: AAC 128k")
        print("[SYSTEM] Sending stream to Restream...")
        print("[SYSTEM] TikTok destination active.\n")

        # ----------------------------------------------------
        # Start FFmpeg
        # ----------------------------------------------------

        ffmpeg_process = subprocess.Popen(
            FFMPEG_CMD,
            stdin=streamlink_process.stdout,
            stdout=None,
            stderr=None,
            bufsize=0
        )

        streamlink_process.stdout.close()

        # ----------------------------------------------------
        # Wait for FFmpeg
        # ----------------------------------------------------

        ffmpeg_return = ffmpeg_process.wait()

        print(
            f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"FFmpeg stopped. Exit code: {ffmpeg_return}"
        )

    except KeyboardInterrupt:

        print("\n[SYSTEM] Stopping...")
        cleanup()
        break

    except Exception as e:

        print(
            f"\n[ERROR] Unexpected error: {e}"
        )

    finally:

        cleanup()

    print("==============================================")
    print("YouTube connection ended.")
    print("Stopping current processes...")
    print("==============================================")

    print(
        f"[SYSTEM] Reconnecting in "
        f"{RECONNECT_DELAY} seconds...\n"
    )

    time.sleep(RECONNECT_DELAY)
