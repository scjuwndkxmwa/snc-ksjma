import os
import subprocess
import time
import signal
import sys


# =========================================================
# SETTINGS
# =========================================================

# YouTube LIVE source
YOUTUBE_URL = "https://www.youtube.com/watch?v=Dkhgp_G81GQ"

# Restream destination
RESTREAM_RTMP = os.environ.get(
    "RESTREAM_RTMP",
    "rtmp://live.restream.io/live"
)

# Restream Stream Key
RESTREAM_KEY = os.environ.get(
    "RESTREAM_KEY",
    "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9"
)

RESTREAM_URL = f"{RESTREAM_RTMP}/{RESTREAM_KEY}"

# Cookies file موجود في GitHub
COOKIES_FILE = "/app/YOUTUBE_COOKIES"

# Quality
QUALITY = "best"

# Retry / reconnect
CHECK_INTERVAL = 30
RECONNECT_DELAY = 10

# Streamlink settings
HLS_LIVE_EDGE = "3"
RINGBUFFER_SIZE = "256M"


# =========================================================
# PROCESS MANAGEMENT
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
                process.wait(timeout=5)

    except Exception:
        pass


def stop_all():
    global streamlink_process, ffmpeg_process

    print("[SYSTEM] Stopping processes...", flush=True)

    stop_process(ffmpeg_process)
    stop_process(streamlink_process)

    ffmpeg_process = None
    streamlink_process = None


def signal_handler(signum, frame):
    print("\n[SYSTEM] Shutdown signal received.", flush=True)
    stop_all()
    sys.exit(0)


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


# =========================================================
# PRINT STATUS
# =========================================================

def print_status():
    print()
    print("==============================================", flush=True)
    print("       YouTube 24/7 -> Restream -> TikTok", flush=True)
    print("==============================================", flush=True)
    print(f"YouTube     : {YOUTUBE_URL}", flush=True)
    print("Video       : COPY", flush=True)
    print("Video Encode: OFF", flush=True)
    print("Crop        : OFF", flush=True)
    print("Resize      : OFF", flush=True)
    print("FPS Convert : OFF", flush=True)
    print("Audio       : AAC 128k", flush=True)
    print("Destination : Restream", flush=True)
    print("Auto-Reconnect: ON", flush=True)
    print("YouTube Cookies: ON", flush=True)
    print("Status      : RUNNING", flush=True)
    print("==============================================", flush=True)


# =========================================================
# START STREAMLINK
# =========================================================

def start_streamlink():

    cmd = [
        "streamlink",

        "--http-cookies-file",
        COOKIES_FILE,

        "--hls-live-edge",
        HLS_LIVE_EDGE,

        "--ringbuffer-size",
        RINGBUFFER_SIZE,

        "--retry-streams",
        "5",

        "--retry-max",
        "0",

        "--stream-segment-attempts",
        "10",

        "--stream-segment-timeout",
        "15",

        "--stream-timeout",
        "30",

        "--http-timeout",
        "30",

        "--stdout",

        YOUTUBE_URL,

        QUALITY
    ]

    print("[SYSTEM] Starting Streamlink...", flush=True)

    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=None,
        bufsize=0
    )


# =========================================================
# START FFMPEG
# =========================================================

def start_ffmpeg():

    cmd = [
        "ffmpeg",

        "-hide_banner",
        "-loglevel",
        "warning",
        "-stats",

        # Input from Streamlink
        "-thread_queue_size",
        "1024",

        "-i",
        "-",

        # Timestamp handling
        "-fflags",
        "+genpts+discardcorrupt",

        "-err_detect",
        "ignore_err",

        "-dts_delta_threshold",
        "1",

        # VIDEO = COPY
        "-map",
        "0:v:0",

        "-c:v",
        "copy",

        # AUDIO = ENCODE
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

        # Audio timestamp correction
        "-af",
        "aresample=async=1000:min_hard_comp=0.100000:first_pts=0",

        # FLV for RTMP
        "-f",
        "flv",

        RESTREAM_URL
    ]

    print("[SYSTEM] Starting FFmpeg...", flush=True)
    print("[SYSTEM] Video: COPY", flush=True)
    print("[SYSTEM] Audio: AAC 128k", flush=True)
    print("[SYSTEM] Sending stream to Restream...", flush=True)

    return subprocess.Popen(
        cmd,
        stdin=streamlink_process.stdout,
        stdout=subprocess.DEVNULL,
        stderr=None
    )


# =========================================================
# MAIN STREAM SESSION
# =========================================================

def run_session():

    global streamlink_process
    global ffmpeg_process

    try:

        print_status()

        if not os.path.exists(COOKIES_FILE):
            print(
                "[WARNING] YOUTUBE_COOKIES file not found!",
                flush=True
            )
            print(
                "[WARNING] YouTube may return LOGIN_REQUIRED.",
                flush=True
            )

        # Start Streamlink
        streamlink_process = start_streamlink()

        time.sleep(2)

        # Start FFmpeg
        ffmpeg_process = start_ffmpeg()

        print(
            "[SYSTEM] Waiting for YouTube stream data...",
            flush=True
        )

        # Monitor both processes
        while True:

            streamlink_exit = streamlink_process.poll()
            ffmpeg_exit = ffmpeg_process.poll()

            # Streamlink stopped
            if streamlink_exit is not None:

                print(
                    f"[SYSTEM] Streamlink stopped. Exit code: {streamlink_exit}",
                    flush=True
                )

                # FFmpeg no longer has valid input
                stop_process(ffmpeg_process)

                return

            # FFmpeg stopped
            if ffmpeg_exit is not None:

                print(
                    f"[SYSTEM] FFmpeg stopped. Exit code: {ffmpeg_exit}",
                    flush=True
                )

                stop_process(streamlink_process)

                return

            time.sleep(2)

    except Exception as e:

        print(
            f"[ERROR] Session error: {e}",
            flush=True
        )

    finally:

        stop_process(ffmpeg_process)
        stop_process(streamlink_process)

        ffmpeg_process = None
        streamlink_process = None


# =========================================================
# 24/7 LOOP
# =========================================================

def main():

    print()
    print("==============================================")
    print("       YouTube -> Restream -> TikTok")
    print("              24/7 AUTO RELAY")
    print("==============================================")
    print()

    while True:

        try:

            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                "Starting YouTube LIVE connection...",
                flush=True
            )

            run_session()

            print()
            print("==============================================")
            print("YouTube LIVE session ended.")
            print("Stopping current processes...")
            print("==============================================")

            print(
                f"[SYSTEM] Waiting {CHECK_INTERVAL} seconds "
                "before checking again...",
                flush=True
            )

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:

            print(
                "[SYSTEM] Keyboard interrupt.",
                flush=True
            )

            stop_all()
            break

        except Exception as e:

            print(
                f"[ERROR] Main loop error: {e}",
                flush=True
            )

            stop_all()

            time.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    main()
