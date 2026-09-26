import os
import subprocess
import time
import signal
import sys


# =========================================================
# SETTINGS
# =========================================================

YOUTUBE_URL = "https://www.youtube.com/live/7DHNbnPMNiM"

RESTREAM_STREAM_KEY = os.environ.get(
    "RESTREAM_STREAM_KEY",
    "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9"
)

RESTREAM_RTMP = (
    "rtmp://live.restream.io/live/"
    + RESTREAM_STREAM_KEY
)

RECONNECT_DELAY = 10
SOURCE_RETRY_DELAY = 15
STREAM_START_TIMEOUT = 120


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

            print(f"[SYSTEM] Stopping {name}...")

            process.terminate()

            try:
                process.wait(timeout=5)

            except subprocess.TimeoutExpired:

                print(f"[SYSTEM] Killing {name}...")

                process.kill()
                process.wait(timeout=5)

    except Exception as e:

        print(f"[SYSTEM] Error stopping {name}: {e}")


def cleanup():

    global streamlink_process
    global ffmpeg_process

    stop_process(ffmpeg_process, "FFmpeg")
    stop_process(streamlink_process, "Streamlink")

    ffmpeg_process = None
    streamlink_process = None


def signal_handler(sig, frame):

    global shutdown_requested

    shutdown_requested = True

    print("\n[SYSTEM] Shutdown requested...")

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

        # HLS latency
        "--hls-live-edge", "2",

        # Buffer
        "--ringbuffer-size", "512M",

        # Automatic reconnect
        "--retry-streams", "10",
        "--retry-max", "50",

        # Segment recovery
        "--stream-segment-attempts", "10",
        "--stream-segment-timeout", "20",
        "--stream-timeout", "30",

        # YouTube
        YOUTUBE_URL,
        "best"
    ]


# =========================================================
# FFMPEG
# =========================================================

def build_ffmpeg_command():

    return [

        "ffmpeg",

        "-hide_banner",
        "-loglevel", "warning",
        "-stats",

        # -------------------------------------------------
        # INPUT
        # -------------------------------------------------

        "-thread_queue_size", "2048",

        "-fflags",
        "+genpts+discardcorrupt",

        "-err_detect",
        "ignore_err",

        "-i",
        "-",

        # -------------------------------------------------
        # VIDEO
        # COPY - NO ENCODING
        # -------------------------------------------------

        "-map",
        "0:v:0",

        "-c:v",
        "copy",

        # -------------------------------------------------
        # AUDIO
        # AAC
        # -------------------------------------------------

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

        # -------------------------------------------------
        # OUTPUT
        # -------------------------------------------------

        "-fps_mode",
        "passthrough",

        "-flush_packets",
        "1",

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

    streamlink_process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        bufsize=0
    )

    return streamlink_process


# =========================================================
# WAIT FOR REAL STREAM
# =========================================================

def wait_for_stream_data():

    global streamlink_process

    start_time = time.time()

    print("[SYSTEM] Waiting for REAL YouTube stream data...")

    while not shutdown_requested:

        # Streamlink stopped
        if streamlink_process.poll() is not None:

            print(
                "[ERROR] Streamlink stopped before "
                "providing stream data."
            )

            return False

        # Check whether data is available
        if streamlink_process.stdout:

            try:

                data = streamlink_process.stdout.peek(1)

                if data:

                    print(
                        "[SYSTEM] REAL YouTube stream data received."
                    )

                    return True

            except Exception:
                pass

        # Timeout
        if time.time() - start_time >= STREAM_START_TIMEOUT:

            print(
                "[ERROR] YouTube stream did not provide "
                "real data within timeout."
            )

            return False

        time.sleep(1)

    return False


# =========================================================
# START FFMPEG
# =========================================================

def start_ffmpeg():

    global ffmpeg_process

    command = build_ffmpeg_command()

    print("[SYSTEM] Starting FFmpeg...")
    print("[SYSTEM] Video: COPY")
    print("[SYSTEM] Audio: AAC 128k")
    print("[SYSTEM] Sending stream to Restream...")

    ffmpeg_process = subprocess.Popen(
        command,
        stdin=streamlink_process.stdout,
        stdout=subprocess.DEVNULL,
        stderr=sys.stderr,
        bufsize=0
    )

    if streamlink_process.stdout:
        streamlink_process.stdout.close()

    print("[SYSTEM] Stream is RUNNING.")


# =========================================================
# MAIN LOOP
# =========================================================

def run():

    global streamlink_process
    global ffmpeg_process

    while not shutdown_requested:

        cleanup()

        print("\n" + "=" * 60)
        print("Waiting for YouTube LIVE...")
        print("=" * 60)

        try:

            # Start YouTube connection
            start_streamlink()

            # Do NOT start FFmpeg until actual data arrives
            if not wait_for_stream_data():

                cleanup()

                print(
                    f"[SYSTEM] YouTube unavailable."
                    f" Retrying in {SOURCE_RETRY_DELAY} seconds..."
                )

                time.sleep(SOURCE_RETRY_DELAY)

                continue

            print("[SYSTEM] YouTube LIVE confirmed.")

            # Start Restream output
            start_ffmpeg()

            # -------------------------------------------------
            # MONITOR
            # -------------------------------------------------

            while not shutdown_requested:

                ffmpeg_status = ffmpeg_process.poll()
                streamlink_status = streamlink_process.poll()

                if ffmpeg_status is not None:

                    print(
                        f"[SYSTEM] FFmpeg stopped "
                        f"(exit code: {ffmpeg_status})"
                    )

                    break

                if streamlink_status is not None:

                    print(
                        f"[SYSTEM] Streamlink stopped "
                        f"(exit code: {streamlink_status})"
                    )

                    break

                time.sleep(2)

        except KeyboardInterrupt:

            break

        except Exception as e:

            print(
                f"[ERROR] {type(e).__name__}: {e}"
            )

        finally:

            cleanup()

        if shutdown_requested:
            break

        print("\n" + "=" * 60)
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
    run()

finally:

    cleanup()

    print("[SYSTEM] Relay stopped.")
