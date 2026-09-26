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

RESTREAM_RTMP = f"rtmp://live.restream.io/live/{RESTREAM_STREAM_KEY}"

COOKIES_FILE = "YOUTUBE_COOKIES"

RECONNECT_DELAY = 5
SOURCE_RETRY_DELAY = 5


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
    global streamlink_process, ffmpeg_process

    print("\n[SYSTEM] Stopping processes...")

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

        "--hls-live-edge", "2",

        "--ringbuffer-size", "512M",

        "--retry-streams", "10",
        "--retry-max", "50",

        "--stream-segment-attempts", "5",
        "--stream-segment-timeout", "15",
        "--stream-timeout", "30",
    ]

    # -----------------------------------------------------
    # YouTube Cookies
    # -----------------------------------------------------

    if os.path.exists(COOKIES_FILE):

        command += [
            "--http-cookies-file",
            COOKIES_FILE
        ]

        print("[SYSTEM] YouTube cookies enabled.")

    else:

        print("[SYSTEM] YouTube cookies file not found.")
        print("[SYSTEM] Continuing without cookies.")

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

        "-thread_queue_size", "1024",

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

        "-af",
        "aresample=async=1000:min_hard_comp=0.100000:first_pts=0",

        # -------------------------------------------------
        # OUTPUT
        # -------------------------------------------------

        "-flvflags", "no_duration_filesize",

        "-f", "flv",

        RESTREAM_RTMP
    ]


# =========================================================
# MAIN STREAM LOOP
# =========================================================

def run_stream():

    global streamlink_process
    global ffmpeg_process

    while True:

        cleanup()

        print("\n==============================================")
        print("Waiting for YouTube LIVE...")
        print("==============================================")

        try:

            streamlink_command = build_streamlink_command()
            ffmpeg_command = build_ffmpeg_command()

            print("[SYSTEM] Starting Streamlink...")
            print("[SYSTEM] Waiting for YouTube stream data...")

            streamlink_process = subprocess.Popen(
                streamlink_command,
                stdout=subprocess.PIPE,
                stderr=sys.stderr,
                bufsize=0
            )

            time.sleep(2)

            if streamlink_process.poll() is not None:

                print(
                    "[ERROR] Streamlink stopped "
                    "before FFmpeg started."
                )

                time.sleep(SOURCE_RETRY_DELAY)
                continue

            print("[SYSTEM] YouTube LIVE connected!")
            print("[SYSTEM] Starting FFmpeg...")
            print("[SYSTEM] Video: COPY")
            print("[SYSTEM] Audio: AAC 128k")
            print("[SYSTEM] Sending stream to Restream...")

            ffmpeg_process = subprocess.Popen(
                ffmpeg_command,
                stdin=streamlink_process.stdout,
                stdout=subprocess.DEVNULL,
                stderr=sys.stderr
            )

            if streamlink_process.stdout:
                streamlink_process.stdout.close()

            print("[SYSTEM] Stream is RUNNING.")

            # -------------------------------------------------
            # Monitor both processes
            # -------------------------------------------------

            while True:

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
