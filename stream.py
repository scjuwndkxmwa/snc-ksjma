import os
import subprocess
import time
import signal
import sys


# =========================================================
# SETTINGS
# =========================================================

YOUTUBE_URL = "https://www.youtube.com/live/7DHNbnPMNiM"

RESTREAM_STREAM_KEY = os.environ.get("RESTREAM_STREAM_KEY")

if not RESTREAM_STREAM_KEY:
    raise RuntimeError("RESTREAM_STREAM_KEY is not set.")

RESTREAM_RTMP = f"rtmp://live.restream.io/live/{RESTREAM_STREAM_KEY}"


# =========================================================
# RECONNECT SETTINGS
# =========================================================

RECONNECT_DELAY = 5
SOURCE_RETRY_DELAY = 5

# How long to wait for Streamlink to actually start
STREAM_START_TIMEOUT = 60

# How often we check the processes
MONITOR_INTERVAL = 2


# =========================================================
# DISPLAY
# =========================================================

print("=" * 60, flush=True)
print("       YouTube 24/7 -> Restream -> TikTok", flush=True)
print("=" * 60, flush=True)
print(f"YouTube        : {YOUTUBE_URL}", flush=True)
print("Destination    : Restream", flush=True)
print("Cookies        : OFF", flush=True)
print("Video          : COPY", flush=True)
print("Video Encode   : OFF", flush=True)
print("Crop           : OFF", flush=True)
print("Resize         : OFF", flush=True)
print("FPS Convert    : OFF", flush=True)
print("Audio          : AAC 128k", flush=True)
print("Auto-Reconnect : ON", flush=True)
print("Status         : STARTING", flush=True)
print("=" * 60, flush=True)


# =========================================================
# PROCESS CONTROL
# =========================================================

streamlink_process = None
ffmpeg_process = None

shutdown_requested = False


def stop_process(process, name="process"):

    if process is None:
        return

    try:

        if process.poll() is None:

            print(f"[SYSTEM] Stopping {name}...", flush=True)

            process.terminate()

            try:
                process.wait(timeout=5)

            except subprocess.TimeoutExpired:

                print(
                    f"[SYSTEM] Killing {name}...",
                    flush=True
                )

                process.kill()
                process.wait()

    except Exception as e:

        print(
            f"[SYSTEM] Error stopping {name}: {e}",
            flush=True
        )


def cleanup():

    global streamlink_process
    global ffmpeg_process

    stop_process(ffmpeg_process, "FFmpeg")
    stop_process(streamlink_process, "Streamlink")

    ffmpeg_process = None
    streamlink_process = None


def signal_handler(sig, frame):

    global shutdown_requested

    print(
        "\n[SYSTEM] Shutdown requested...",
        flush=True
    )

    shutdown_requested = True

    cleanup()

    sys.exit(0)


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


# =========================================================
# STREAMLINK
# =========================================================

def build_streamlink_command():

    return [
        "streamlink",

        "--stdout",

        # Keep a small live edge for lower latency.
        "--hls-live-edge",
        "2",

        # Buffer for temporary network problems.
        "--ringbuffer-size",
        "256M",

        # Stream retry settings.
        "--retry-streams",
        "10",

        "--retry-max",
        "50",

        # Segment retry settings.
        "--stream-segment-attempts",
        "10",

        "--stream-segment-timeout",
        "20",

        "--stream-timeout",
        "30",

        # Source
        YOUTUBE_URL,

        # Highest available quality.
        "best"
    ]


# =========================================================
# FFMPEG
# =========================================================

def build_ffmpeg_command():

    return [

        "ffmpeg",

        "-hide_banner",

        "-loglevel",
        "warning",

        "-stats",

        # Input queue.
        "-thread_queue_size",
        "1024",

        # Generate usable timestamps and discard corrupt packets.
        "-fflags",
        "+genpts+discardcorrupt",

        "-err_detect",
        "ignore_err",

        # Input from Streamlink.
        "-i",
        "-",

        # =================================================
        # VIDEO = COPY
        # =================================================

        "-map",
        "0:v:0",

        "-c:v",
        "copy",

        # =================================================
        # AUDIO = AAC
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

        # Audio timestamp correction.
        "-af",
        "aresample=async=1000:min_hard_comp=0.100000:first_pts=0",

        # =================================================
        # OUTPUT
        # =================================================

        "-flvflags",
        "no_duration_filesize",

        "-f",
        "flv",

        RESTREAM_RTMP
    ]


# =========================================================
# WAIT FOR REAL STREAM
# =========================================================

def wait_for_streamlink(process):

    start_time = time.time()

    print(
        "[SYSTEM] Waiting for REAL YouTube stream data...",
        flush=True
    )

    while True:

        if shutdown_requested:
            return False

        # Streamlink died.
        if process.poll() is not None:

            print(
                f"[SYSTEM] Streamlink exited before data "
                f"(exit code: {process.returncode})",
                flush=True
            )

            return False

        # We don't wait forever.
        if time.time() - start_time >= STREAM_START_TIMEOUT:

            print(
                "[SYSTEM] YouTube stream did not provide "
                "data within the timeout.",
                flush=True
            )

            return False

        # Give Streamlink time to open the HLS stream.
        time.sleep(1)

        # If stdout has received data, FFmpeg can start.
        if process.stdout:

            try:

                import select

                ready, _, _ = select.select(
                    [process.stdout],
                    [],
                    [],
                    0
                )

                if ready:

                    print(
                        "[SYSTEM] YouTube stream detected.",
                        flush=True
                    )

                    return True

            except Exception:

                # Linux/POSIX fallback.
                # Railway runs Linux.
                pass


