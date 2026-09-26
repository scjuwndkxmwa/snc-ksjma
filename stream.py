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
    "rtmp://live.restream.io/live/"
    + RESTREAM_STREAM_KEY
)

RECONNECT_DELAY = 5
SOURCE_RETRY_DELAY = 5


# =========================================================
# DISPLAY
# =========================================================

print("=" * 60)
print("       YouTube 24/7 -> Restream -> TikTok")
print("=" * 60)

print(f"YouTube        : {YOUTUBE_URL}")
print("Destination    : Restream")
print("Video          : COPY")
print("Video Encode   : OFF")
print("Crop           : OFF")
print("Resize         : OFF")
print("FPS Convert    : OFF")
print("Audio          : AAC 128k")
print("Auto-Reconnect : ON")
print("Cookies        : OFF")
print("Status         : STARTING")
print("=" * 60)


# =========================================================
# PROCESS CONTROL
# =========================================================

streamlink_process = None
ffmpeg_process = None


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
                process.wait(timeout=3)

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

        "--hls-live-edge", "2",

        "--ringbuffer-size", "512M",

        "--retry-streams", "10",
        "--retry-max", "50",

        "--stream-segment-attempts", "10",
        "--stream-segment-timeout", "30",
        "--stream-timeout", "60",

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
        # AAC ONLY
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
# MAIN
# =========================================================

def run_stream():

    global streamlink_process
    global ffmpeg_process

    while True:

        cleanup()

        print("\n" + "=" * 60)
        print("Waiting for YouTube LIVE...")
        print("=" * 60)

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

            # Give Streamlink time to resolve the YouTube stream.
            time.sleep(3)

            # -------------------------------------------------
            # CHECK STREAMLINK
            # -------------------------------------------------

            if streamlink_process.poll() is not None:

                print(
                    "[ERROR] Streamlink stopped "
                    "before FFmpeg started."
                )

                time.sleep(SOURCE_RETRY_DELAY)

                continue

            # -------------------------------------------------
            # START FFMPEG DIRECTLY
            # -------------------------------------------------

            print("[SYSTEM] YouTube stream detected.")
            print("[SYSTEM] Starting FFmpeg...")
            print("[SYSTEM] Video: COPY")
            print("[SYSTEM] Video Encode: OFF")
            print("[SYSTEM] Audio: AAC 128k")
            print("[SYSTEM] Sending stream to Restream...")

            ffmpeg_process = subprocess.Popen(

                ffmpeg_command,

                stdin=streamlink_process.stdout,

                stdout=subprocess.DEVNULL,

                stderr=sys.stderr,

                bufsize=0
            )

            # Parent no longer needs this pipe.
            if streamlink_process.stdout:

                streamlink_process.stdout.close()

            print("[SYSTEM] Stream is RUNNING.")

            # -------------------------------------------------
            # MONITOR
            # -------------------------------------------------

            while True:

                ffmpeg_status = ffmpeg_process.poll()
                streamlink_status = streamlink_process.poll()

                # FFmpeg stopped
                if ffmpeg_status is not None:

                    print(
                        f"[SYSTEM] FFmpeg stopped "
                        f"(exit code: {ffmpeg_status})"
                    )

                    break

                # Streamlink stopped
                if streamlink_status is not None:

                    print(
                        f"[SYSTEM] Streamlink stopped "
                        f"(exit code: {streamlink_status})"
                    )

                    break

                time.sleep(2)

        except KeyboardInterrupt:

            print("\n[SYSTEM] Keyboard interrupt.")

            cleanup()

            break

        except BrokenPipeError:

            print("\n[SYSTEM] Broken pipe detected.")

            cleanup()

        except Exception as e:

            print(
                f"\n[ERROR] {type(e).__name__}: {e}"
            )

        finally:

            cleanup()

        # -------------------------------------------------
        # AUTO RECONNECT
        # -------------------------------------------------

        print("\n" + "=" * 60)
        print("[SYSTEM] YouTube stream ended or connection was lost.")
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

    run_stream()

except KeyboardInterrupt:

    print("\n[SYSTEM] Stopped.")

finally:

    cleanup()
