import os
import subprocess
import time
import signal
import sys

YOUTUBE_VIDEO_URL = "https://youtu.be/mtKF4rn6SLM"
YOUTUBE_STREAM_KEY = "r77y-h37m-x6xr-x0dj-0g6q"

YOUTUBE_RTMP_DESTINATION = f"rtmp://a.rtmp.youtube.com/live2/{YOUTUBE_STREAM_KEY}"

def get_stream_url(video_url):
    cmd = [
        "yt-dlp",
        "-g",
        "-f", "best",
        video_url
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    return None

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
    global ffmpeg_process
    kill_forcefully(ffmpeg_process)
    ffmpeg_process = None

def signal_handler(sig, frame):
    cleanup()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

try:
    direct_url = get_stream_url(YOUTUBE_VIDEO_URL)
    if not direct_url:
        sys.exit(1)

    FFMPEG_CMD = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "warning",
        "-re",
        "-i", direct_url,
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

    ffmpeg_process = subprocess.Popen(
        FFMPEG_CMD,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    ffmpeg_process.wait()

except Exception:
    pass
finally:
    cleanup()
