import os
import subprocess
import time
import signal
import sys

TIKTOK_URL = "https://www.tiktok.com/@abdullahal3085/live"
YOUTUBE_RTMP = "rtmp://a.rtmp.youtube.com/live2/r77y-h37m-x6xr-x0dj-0g6q"

CHECK_INTERVAL_OFFLINE = 30  

STREAMLINK_CMD = [
    "streamlink",
    "--hls-live-edge", "2",
    "--ringbuffer-size", "512M",
    "--retry-streams", "2",
    "--retry-max", "2",
    "--stream-segment-attempts", "5",
    "--stream-segment-timeout", "15",
    "--stream-timeout", "30",
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

    "-rw_timeout", "10000000",

    "-f", "flv",
    YOUTUBE_RTMP
]

streamlink_process = None
ffmpeg_process = None


def reset_youtube_session(rtmp_url):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [RTMP RESET] Resetting YouTube session...", flush=True)
    
    dummy_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "quiet",
        "-f", "lavfi", "-i", "color=c=black:s=320x240:r=10",
        "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
        "-c:a", "aac",
        "-f", "flv",
        rtmp_url
    ]
    
    try:
        p = subprocess.Popen(dummy_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
        p.kill()
        p.wait()
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [RTMP RESET] Session cleared successfully.", flush=True)
    except Exception as e:
        print(f"[RTMP RESET Warning] Could not reset session: {e}", flush=True)
    
    time.sleep(2)


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
    stop_process(ffmpeg_process)
    stop_process(streamlink_process)
    streamlink_process = None
    ffmpeg_process = None


def signal_handler(sig, frame):
    print("\n[SYSTEM] Stopped by Railway / User.", flush=True)
    cleanup()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


print("========================================", flush=True)
print("TikTok Live Monitor & Auto-Restreamer", flush=True)
print("Status: RUNNING & LISTENING...", flush=True)
print("========================================\n", flush=True)

while True:
    try:
        cleanup()
        
        streamlink_process = subprocess.Popen(
            STREAMLINK_CMD,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0
        )

        time.sleep(3)
        
        if streamlink_process.poll() is not None:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Stream is OFFLINE. Re-checking in {CHECK_INTERVAL_OFFLINE} seconds...", flush=True)
            cleanup()
            time.sleep(CHECK_INTERVAL_OFFLINE)
            continue

        print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Stream ONLINE!", flush=True)
        
        reset_youtube_session(YOUTUBE_RTMP)

        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting Restream to YouTube...", flush=True)
        ffmpeg_process = subprocess.Popen(
            FFMPEG_CMD,
            stdin=streamlink_process.stdout,
            stdout=None,
            stderr=None,
            bufsize=0
        )

        streamlink_process.stdout.close()

        ffmpeg_return = ffmpeg_process.wait()
        
        print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Stream ended (FFmpeg exit code: {ffmpeg_return}).", flush=True)

    except KeyboardInterrupt:
        print("\nStopping...", flush=True)
        cleanup()
        break

    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}", flush=True)

    finally:
        cleanup()

    print(f"Waiting {CHECK_INTERVAL_OFFLINE} seconds before checking for the next stream...\n", flush=True)
    time.sleep(CHECK_INTERVAL_OFFLINE)
