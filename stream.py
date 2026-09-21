import os
import subprocess
import time
import signal
import sys


TIKTOK_URL = "https://www.tiktok.com/@c.ahmed.h/live"

YOUTUBE_STREAM_KEY = "8yjs-eb3y-wt8s-y45e-ezsu"

YOUTUBE_RTMP = (
    "rtmp://a.rtmp.youtube.com/live2/"
    + YOUTUBE_STREAM_KEY
)


STREAMLINK_CMD = [
    "streamlink",

    "--hls-live-edge", "2",
    "--ringbuffer-size", "512M",

    "--retry-streams", "10",
    "--retry-max", "50",

    "--stream-segment-attempts", "10",
    "--stream-segment-timeout", "30",
    "--stream-timeout", "60",

    "--stdout",

    TIKTOK_URL,
    "best"
]


FFMPEG_CMD = [
    "ffmpeg",

    "-hide_banner",
    "-loglevel", "warning",
    "-stats",

    # =====================================
    # INPUT & TIMESTAMP HANDLING
    # =====================================

    "-thread_queue_size", "2048",

    "-avoid_negative_ts", "make_zero",

    # Use demuxer timebase when stream copying.
    # Helps with non-monotonic timestamps.
    "-copytb", "1",

    "-fflags", "+genpts+discardcorrupt",
    "-err_detect", "ignore_err",

    "-i", "-",

    # =====================================
    # VIDEO
    # =====================================

    # VIDEO COPY - NO ENCODING
    "-map", "0:v:0",
    "-c:v", "copy",

    # Preserve source frame timestamps.
    "-fps_mode", "passthrough",

    # =====================================
    # AUDIO
    # =====================================

    "-map", "0:a:0?",

    # Audio only is encoded.
    "-c:a", "aac",
    "-b:a", "128k",
    "-ar", "44100",
    "-ac", "2",

    # Keep audio synchronized.
    "-af",
    "aresample=async=1000:min_hard_comp=0.100000:first_pts=0",

    # =====================================
    # OUTPUT
    # =====================================

    "-flush_packets", "1",

    "-flvflags", "no_duration_filesize",

    "-f", "flv",

    YOUTUBE_RTMP
]


streamlink_process = None
ffmpeg_process = None
stopping = False


def stop_process(process, name="process"):

    if process is None:
        return

    if process.poll() is not None:
        return

    print(f"Stopping {name}...")

    try:
        process.terminate()
        process.wait(timeout=5)

    except subprocess.TimeoutExpired:

        print(f"{name} did not stop. Killing it...")

        try:
            process.kill()
            process.wait(timeout=3)
        except Exception:
            pass

    except Exception as e:

        print(f"Error stopping {name}: {e}")

        try:
            process.kill()
        except Exception:
            pass


def cleanup():

    global streamlink_process
    global ffmpeg_process

    stop_process(ffmpeg_process, "FFmpeg")
    stop_process(streamlink_process, "Streamlink")

    ffmpeg_process = None
    streamlink_process = None


def signal_handler(sig, frame):

    global stopping

    stopping = True

    print("\nStopping stream...")

    cleanup()

    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


while not stopping:

    try:

        print("\n========================================")
        print("TikTok -> YouTube Persistent Relay")
        print("Quality: BEST")
        print("Video: COPY")
        print("Video Encoding: OFF")
        print("Crop: OFF")
        print("Resize: OFF")
        print("FPS Conversion: OFF")
        print("Audio: AAC 128k")
        print("Timebase: COPY")
        print("Avoid Negative TS: make_zero")
        print("Auto Reconnect: ON")
        print("Retry Max: 50")
        print("========================================\n")


        # =====================================
        # START STREAMLINK
        # =====================================

        streamlink_process = subprocess.Popen(
            STREAMLINK_CMD,
            stdout=subprocess.PIPE,
            stderr=None,
            bufsize=0
        )


        # =====================================
        # START FFMPEG
        # =====================================

        ffmpeg_process = subprocess.Popen(
            FFMPEG_CMD,
            stdin=streamlink_process.stdout,
            stdout=None,
            stderr=None,
            bufsize=0
        )


        # Close parent copy of pipe.
        streamlink_process.stdout.close()


        # =====================================
        # MONITOR BOTH PROCESSES
        # =====================================

        while not stopping:

            ffmpeg_return = ffmpeg_process.poll()
            streamlink_return = streamlink_process.poll()


            # FFmpeg stopped
            if ffmpeg_return is not None:

                print(
                    f"\nFFmpeg stopped "
                    f"(exit code: {ffmpeg_return})"
                )

                break


            # Streamlink stopped
            if streamlink_return is not None:

                print(
                    f"\nStreamlink stopped "
                    f"(exit code: {streamlink_return})"
                )

                break


            time.sleep(1)


        if stopping:
            break


        print("\n========================================")
        print("Live session ended.")
        print(
            f"FFmpeg exit code: "
            f"{ffmpeg_process.poll()}"
        )
        print(
            f"Streamlink exit code: "
            f"{streamlink_process.poll()}"
        )
        print("Restarting automatically...")
        print("========================================\n")


    except KeyboardInterrupt:

        stopping = True
        cleanup()
        break


    except BrokenPipeError:

        print("\nBroken pipe detected.")
        cleanup()


    except OSError as e:

        print(f"\nOS error: {e}")
        cleanup()


    except Exception as e:

        print(f"\nUnexpected error: {e}")
        cleanup()


    finally:

        if not stopping:
            cleanup()


    if not stopping:

        print(
            "\nWaiting 3 seconds before "
            "searching for the next LIVE..."
        )

        time.sleep(3)