# =========================================================
# RUN ONE STREAM SESSION
# =========================================================

def run_one_session():

    global streamlink_process
    global ffmpeg_process

    cleanup()

    print("\n" + "=" * 60, flush=True)
    print("Waiting for YouTube LIVE...", flush=True)
    print("=" * 60, flush=True)

    streamlink_command = build_streamlink_command()
    ffmpeg_command = build_ffmpeg_command()

    print(
        "[SYSTEM] Starting Streamlink...",
        flush=True
    )

    streamlink_process = subprocess.Popen(
        streamlink_command,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        bufsize=0
    )

    print(
        "[SYSTEM] Waiting for YouTube stream data...",
        flush=True
    )

    # -----------------------------------------------------
    # IMPORTANT
    # -----------------------------------------------------
    # We need to know whether Streamlink actually produced
    # data before launching FFmpeg.
    # -----------------------------------------------------

    start_time = time.time()

    while True:

        if shutdown_requested:
            return False

        if streamlink_process.poll() is not None:

            print(
                "[SYSTEM] Streamlink stopped before "
                "producing a usable stream.",
                flush=True
            )

            return False

        # On Linux, select() lets us detect data without
        # blocking the Python process.
        try:

            import select

            ready, _, _ = select.select(
                [streamlink_process.stdout],
                [],
                [],
                1
            )

            if ready:

                print(
                    "[SYSTEM] YouTube stream detected.",
                    flush=True
                )

                break

        except Exception as e:

            print(
                f"[SYSTEM] Stream detection warning: {e}",
                flush=True
            )

            break

        if time.time() - start_time >= STREAM_START_TIMEOUT:

            print(
                "[SYSTEM] YouTube stream did not provide "
                "data within the timeout.",
                flush=True
            )

            return False

    # -----------------------------------------------------
    # START FFMPEG
    # -----------------------------------------------------

    print(
        "[SYSTEM] Starting FFmpeg...",
        flush=True
    )

    print(
        "[SYSTEM] Video: COPY",
        flush=True
    )

    print(
        "[SYSTEM] Video Encode: OFF",
        flush=True
    )

    print(
        "[SYSTEM] Audio: AAC 128k",
        flush=True
    )

    print(
        "[SYSTEM] Sending stream to Restream...",
        flush=True
    )

    ffmpeg_process = subprocess.Popen(
        ffmpeg_command,
        stdin=streamlink_process.stdout,
        stdout=subprocess.DEVNULL,
        stderr=sys.stderr
    )

    # FFmpeg owns stdin now.
    if streamlink_process.stdout:
        streamlink_process.stdout.close()

    print(
        "[SYSTEM] Stream is RUNNING.",
        flush=True
    )

    # =====================================================
    # MONITOR
    # =====================================================

    while True:

        if shutdown_requested:
            return False

        ffmpeg_status = ffmpeg_process.poll()
        streamlink_status = streamlink_process.poll()

        # -------------------------------------------------
        # FFmpeg stopped
        # -------------------------------------------------

        if ffmpeg_status is not None:

            print(
                f"[SYSTEM] FFmpeg stopped "
                f"(exit code: {ffmpeg_status})",
                flush=True
            )

            return False

        # -------------------------------------------------
        # Streamlink stopped
        # -------------------------------------------------

        if streamlink_status is not None:

            print(
                f"[SYSTEM] Streamlink stopped "
                f"(exit code: {streamlink_status})",
                flush=True
            )

            return False

        time.sleep(MONITOR_INTERVAL)


# =========================================================
# MAIN LOOP
# =========================================================

def run_stream():

    global shutdown_requested

    while not shutdown_requested:

        try:

            success = run_one_session()

        except Exception as e:

            print(
                f"[ERROR] {type(e).__name__}: {e}",
                flush=True
            )

            success = False

        finally:

            cleanup()

        if shutdown_requested:
            break

        print("\n" + "=" * 60, flush=True)

        if success:

            print(
                "[SYSTEM] Stream session ended.",
                flush=True
            )

        else:

            print(
                "[SYSTEM] Stream lost or unavailable.",
                flush=True
            )

        print(
            f"[SYSTEM] Auto-reconnect in "
            f"{RECONNECT_DELAY} seconds...",
            flush=True
        )

        print("=" * 60, flush=True)

        # -------------------------------------------------
        # Wait before reconnecting.
        # -------------------------------------------------

        for _ in range(RECONNECT_DELAY):

            if shutdown_requested:
                break

            time.sleep(1)


# =========================================================
# START
# =========================================================

try:

    print(
        "[SYSTEM] Starting 24/7 relay...",
        flush=True
    )

    run_stream()

except KeyboardInterrupt:

    print(
        "\n[SYSTEM] Keyboard interrupt.",
        flush=True
    )

finally:

    cleanup()

    print(
        "[SYSTEM] Relay stopped.",
        flush=True
    )
