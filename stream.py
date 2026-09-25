import os
import subprocess
import time
import signal
import sys

YOUTUBE_VIDEO_URL = "https://youtu.be/mtKF4rn6SLM"
YOUTUBE_STREAM_KEY = "r77y-h37m-x6xr-x0dj-0g6q"

YOUTUBE_RTMP_DESTINATION = f"rtmp://a.rtmp.youtube.com/live2/{YOUTUBE_STREAM_KEY}"

STREAMLINK_CMD = [
    "streamlink",
    "--hls-live-edge", "2",
    "--ringbuffer-size", "32M",
    "--stdout",
    YOUTUBE_VIDEO_URL,
    "best"
]

FFMPEG_CMD = [
    "ffmpeg",
    "-hide_banner",
    "-loglevel", "info",
    "-thread_queue_size", "512",
    "-i", "-",
    "-c:v", "libx264",
    "-preset", "veryfast",
    "-maxrate", "3000k",
    "-bufsize", "6000k",
    "-pix_fmt", "yuv420p",
    "-g", "60",
    "-c:a", "aac",
    "-b:a", "128k",
    "-ar", "44100",
    "-f", "flv",
    YOUTUBE_RTMP_DESTINATION
]

streamlink_process = None
ffmpeg_process = None

def kill_forcefully(p):
    if p is not None:
        try:
            if p.poll() is None:
                p.terminate()
                p.wait(timeout=2)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass

def cleanup():
    global streamlink_process, ffmpeg_process
    kill_forcefully(ffmpeg_process)
    kill_forcefully(streamlink_process)
    streamlink_process = None
    ffmpeg_process = None

def signal_handler(sig, frame):
    cleanup()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

try:
    print("[INFO] Starting Streamlink...")
    streamlink_process = subprocess.Popen(
        STREAMLINK_CMD,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        bufsize=0
    )

    time.sleep(3)

    if streamlink_process.poll() is not None:
        print("[ERROR] Streamlink failed to start.")
        sys.exit(1)

    print("[INFO] Starting FFmpeg...")
    ffmpeg_process = subprocess.Popen(
        FFMPEG_CMD,
        stdin=streamlink_process.stdout,
        stdout=sys.stdout,
        stderr=sys.stderr,
        bufsize=0
    )

    streamlink_process.stdout.close()
    ffmpeg_process.wait()

except Exception as e:
    print(f"[ERROR] Exception: {e}")
finally:
    cleanup()
