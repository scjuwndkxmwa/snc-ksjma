import os
import subprocess
import time
import signal
import sys

YOUTUBE_VIDEO_URL = "https://youtu.be/mtKF4rn6SLM"
YOUTUBE_STREAM_KEY = "r77y-h37m-x6xr-x0dj-0g6q"

YOUTUBE_RTMP_DESTINATION = f"rtmp://a.rtmp.youtube.com/live2/{YOUTUBE_STREAM_KEY}"

def get_stream_urls(video_url):
    print("[INFO] Extracting Video & Audio URLs via yt-dlp (Android Client)...")
    cmd = [
        "yt-dlp",
        "-g",
        "-f", "bv*+ba/b",
        "--extractor-args", "youtube:player_client=android",
        "--no-check-certificates",
        video_url
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode == 0:
        urls = result.stdout.strip().split('\n')
        return urls
    else:
        print(f"[ERROR] yt-dlp failed: {result.stderr}")
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
    urls = get_stream_urls(YOUTUBE_VIDEO_URL)
    if not urls:
        print("[ERROR] Could not extract links.")
        sys.exit(1)

    if len(urls) == 2:
        video_url, audio_url = urls[0], urls[1]
        FFMPEG_CMD = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-re",
            "-i", video_url,
            "-i", audio_url,
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
    else:
        video_url = urls[0]
        FFMPEG_CMD = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-re",
            "-i", video_url,
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

    print("[INFO] Starting FFmpeg live stream...")
    ffmpeg_process = subprocess.Popen(
        FFMPEG_CMD,
        stdout=sys.stdout,
        stderr=sys.stderr
    )

    ffmpeg_process.wait()

except Exception as e:
    print(f"[ERROR] Exception: {e}")
finally:
    cleanup()
