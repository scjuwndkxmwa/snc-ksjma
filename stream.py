import os
import subprocess
import time
import signal
import sys
import threading


# =========================================================
# SETTINGS
# =========================================================

YOUTUBE_URL = "https://www.youtube.com/live/7DHNbnPMNiM"

RESTREAM_STREAM_KEY = os.environ.get(
    "RESTREAM_STREAM_KEY",
    "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9"
)

RESTREAM_RTMP = f"rtmp://live.restream.io/live/{RESTREAM_STREAM_KEY}"

COOKIES_FILE = "YOUTUBE_COOKIES"

RECONNECT_DELAY = 5
SOURCE_RETRY_DELAY = 5

# الوقت الأقصى الذي ننتظره لظهور بيانات فعلية من YouTube
STREAM_START_TIMEOUT = 90

# حجم القراءة من Streamlink
BUFFER_SIZE = 1024 * 1024


# =========================================================
# DISPLAY
# =========================================================

print("=" * 50)
print("       YouTube 24/7 -> Restream -> TikTok")
print("=" * 50)

print(f"YouTube     : {YOUTUBE_URL}")
print("Destination : Restream")
print("Video       : COPY")
print("Video Encode: OFF")
print("Crop        : OFF")
print("Resize      : OFF")
print("FPS Convert : OFF")
print("Audio       : AAC 128k")
print("Auto-Reconnect: ON")
print("Status      : STARTING")
print("=" * 50)


# =========================================================
# PROCESS CONTROL
# =========================================================

streamlink_process = None
ffmpeg_process = None

stop_event = threading.Event()


def stop_process(process):

    if process is None:
        return

    try:

        if process.poll() is None:

            process.terminate()

            try:
                process.wait(timeout=5)

            except subprocess.TimeoutExpired:

                process.kill()
                process.wait()

    except Exception:
        pass


def cleanup():

    global streamlink_process
    global ffmpeg_process

    print("\n[SYSTEM] Stopping processes...")

    stop_event.set()

    stop_process(ffmpeg_process)
    stop_process(streamlink_process)

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

        "--stdout",

        # Low latency
        "--hls-live-edge", "2",

        # Buffer
        "--ringbuffer-size", "128M",

        # Retry source
        "--retry-streams", "10",
        "--retry-max", "50",

        # Segment stability
        "--stream-segment-attempts", "5",
        "--stream-segment-timeout", "15",
        "--stream-timeout", "30",

        # YouTube/browser-like user agent
        "--http-header",
        "User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
    ]

    # -----------------------------------------------------
    # YouTube cookies
    # -----------------------------------------------------

    if os.path.exists(COOKIES_FILE):

        command += [
            "--http-cookies-file",
            COOKIES_FILE
        ]

        print("[SYSTEM] YouTube cookies enabled.")

    else:

        print("[WARNING] YouTube cookies file not found.")
        print("[WARNING] Continuing without cookies.")

    # -----------------------------------------------------
    # URL
    # -----------------------------------------------------

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
        "-loglevel", "warning",
        "-stats",

        # Input buffering
        "-thread_queue_size", "1024",

        # Timestamp handling
        "-fflags", "+genpts+discardcorrupt",

        "-err_detect", "ignore_err",

        "-i", "-",

        # -------------------------------------------------
        # VIDEO = COPY
        # -------------------------------------------------

        "-map", "0:v:0",
        "-c:v", "copy",

        # -------------------------------------------------
        # AUDIO = AAC
        # -------------------------------------------------

        "-map", "0:a:0?",

        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-ac", "2",

        # Keep audio timestamps stable
        "-af",
        "aresample=async=1000:min_hard_comp=0.100000:first_pts=0",

        # -------------------------------------------------
        # OUTPUT
        # -------------------------------------------------

        "-flvflags",
        "no_duration_filesize",

        "-f",
        "flv",

        RESTREAM_RTMP
    ]


# =========================================================
# STREAM PUMP
# =========================================================

def pump_streamlink_to_ffmpeg():

    global streamlink_process
    global ffmpeg_process

    try:

        while not stop_event.is_set():

            if streamlink_process is None:
                break

            if ffmpeg_process is None:
                break

            data = streamlink_process.stdout.read(BUFFER_SIZE)

            if not data:

                break

            try:

                ffmpeg_process.stdin.write(data)
                ffmpeg_process.stdin.flush()

            except (BrokenPipeError, OSError):

                break

    except Exception as e:

        print(
            f"[SYSTEM] Stream transfer stopped: "
            f"{type(e).__name__}: {e}"
        )

    finally:

        try:

            if ffmpeg_process and ffmpeg_process.stdin:
                ffmpeg_process.stdin.close()

        except Exception:
            pass


