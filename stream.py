import os
import subprocess
import time
import signal
import sys


# =========================================================
# SETTINGS
# =========================================================

YOUTUBE_URL = "https://www.youtube.com/live/7DHNbnPMNiM"

RESTREAM_STREAM_KEY = "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9"

RESTREAM_RTMP = (
    f"rtmp://live.restream.io/live/{RESTREAM_STREAM_KEY}"
)

RECONNECT_DELAY = 5

STREAMLINK_RETRY_DELAY = 10


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


# =========================================================
# STOP PROCESS
# =========================================================

def stop_process(process, name):

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
                process.wait()

    except Exception as e:

        print(
            f"[SYSTEM] Error stopping {name}: {e}"
        )


# =========================================================
# CLEANUP
# =========================================================

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

        # Keep a small live buffer.
        "--hls-live-edge",
        "3",

        "--ringbuffer-size",
        "256M",

        # Retry individual HLS segments.
        "--stream-segment-attempts",
        "8",

        "--stream-segment-timeout",
        "20",

        "--stream-timeout",
        "30",

        # Retry YouTube when temporarily unavailable.
        "--retry-streams",
        "10",

        "--retry-max",
        "50",

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

        "-loglevel",
        "warning",

        "-stats",

        # Large input queue.
        "-thread_queue_size",
        "2048",

        # Generate timestamps and discard damaged packets.
        "-fflags",
        "+genpts+discardcorrupt",

        "-err_detect",
        "ignore_err",

        # Input from Streamlink.
        "-i",
        "-",

        # =================================================
        # VIDEO
        # =================================================

        "-map",
        "0:v:0",

        "-c:v",
        "copy",

        # =================================================
        # AUDIO
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
        # OUTPUT
        # =================================================

        "-flvflags",
        "no_duration_filesize",

        "-f",
        "flv",

        RESTREAM_RTMP
    ]


# =========================================================
# START ONE SESSION
# =========================================================

def start_session():

    global streamlink_process
    global ffmpeg_process

    print("=" * 60)
    print("[SYSTEM] Starting relay session")
    print("=" * 60)

    # -----------------------------------------------------
    # STREAMLINK
    # -----------------------------------------------------

    streamlink_command = build_streamlink_command()

    print("[SYSTEM] Starting Streamlink...")
    print("[SYSTEM] Cookies: OFF")
    print("[SYSTEM] Quality: BEST")
    print("[SYSTEM] Video source: COPY")
    print("[SYSTEM] Waiting for YouTube stream data...")

    streamlink_process = subprocess.Popen(

        streamlink_command,

        stdout=subprocess.PIPE,

        stderr=sys.stderr,

        bufsize=0
    )

    # -----------------------------------------------------
    # IMPORTANT
    # -----------------------------------------------------
    # Do NOT declare the stream as running simply because
    # Streamlink process exists.
    #
    # Wait until actual bytes arrive.
    # -----------------------------------------------------

    print("[SYSTEM] Streamlink process started.")

    first_data = False

    start_time = time.time()

    while True:

        if streamlink_process.poll() is not None:

            print(
                "[SYSTEM] Streamlink exited before media data."
            )

            return False

        if streamlink_process.stdout:

            data = streamlink_process.stdout.peek(
                1
            )

            if data:

                first_data = True
                break

        # Timeout for first media data.
        if time.time() - start_time > 90:

            print(
                "[SYSTEM] No real media data received "
                "within 90 seconds."
            )

            return False

        time.sleep(0.2)

    if not first_data:

        return False

    print("[SYSTEM] REAL YouTube media data received.")
    print("[SYSTEM] Starting FFmpeg...")


    # -----------------------------------------------------
    # FFMPEG
    # -----------------------------------------------------

    ffmpeg_command = build_ffmpeg_command()

    ffmpeg_process = subprocess.Popen(

        ffmpeg_command,

        stdin=streamlink_process.stdout,

        stdout=subprocess.DEVNULL,

        stderr=sys.stderr,

        bufsize=0
    )

    # Give ownership of the pipe to FFmpeg.
    if streamlink_process.stdout:

        streamlink_process.stdout.close()

    print("[SYSTEM] FFmpeg connected to Streamlink.")
    print("[SYSTEM] Video: COPY")
    print("[SYSTEM] Video Encode: OFF")
    print("[SYSTEM] Audio: AAC 128k")
    print("[SYSTEM] Sending YouTube -> Restream.")
    print("[SYSTEM] Stream is RUNNING.")

    # -----------------------------------------------------
    # MONITOR
    # -----------------------------------------------------

    while True:

        ffmpeg_status = ffmpeg_process.poll()

        streamlink_status = streamlink_process.poll()

        # FFmpeg stopped.
        if ffmpeg_status is not None:

            print(
                f"[SYSTEM] FFmpeg stopped "
                f"(exit code: {ffmpeg_status})."
            )

            return False

        # Streamlink stopped.
        if streamlink_status is not None:

            print(
                f"[SYSTEM] Streamlink stopped "
                f"(exit code: {streamlink_status})."
            )

            return False

        time.sleep(2)


# =========================================================
# MAIN LOOP
# =========================================================

def run_forever():

    while True:

        cleanup()

        try:

            result = start_session()

            if result:

                print(
                    "[SYSTEM] Relay session ended normally."
                )

            else:

                print(
                    "[SYSTEM] Relay session failed "
                    "or source disconnected."
                )

        except Exception as e:

            print(
                f"[ERROR] {type(e).__name__}: {e}"
            )

        finally:

            cleanup()

        print("=" * 60)
        print(
            f"[SYSTEM] Reconnecting in "
            f"{RECONNECT_DELAY} seconds..."
        )
        print("=" * 60)

        time.sleep(RECONNECT_DELAY)


# =========================================================
# START
# =========================================================

try:

    print("[SYSTEM] Starting 24/7 relay...")

    run_forever()

except KeyboardInterrupt:

    print("\n[SYSTEM] Keyboard interrupt.")

finally:

    cleanup()
