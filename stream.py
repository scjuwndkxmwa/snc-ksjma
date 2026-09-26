import os
import subprocess
import time
import signal
import sys

YOUTUBE_CHANNEL_URL = "https://www.youtube.com/@Yasseraldosry/live"
RESTREAM_KEY = os.getenv("RESTREAM_KEY", "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9")
RESTREAM_RTMP_DESTINATION = f"rtmp://live.restream.io/live/{RESTREAM_KEY}"

def get_streamlink_url():
    print("[+] Extracting stream URL from channel...", flush=True)
    cmd = [
        "streamlink",
        "--stream-url",
        YOUTUBE_CHANNEL_URL,
        "best,720p,480p,worst"
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    else:
        print(f"[-] Streamlink failed: {result.stderr.strip()}", flush=True)
        return None

ffmpeg_process = None

def cleanup():
    global ffmpeg_process
    if ffmpeg_process and ffmpeg_process.poll() is None:
        try:
            ffmpeg_process.terminate()
            ffmpeg_process.wait(timeout=2)
        except Exception:
            ffmpeg_process.kill()
    ffmpeg_process = None

def signal_handler(sig, frame):
    cleanup()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

print("[+] Script initialized and running...", flush=True)

while True:
    stream_url = get_streamlink_url()
    if not stream_url:
        print("[-] Retrying channel stream extraction in 10 seconds...", flush=True)
        time.sleep(10)
        continue

    print("[+] Stream URL obtained. Launching FFmpeg to Restream...", flush=True)

    FFMPEG_CMD = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "warning",
        "-re",
        "-i", stream_url,
        "-c:v", "copy",
        "-c:a", "copy",
        "-f", "flv",
        RESTREAM_RTMP_DESTINATION
    ]

    try:
        ffmpeg_process = subprocess.Popen(FFMPEG_CMD, stdout=sys.stdout, stderr=sys.stderr)
        ffmpeg_process.wait()
        print("[-] FFmpeg process exited.", flush=True)
    except Exception as e:
        print(f"[-] FFmpeg error: {e}", flush=True)
    finally:
        cleanup()

    time.sleep(5)
