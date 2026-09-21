import os
import subprocess
import time
import signal
import sys

TIKTOK_URL = "https://www.tiktok.com/@c.ahmed.h/live"

YOUTUBE_RTMP = "rtmp://a.rtmp.youtube.com/live2/4jvb-dz1u-km9t-6gxk-1yex"


STREAMLINK_CMD = [
    "streamlink",
    "--hls-live-edge", "2",
    "--ringbuffer-size", "512M",
    "--retry-streams", "10",
    "--retry-max", "0",
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

    "-dts_delta_threshold", "1",
    "-fflags", "+genpts+discardcorrupt",
    "-err_detect", "ignore_err",

    "-thread_queue_size", "1024",
    "-i", "-",

    "-map", "0:v:0",
    "-c:v", "copy",

    "-map", "0:a:0?",
    "-c:a", "aac",
    "-b:a", "128k",
    "-ar", "44100",
    "-ac", "2",
    "-af", "aresample=async=1000:min_hard_comp=0.100000:first_pts=0",

    "-fps_mode", "passthrough",
    "-flush_packets", "1",

    "-flvflags", "no_duration_filesize",

    "-f", "flv",
    YOUTUBE_RTMP
]


streamlink_process = None
ffmpeg_process = None


def stop_process(process):
    if process and process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            try:
                process.kill()
                process.wait(timeout=3)
            except Exception:
                pass


def cleanup():
    global streamlink_process, ffmpeg_process

    print("\nStopping processes...")

    stop_process(ffmpeg_process)
    stop_process(streamlink_process)

    streamlink_process = None
    ffmpeg_process = None


def signal_handler(sig, frame):
    print("\nStopped by user.")
    cleanup()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


while True:
    try:
        print("\n========================================")
        print("Starting TikTok -> YouTube stream...")
        print("Quality: BEST")
        print("Video: COPY (NO RE-ENCODE)")
        print("Timestamp correction: ON")
        print("Crop: OFF")
        print("Resize: OFF")
        print("========================================\n")

        streamlink_process = subprocess.Popen(
            STREAMLINK_CMD,
            stdout=subprocess.PIPE,
            stderr=None,
            bufsize=0
        )

        ffmpeg_process = subprocess.Popen(
            FFMPEG_CMD,
            stdin=streamlink_process.stdout,
            stdout=None,
            stderr=None,
            bufsize=0
        )

        streamlink_process.stdout.close()

        ffmpeg_return = ffmpeg_process.wait()

        if streamlink_process and streamlink_process.poll() is None:
            stop_process(streamlink_process)

        streamlink_return = (
            streamlink_process.poll()
            if streamlink_process
            else "N/A"
        )

        print("\n========================================")
        print("Stream stopped.")
        print(f"FFmpeg exit code: {ffmpeg_return}")
        print(f"Streamlink exit code: {streamlink_return}")
        print("Restarting in 1 second...")
        print("========================================\n")

    except KeyboardInterrupt:
        cleanup()
        break

    except BrokenPipeError:
        print("\nBroken pipe detected.")

    except OSError as e:
        print(f"\nOS error: {e}")

    except Exception as e:
        print(f"\nError: {e}")

    finally:
        cleanup()

    time.sleep(50)
