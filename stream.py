import os
import subprocess
import time
import signal
import sys


# =========================================================
# CONFIG
# =========================================================

YOUTUBE_URL = "https://www.youtube.com/live/7DHNbnPMNiM"

RESTREAM_RTMP = "rtmp://live.restream.io/live"
RESTREAM_STREAM_KEY = "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9"

YOUTUBE_SOURCE = "@Yasseraldosry"

RESTART_DELAY = 5


# =========================================================
# RESTREAM DESTINATION
# =========================================================

RESTREAM_URL = (
    RESTREAM_RTMP
    + "/"
    + RESTREAM_STREAM_KEY
)


# =========================================================
# STREAMLINK
# =========================================================

STREAMLINK_CMD = [
    "streamlink",

    "--loglevel", "info",

    # Browser-like headers
    "--http-header",
    "User-Agent=Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/141.0.0.0 Safari/537.36",

    "--http-header",
    "Referer=https://www.youtube.com/",

    # HLS stability
    "--hls-live-edge", "3",

    # Automatically wait/retry for stream
    "--retry-streams", "5",
    "--retry-max", "0",
    "--retry-open", "5",

    # Segment retry settings
    "--stream-segment-attempts", "8",
    "--stream-segment-timeout", "20",
    "--stream-timeout", "60",

    # Buffer
    "--ringbuffer-size", "512M",

    # Output to FFmpeg
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

    # =====================================================
    # INPUT
    # =====================================================

    "-thread_queue_size", "2048",

    "-dts_delta_threshold", "1",

    "-fflags",
    "+genpts+discardcorrupt",

    "-err_detect",
    "ignore_err",

    "-i",
    "-",

    # =====================================================
    # VIDEO
    # =====================================================

    # COPY VIDEO - NO ENCODING
    "-map", "0:v:0",
    "-c:v", "copy",

    # No FPS conversion
    "-fps_mode", "passthrough",

    # =====================================================
    # AUDIO
    # =====================================================

    "-map", "0:a:0?",

    # Encode audio only
    "-c:a", "aac",
    "-b:a", "128k",
    "-ar", "44100",
    "-ac", "2",

    # Audio synchronization
    "-af",
    "aresample=async=1000:"
    "min_hard_comp=0.100000:"
    "first_pts=0",

    # =====================================================
    # OUTPUT
    # =====================================================

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

    # Stop FFmpeg first
    stop_process(
        ffmpeg_process,
        "FFmpeg"
    )

    # Then stop Streamlink
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
    print("[SYSTEM] Stopping current processes...")
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
print(f"YouTube     : {YOUTUBE_SOURCE}")
print(f"Video       : COPY")
print(f"Video Encode: OFF")
print(f"Crop        : OFF")
print(f"Resize      : OFF")
print(f"FPS Convert : OFF")
print(f"Audio       : AAC 128k")
print(f"Destination : Restream")
print(f"Auto Retry  : ON")
print(f"Status      : RUNNING")
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
            "Starting YouTube monitor..."
        )
        print("==============================================")

        print(
            "[SYSTEM] Waiting for an actual "
            "YouTube LIVE stream..."
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

        print("[SYSTEM] FFmpeg started.")
        print(
            "[SYSTEM] Waiting for YouTube "
            "stream data..."
        )
        print(
            "[SYSTEM] Sending stream "
            "to Restream..."
        )

        ffmpeg_process = subprocess.Popen(
            FFMPEG_CMD,
            stdin=streamlink_process.stdout,
            stdout=None,
            stderr=None,
            bufsize=0
        )

        # Close parent copy of pipe
        streamlink_process.stdout.close()

        # =================================================
        # MONITOR
        # =================================================

        while not stopping:

            ffmpeg_return = (
                ffmpeg_process.poll()
            )

            streamlink_return = (
                streamlink_process.poll()
            )

            # ---------------------------------------------
            # FFmpeg stopped
            # ---------------------------------------------

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

            # ---------------------------------------------
            # Streamlink stopped
            # ---------------------------------------------

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

        # =================================================
        # STREAM ENDED / CONNECTION FAILED
        # =================================================

        if stopping:
            break

        print()
        print(
            "=============================================="
        )
        print(
            "YouTube LIVE session ended "
            "or connection failed."
        )
        print(
            "Stopping current processes..."
        )
        print(
            "=============================================="
        )

        cleanup()

        print(
            f"[SYSTEM] Waiting {RESTART_DELAY} "
            "seconds before reconnecting..."
        )

        time.sleep(RESTART_DELAY)

    # =====================================================
    # INTERRUPT
    # =====================================================

    except KeyboardInterrupt:

        stopping = True

        print(
            "\n[SYSTEM] Keyboard interrupt."
        )

        cleanup()

        break

    # =====================================================
    # BROKEN PIPE
    # =====================================================

    except BrokenPipeError:

        print(
            "\n[SYSTEM] Broken pipe detected."
        )

        cleanup()

        if not stopping:
            time.sleep(RESTART_DELAY)

    # =====================================================
    # OS ERROR
    # =====================================================

    except OSError as e:

        print(
            f"\n[SYSTEM] OS error: {e}"
        )

        cleanup()

        if not stopping:
            time.sleep(RESTART_DELAY)

    # =====================================================
    # UNKNOWN ERROR
    # =====================================================

    except Exception as e:

        print(
            f"\n[SYSTEM] Unexpected error: {e}"
        )

        cleanup()

        if not stopping:
            time.sleep(RESTART_DELAY)

    # =====================================================
    # FINAL CLEANUP
    # =====================================================

    finally:

        if not stopping:
            cleanup()


print()
print("[SYSTEM] Relay stopped.")
