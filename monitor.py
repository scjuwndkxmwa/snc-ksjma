import os
import subprocess
import time
import signal
import sys

TIKTOK_URL = os.environ.get("TIKTOK_URL", "https://www.tiktok.com/@abdullahal3085/live")
YOUTUBE_RTMP = os.environ.get("YOUTUBE_RTMP", "rtmp://a.rtmp.youtube.com/live2/r77y-h37m-x6xr-x0dj-0g6q")

STREAMLINK_CMD = [
    "streamlink",
    "--hls-live-edge", "2",
    "--ringbuffer-size", "512M",
    "--retry-streams", "0",
    "--retry-max", "0",
    "--stream-timeout", "5",
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
            process.wait(timeout=2)
        except Exception:
            try:
                process.kill()
                process.wait(timeout=1)
            except Exception:
                pass


def cleanup():
    global streamlink_process, ffmpeg_process
    stop_process(ffmpeg_process)
    stop_process(streamlink_process)
    streamlink_process = None
    ffmpeg_process = None


def signal_handler(sig, frame):
    cleanup()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def run_once():
    global streamlink_process, ffmpeg_process

    try:
        cleanup()
        
        streamlink_process = subprocess.Popen(
            STREAMLINK_CMD,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0
        )

        time.sleep(2)
        
        if streamlink_process.poll() is not None:
            print(f"[{time.strftime('%H:%M:%S')}] Stream offline or closed. Exiting stream.py immediately.")
            return

        print(f"[{time.strftime('%H:%M:%S')}] Stream active! Piping to YouTube...")
        
        ffmpeg_process = subprocess.Popen(
            FFMPEG_CMD,
            stdin=streamlink_process.stdout,
            stdout=None,
            stderr=None,
            bufsize=0
        )

        streamlink_process.stdout.close()

        ffmpeg_process.wait()
        
        print(f"[{time.strftime('%H:%M:%S')}] Stream ended. Terminating stream.py completely.")

    except Exception as e:
        print(f"[STREAM ERROR] {e}")

    finally:
        cleanup()
        sys.exit(0)


if __name__ == "__main__":
    run_once()
