import os
import subprocess
import time
import signal
import sys

TIKTOK_URL = "https://www.tiktok.com/@c.ahmed.h/live"
YOUTUBE_STREAM_KEY = "4jvb-dz1u-km9t-6gxk-1yex"
YOUTUBE_RTMP = f"rtmp://a.rtmp.youtube.com/live2/{YOUTUBE_STREAM_KEY}"

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
    "-thread_queue_size", "2048",
    "-use_wallclock_as_timestamps", "1",
    "-avoid_negative_ts", "make_zero",
    "-copytb", "1",
    "-fflags", "+genpts+discardcorrupt+nobuffer",
    "-err_detect", "ignore_err",
    "-i", "-",
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
    global streamlink_process, ffmpeg_process
    
    stop_process(ffmpeg_process, "FFmpeg")
    stop_process(streamlink_process, "Streamlink")

    if streamlink_process and streamlink_process.stdout:
        try:
            streamlink_process.stdout.close()
        except Exception:
            pass

    ffmpeg_process = None
    streamlink_process = None

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
        print("TikTok -> YouTube Persistent Relay")
        print("Auto Reconnect & Cleanup: ACTIVE")
        print("========================================\n")

        cleanup()

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

        try:
            streamlink_process.stdout.close()
        except Exception:
            pass

        while not stopping:
            ffmpeg_return = ffmpeg_process.poll()
            streamlink_return = streamlink_process.poll()

            if ffmpeg_return is not None:
                print(f"\nFFmpeg stopped (exit code: {ffmpeg_return})")
                break

            if streamlink_return is not None:
                print(f"\nStreamlink stopped (exit code: {streamlink_return})")
                break

            time.sleep(1)

        if stopping:
            break

        print("\n========================================")
        print("Live session ended or disconnected.")
        print("Cleaning up processes before restart...")
        print("========================================\n")
        
        cleanup()

    except KeyboardInterrupt:
        stopping = True
        cleanup()
        break
    except Exception as e:
        print(f"\nUnexpected error in main loop: {e}")
        cleanup()

    if not stopping:
        print("\nWaiting 10 seconds before searching for the LIVE again...")
        time.sleep(10)
