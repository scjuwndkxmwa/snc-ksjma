import os
import subprocess
import time
import signal
import sys


# =========================================================
# CONFIG
# =========================================================

YOUTUBE_URL = "https://www.youtube.com/@Yasseraldosry/live"
YOUTUBE_CHANNEL = "@Yasseraldosry"

RESTREAM_RTMP = "rtmp://live.restream.io/live"
RESTREAM_STREAM_KEY = "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9"

RESTREAM_URL = (
    RESTREAM_RTMP + "/" + RESTREAM_STREAM_KEY
)

RESTART_DELAY = 5


# =========================================================
# STREAMLINK
# =========================================================

STREAMLINK_CMD = [
    "streamlink",

    "--loglevel", "info",

    "--http-header",
    "User-Agent=Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/141.0.0.0 Safari/537.36",

    "--http-header",
    "Referer=https://www.youtube.com/",

    "--hls-live-edge", "3",

    # Keep waiting for the next LIVE
    "--retry-streams", "5",
    "--retry-max", "0",
    "--retry-open", "5",

    # HLS segment stability
    "--stream-segment-attempts", "8",
    "--stream-segment-timeout", "20",
    "--stream-timeout", "60",

    "--ringbuffer-size", "512M",

    "--stdout",

    YOUTUBE_URL,

    "best"
]


# =========================================================
# FFMPEG
# =========================================================

FFMPEG_CMD = [
    "ffmpeg",

    "-hide_banner",
    "-loglevel", "warning",
    "-stats",

    # INPUT
    "-thread_queue_size", "2048",

    "-dts_delta_threshold", "1",

    "-fflags",
    "+genpts+discardcorrupt",

    "-err_detect",
    "ignore_err",

    "-i", "-",

    # VIDEO
    "-map", "0:v:0",
    "-c:v", "copy",

    "-fps_mode", "passthrough",

    # AUDIO
    "-map", "0:a:0?",

    "-c:a", "aac",
    "-b:a", "128k",
    "-ar", "44100",
    "-ac", "2",

    "-af",
    "aresample=async=1000:"
    "min_hard_comp=0.100000:"
    "first_pts=0",

    # OUTPUT
    "-flush_packets", "1",

    "-flvflags",
    "no_duration_filesize",

    "-f",
    "flv",

    RESTREAM_URL
]


# =========================================================
# PROCESSES
# =========================================================

streamlink_process = None
ffmpeg_process = None
stopping = False


# =========================================================
# STOP PROCESS
# =========================================================

def stop_process(process, name):

    if process is None:
        return

    if process.poll() is not None:
        return

    print(f"[SYSTEM] Stopping {name}...")

    try:
        process.terminate()
        process.wait(timeout=5)

    except subprocess.TimeoutExpired:

        print(
            f"[SYSTEM] {name} did not stop. "
            "Killing..."
        )

        try:
            process.kill()
            process.wait(timeout=3)
        except Exception:
            pass

    except Exception as e:

        print(
            f"[SYSTEM] Error stopping "
            f"{name}: {e}"
        )

        try:
            process.kill()
        except Exception:
            pass


# =========================================================
# CLEANUP
# =========================================================

def cleanup():

    global streamlink_process
    global ffmpeg_process

    stop_process(
        ffmpeg_process,
        "FFmpeg"
    )

    stop_process(
        streamlink_process,
        "Streamlink"
    )

    ffmpeg_process = None
    streamlink_process = None


# =========================================================
# SIGNAL HANDLER
# =========================================================

def signal_handler(sig, frame):

    global stopping

    stopping = True

    print()
    print("==============================================")
    print("[SYSTEM] Shutdown signal received.")
    print("[SYSTEM] Stopping...")
    print("==============================================")

    cleanup()

    sys.exit(0)


signal.signal(
    signal.SIGINT,
    signal_handler
)

signal.signal(
    signal.SIGTERM,
    signal_handler
)


# =========================================================
# STARTUP
# =========================================================

print("==============================================")
print("       YouTube -> Restream -> TikTok")
print("==============================================")
print(f"YouTube     : {YOUTUBE_CHANNEL}")
print("Auto Detect : ON")
print("Video       : COPY")
print("Video Encode: OFF")
print("Crop        : OFF")
print("Resize      : OFF")
print("FPS Convert : OFF")
print("Audio       : AAC 128k")
print("Destination : Restream")
print("Auto Retry  : ON")
print("Next LIVE   : AUTO")
print("Status      : RUNNING")
print("==============================================")
print()


# =========================================================
# MAIN LOOP
# =========================================================

while not stopping:

    try:

        cleanup()

        print("==============================================")
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            "Checking YouTube LIVE..."
        )
        print("==============================================")

        print(
            "[SYSTEM] Waiting for "
            "YouTube LIVE..."
        )

        # =================================================
        # START STREAMLINK
        # =================================================

        streamlink_process = subprocess.Popen(
            STREAMLINK_CMD,
            stdout=subprocess.PIPE,
            stderr=None,
            bufsize=0
        )

        # =================================================
        # START FFMPEG
        # =================================================

        print("[SYSTEM] Starting FFmpeg...")

        ffmpeg_process = subprocess.Popen(
            FFMPEG_CMD,
            stdin=streamlink_process.stdout,
            stdout=None,
            stderr=None,
            bufsize=0
        )

        streamlink_process.stdout.close()

        print("[SYSTEM] FFmpeg started.")
        print(
            "[SYSTEM] Sending YouTube LIVE "
            "to Restream..."
        )

        # =================================================
        # MONITOR
        # =================================================

        while not stopping:

            ffmpeg_return = ffmpeg_process.poll()
            streamlink_return = streamlink_process.poll()

            if ffmpeg_return is not None:

                print()
                print(
                    "=============================================="
                )
                print(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                    f"FFmpeg stopped. "
                    f"Exit code: {ffmpeg_return}"
                )
                print(
                    "=============================================="
                )

                break

            if streamlink_return is not None:

                print()
                print(
                    "=============================================="
                )
                print(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                    f"Streamlink stopped. "
                    f"Exit code: {streamlink_return}"
                )
                print(
                    "=============================================="
                )

                break

            time.sleep(1)

        if stopping:
            break

        print()
        print(
            "=============================================="
        )
        print(
            "YouTube LIVE ended "
            "or connection was lost."
        )
        print(
            "Stopping current session..."
        )
        print(
            "=============================================="
        )

        cleanup()

        print(
            f"[SYSTEM] Waiting {RESTART_DELAY} "
            "seconds..."
        )

        time.sleep(RESTART_DELAY)

        print(
            "[SYSTEM] Searching for "
            "the next YouTube LIVE..."
        )

    except KeyboardInterrupt:

        stopping = True

        print(
            "\n[SYSTEM] Stopping..."
        )

        cleanup()

        break

    except BrokenPipeError:

        print(
            "\n[SYSTEM] Broken pipe detected."
        )

        cleanup()

        if not stopping:
            time.sleep(RESTART_DELAY)

    except OSError as e:

        print(
            f"\n[SYSTEM] OS error: {e}"
        )

        cleanup()

        if not stopping:
            time.sleep(RESTART_DELAY)

    except Exception as e:

        print(
            f"\n[SYSTEM] Unexpected error: {e}"
        )

        cleanup()

        if not stopping:
            time.sleep(RESTART_DELAY)

    finally:

        if not stopping:
            cleanup()


print("\n[SYSTEM] Relay stopped.")