# =========================================================
# WAIT FOR REAL STREAM DATA
# =========================================================

def wait_for_stream_data():

    global streamlink_process

    print("[SYSTEM] Waiting for REAL YouTube stream data...")

    start_time = time.time()

    while True:

        # Streamlink died
        if streamlink_process.poll() is not None:

            print(
                "[SYSTEM] Streamlink stopped "
                "before receiving stream data."
            )

            return False

        # Check if data is available
        if streamlink_process.stdout:

            try:

                import select

                ready, _, _ = select.select(
                    [streamlink_process.stdout],
                    [],
                    [],
                    1
                )

                if ready:

                    print("[SYSTEM] YouTube LIVE data detected!")

                    return True

            except Exception:

                # Fallback for environments where select
                # cannot be used on the pipe.
                time.sleep(1)

        # Timeout
        if time.time() - start_time >= STREAM_START_TIMEOUT:

            print(
                "[SYSTEM] YouTube stream did not provide "
                "data within the timeout."
            )

            return False

        time.sleep(1)


# =========================================================
# MAIN STREAM LOOP
# =========================================================

def run_stream():

    global streamlink_process
    global ffmpeg_process

    while True:

        stop_event.clear()

        cleanup()

        print("\n==============================================")
        print("Waiting for YouTube LIVE...")
        print("==============================================")

        try:

            streamlink_command = build_streamlink_command()
            ffmpeg_command = build_ffmpeg_command()

            # -------------------------------------------------
            # START STREAMLINK
            # -------------------------------------------------

            print("[SYSTEM] Starting Streamlink...")
            print("[SYSTEM] Waiting for YouTube stream data...")

            streamlink_process = subprocess.Popen(

                streamlink_command,

                stdout=subprocess.PIPE,

                stderr=sys.stderr,

                bufsize=0
            )

            # -------------------------------------------------
            # IMPORTANT:
            # Don't assume connection after 2 seconds.
            # Wait for REAL stream bytes.
            # -------------------------------------------------

            if not wait_for_stream_data():

                print(
                    "[SYSTEM] YouTube stream is not available."
                )

                cleanup()

                time.sleep(SOURCE_RETRY_DELAY)

                continue

            # -------------------------------------------------
            # START FFMPEG
            # -------------------------------------------------

            print("[SYSTEM] YouTube LIVE connected!")
            print("[SYSTEM] Starting FFmpeg...")
            print("[SYSTEM] Video: COPY")
            print("[SYSTEM] Audio: AAC 128k")
            print("[SYSTEM] Sending stream to Restream...")

            ffmpeg_process = subprocess.Popen(

                ffmpeg_command,

                stdin=subprocess.PIPE,

                stdout=subprocess.DEVNULL,

                stderr=sys.stderr,

                bufsize=0
            )

            print("[SYSTEM] Stream is RUNNING.")

            # -------------------------------------------------
            # Transfer thread
            # -------------------------------------------------

            transfer_thread = threading.Thread(

                target=pump_streamlink_to_ffmpeg,

                daemon=True
            )

            transfer_thread.start()

            # -------------------------------------------------
            # Monitor
            # -------------------------------------------------

            while True:

                ffmpeg_status = ffmpeg_process.poll()

                streamlink_status = streamlink_process.poll()

                # -------------------------------------------------
                # FFmpeg stopped
                # -------------------------------------------------

                if ffmpeg_status is not None:

                    print(
                        f"[SYSTEM] FFmpeg stopped "
                        f"(exit code: {ffmpeg_status})"
                    )

                    break

                # -------------------------------------------------
                # Streamlink stopped
                # -------------------------------------------------

                if streamlink_status is not None:

                    print(
                        f"[SYSTEM] Streamlink stopped "
                        f"(exit code: {streamlink_status})"
                    )

                    break

                time.sleep(2)

        except Exception as e:

            print(
                f"[ERROR] {type(e).__name__}: {e}"
            )

        finally:

            cleanup()

        print("\n==============================================")
        print("[SYSTEM] Stream ended or connection lost.")
        print(
            f"[SYSTEM] Auto-reconnect in "
            f"{RECONNECT_DELAY} seconds..."
        )
        print("==============================================")

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
