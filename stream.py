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
    "-loglevel", "warning",
    "-stats",
    "-thread_queue_size", "512",
    "-i", "-",
    "-c:v", "copy",
    "-c:a", "copy",
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
    streamlink_process = subprocess.Popen(
        STREAMLINK_CMD,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0
    )

    time.sleep(3)

    if streamlink_process.poll() is not None:
        sys.exit(1)

    ffmpeg_process = subprocess.Popen(
        FFMPEG_CMD,
        stdin=streamlink_process.stdout,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        bufsize=0
    )

    streamlink_process.stdout.close()
    ffmpeg_process.wait()

except Exception:
    pass
finally:
    cleanup()
