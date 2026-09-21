import os
import subprocess
import time
import signal
import sys
from streamlink import Streamlink

TIKTOK_URL = "https://www.tiktok.com/@c.ahmed.h/live"
YOUTUBE_STREAM_KEY = "4jvb-dz1u-km9t-6gxk-1yex"

session = Streamlink()
session.set_option("http-headers", {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.tiktok.com/"
})

ffmpeg_process = None
stopping = False

def get_live_stream_url(tiktok_url):
    try:
        streams = session.streams(tiktok_url)
        if "best" in streams:
            return streams["best"].url
        elif "live" in streams:
            return streams["live"].url
    except Exception as e:
        print(f"Error fetching TikTok stream: {e}")
    return None

def stop_process(process, name="process"):
    if process is None:
        return
    if process.poll() is not None:
        return

    print(f"Stopping {name}...")
    try:
        process.terminate()
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        print(f"{name} did not stop. Killing it forcefully...")
        try:
            process.kill()
            process.wait(timeout=2)
        except Exception:
            pass
    except Exception as e:
        print(f"Error stopping {name}: {e}")
        try:
            process.kill()
        except Exception:
            pass

def cleanup():
    global ffmpeg_process
    stop_process(ffmpeg_process, "FFmpeg")
    ffmpeg_process = None

def signal_handler(sig, frame):
    global stopping
    stopping = True
    print("\nStopping stream gracefully...")
    cleanup()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

while not stopping:
    try:
        print("\n========================================")
        print("Searching for TikTok LIVE...")
        print("========================================\n")

        cleanup()

        stream_url = get_live_stream_url(TIKTOK_URL)

        if stream_url:
            print("LIVE detected! Starting FFmpeg relay...")

            ffmpeg_cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "warning",
                "-stats",
                "-thread_queue_size", "2048",
                "-use_wallclock_as_timestamps", "1",
                "-avoid_negative_ts", "make_zero",
                "-copytb", "1",
                "-fflags", "+genpts+discardcorrupt+nobuffer",
                "-err_detect", "ignore_err",
                "-i", stream_url,
                "-map", "0:v:0",
                "-c:v", "copy",
                "-fps_mode", "passthrough",
                "-map", "0:a:0?",
                "-c:a", "aac",
                "-b:a", "128k",
                "-ar", "44100",
                "-ac", "2",
                "-af", "aresample=async=1000:min_hard_comp=0.100000:first_pts=0",
                "-flush_packets", "1",
                "-flvflags", "no_duration_filesize",
                "-f", "flv",
                f"rtmp://a.rtmp.youtube.com/live2/{YOUTUBE_STREAM_KEY}"
            ]

            ffmpeg_process = subprocess.Popen(ffmpeg_cmd)

            while not stopping:
                ffmpeg_return = ffmpeg_process.poll()
                if ffmpeg_return is not None:
                    print(f"\nFFmpeg stopped (exit code: {ffmpeg_return})")
                    break
                time.sleep(2)
        else:
            print("No active LIVE found or TikTok blocked the request.")

        if stopping:
            break

        cleanup()

    except KeyboardInterrupt:
        stopping = True
        cleanup()
        break
    except Exception as e:
        print(f"\nUnexpected error in main loop: {e}")
        cleanup()

    if not stopping:
        print("\nWaiting 15 seconds before checking again...")
        time.sleep(15)
