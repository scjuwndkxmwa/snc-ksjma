import subprocess
import time
import signal
import sys

TIKTOK_URL = "https://www.tiktok.com/@.31342257/live"
YOUTUBE_RTMP = "rtmp://a.rtmp.youtube.com/live2/4vm5-3h9h-1t7u-a7aa-0e57"

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

    "-f", "flv",
    YOUTUBE_RTMP
]


streamlink_process = None
ffmpeg_process = None


def cleanup():
    global streamlink_process, ffmpeg_process

    print("\nStopping processes...")

    if ffmpeg_process and ffmpeg_process.poll() is None:
        try:
            ffmpeg_process.terminate()
            ffmpeg_process.wait(timeout=5)
        except:
            try:
                ffmpeg_process.kill()
            except:
                pass

    if streamlink_process and streamlink_process.poll() is None:
        try:
            streamlink_process.terminate()
            streamlink_process.wait(timeout=5)
        except:
            try:
                streamlink_process.kill()
            except:
                pass

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
        print("Quality: BEST / ORIGIN")
        print("Video: COPY (NO RE-ENCODE)")
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
            try:
                streamlink_process.terminate()
                streamlink_process.wait(timeout=3)
            except:
                try:
                    streamlink_process.kill()
                except:
                    pass

        streamlink_return = streamlink_process.poll() if streamlink_process else "N/A"

        print("\n========================================")
        print("Stream stopped.")
        print(f"FFmpeg exit code: {ffmpeg_return}")
        print(f"Streamlink exit code: {streamlink_return}")
        print("Reconnecting immediately in 1 second...")
        print("========================================\n")

    except KeyboardInterrupt:
        cleanup()
        break

    except Exception as e:
        print(f"\nError: {e}")

    finally:
        cleanup()

    time.sleep(1)
