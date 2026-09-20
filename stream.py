import os
import subprocess
import threading
import time
import signal
import sys

TIKTOK_URL = "https://www.tiktok.com/@.31342257/live"
YOUTUBE_RTMP = "rtmp://a.rtmp.youtube.com/live2/8yjs-eb3y-wt8s-y45e-ezsu"

COPY_AUDIO = False

STALL_TIMEOUT = 30
WATCHDOG_INTERVAL = 5
MAX_MUXING_QUEUE_SIZE = 4096

STREAMLINK_CMD = [
    "streamlink",
    "--hls-live-edge", "4",
    "--ringbuffer-size", "512M",
    "--stream-segment-attempts", "5",
    "--stream-segment-timeout", "10",
    "--stream-timeout", "15",
    "--stdout",
    TIKTOK_URL,
    "best"
]

def build_ffmpeg_cmd(copy_audio: bool):
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "warning",
        "-stats",
        "-nostdin",
        "-threads", "1",

        "-dts_delta_threshold", "10",
        "-fflags", "+genpts+discardcorrupt+nobuffer",
        "-err_detect", "ignore_err",

        "-thread_queue_size", "2048",
        "-i", "-",

        "-map", "0:v:0",
        "-c:v", "copy",
        "-map", "0:a:0?",
    ]

    if copy_audio:
        cmd += ["-c:a", "copy", "-bsf:a", "aac_adtstoasc"]
    else:
        cmd += [
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "44100",
            "-ac", "2",
            "-af", "aresample=async=1000:min_hard_comp=0.100000:first_pts=0",
        ]

    cmd += [
        "-fps_mode", "passthrough",
        "-flush_packets", "1",
        "-max_muxing_queue_size", str(MAX_MUXING_QUEUE_SIZE),
        "-flvflags", "no_duration_filesize",
        "-f", "flv",
        YOUTUBE_RTMP
    ]

    return cmd

streamlink_process = None
ffmpeg_process = None

_last_progress_lock = threading.Lock()
_last_progress_time = [0.0]
_watchdog_stop = threading.Event()

def _mark_progress():
    with _last_progress_lock:
        _last_progress_time[0] = time.time()

def _seconds_since_progress():
    with _last_progress_lock:
        return time.time() - _last_progress_time[0]

def stderr_reader(proc):
    try:
        for raw_line in iter(proc.stderr.readline, b""):
            if not raw_line:
                break
            line = raw_line.decode(errors="replace").rstrip()
            if line:
                print(line, file=sys.stderr, flush=True)
                _mark_progress()
    except Exception:
        pass

def watchdog(proc):
    while not _watchdog_stop.is_set():
        if proc.poll() is not None:
            return
        if _seconds_since_progress() > STALL_TIMEOUT:
            print(
                f"\nNo progress for over {STALL_TIMEOUT}s — pipeline looks frozen, forcing restart...",
                flush=True,
            )
            stop_process(proc)
            return
        _watchdog_stop.wait(WATCHDOG_INTERVAL)

def stop_process(process):
    if process and process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=3)
        except Exception:
            try:
                process.kill()
                process.wait(timeout=2)
            except Exception:
                pass

def cleanup():
    global streamlink_process, ffmpeg_process
    stop_process(ffmpeg_process)
    stop_process(streamlink_process)
    streamlink_process = None
    ffmpeg_process = None

def signal_handler(sig, frame):
    _watchdog_stop.set()
    cleanup()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

while True:
    try:
        ffmpeg_cmd = build_ffmpeg_cmd(COPY_AUDIO)
        _watchdog_stop.clear()
        _mark_progress()

        streamlink_process = subprocess.Popen(
            STREAMLINK_CMD,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0
        )

        ffmpeg_process = subprocess.Popen(
            ffmpeg_cmd,
            stdin=streamlink_process.stdout,
            stdout=None,
            stderr=subprocess.PIPE,
            bufsize=0
        )

        streamlink_process.stdout.close()

        reader_thread = threading.Thread(
            target=stderr_reader, args=(ffmpeg_process,), daemon=True
        )
        reader_thread.start()

        watchdog_thread = threading.Thread(
            target=watchdog, args=(ffmpeg_process,), daemon=True
        )
        watchdog_thread.start()

        ffmpeg_process.wait()

    except Exception as e:
        print(f"\nError: {e}")
    finally:
        _watchdog_stop.set()
        cleanup()

    time.sleep(0.5)
