import os
import sys
import time
import signal
import subprocess


# ============================================================
# CONFIG
# ============================================================

YOUTUBE_URL = "https://www.youtube.com/live/7DHNbnPMNiM"

# Restream Stream Key
RESTREAM_STREAM_KEY = "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9"

# Restream RTMP server
RESTREAM_RTMP = f"rtmp://live.restream.io/live/{RESTREAM_STREAM_KEY}"


# ============================================================
# STREAM SETTINGS
# ============================================================

VIDEO_MODE = "COPY"
VIDEO_ENCODE = False

AUDIO_CODEC = "aac"
AUDIO_BITRATE = "128k"
AUDIO_RATE = "44100"
AUDIO_CHANNELS = "2"

COOKIES_ENABLED = False

# Highest available YouTube quality
STREAM_QUALITY = "best"

# Streamlink buffering / retry
RINGBUFFER_SIZE = "128M"
HLS_LIVE_EDGE = "3"

STREAM_SEGMENT_ATTEMPTS = "10"
STREAM_SEGMENT_TIMEOUT = "15"
STREAM_TIMEOUT = "60"

# Retry finding the live stream
RETRY_STREAMS = "10"
RETRY_MAX = "0"

# Wait between complete relay restarts
RESTART_DELAY = 5


# ============================================================
# PROCESS STATE
# ============================================================

streamlink_process = None
ffmpeg_process = None

shutdown_requested = False


# ============================================================
# LOGGING
# ============================================================

def log(message):
    print(message, flush=True)


# ============================================================
# SIGNAL HANDLER
# ============================================================

def signal_handler(signum, frame):
    global shutdown_requested

    if shutdown_requested:
        return

    shutdown_requested = True

    log("")
    log("[SYSTEM] Shutdown requested...")

    stop_processes()


# ============================================================
# STOP PROCESSES
# ============================================================

def stop_process(process, name):
    if process is None:
        return

    try:
        if process.poll() is None:
            log(f"[SYSTEM] Stopping {name}...")

            process.terminate()

            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                log(f"[SYSTEM] Killing {name}...")
                process.kill()

                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass

    except Exception as e:
        log(f"[SYSTEM] Error stopping {name}: {e}")


def stop_processes():
    global streamlink_process
    global ffmpeg_process

    stop_process(ffmpeg_process, "FFmpeg")
    stop_process(streamlink_process, "Streamlink")

    ffmpeg_process = None
    streamlink_process = None


# ============================================================
# START STREAMLINK
# ============================================================

def start_streamlink():
    global streamlink_process

    log("[SYSTEM] Starting Streamlink...")
    log("[SYSTEM] Cookies: OFF")
    log("[SYSTEM] Waiting for YouTube stream data...")

    command = [
        "streamlink",

        "--stdout",

        "--hls-live-edge",
        HLS_LIVE_EDGE,

        "--ringbuffer-size",
        RINGBUFFER_SIZE,

        "--retry-streams",
        RETRY_STREAMS,

        "--retry-max",
        RETRY_MAX,

        "--retry-open",
        "5",

        "--stream-segment-attempts",
        STREAM_SEGMENT_ATTEMPTS,

        "--stream-segment-timeout",
        STREAM_SEGMENT_TIMEOUT,

        "--stream-timeout",
        STREAM_TIMEOUT,

        "--hls-playlist-reload-attempts",
        "10",

        YOUTUBE_URL,
        STREAM_QUALITY
    ]

    try:
        streamlink_process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0
        )

        return streamlink_process

    except Exception as e:
        log(f"[ERROR] Could not start Streamlink: {e}")
        return None


# ============================================================
# START FFMPEG
# ============================================================

def start_ffmpeg(streamlink):
    global ffmpeg_process

    log("[SYSTEM] Starting FFmpeg...")
    log("[SYSTEM] Video: COPY")
    log("[SYSTEM] Video Encode: OFF")
    log("[SYSTEM] Audio: AAC 128k")
    log("[SYSTEM] Sending stream to Restream...")

    command = [
        "ffmpeg",

        "-hide_banner",
        "-loglevel",
        "warning",
        "-stats",

        # Input
        "-thread_queue_size",
        "1024",

        "-i",
        "pipe:0",

        # Generate clean timestamps
        "-fflags",
        "+genpts+discardcorrupt",

        "-err_detect",
        "ignore_err",

        # Keep video exactly as received
        "-map",
        "0:v:0",

        "-c:v",
        "copy",

        # Audio is re-encoded
        "-map",
        "0:a:0?",

        "-c:a",
        AUDIO_CODEC,

        "-b:a",
        AUDIO_BITRATE,

        "-ar",
        AUDIO_RATE,

        "-ac",
        AUDIO_CHANNELS,

        # Audio timestamp correction
        "-af",
        "aresample=async=1000:min_hard_comp=0.100000:first_pts=0",

        # FLV / RTMP
        "-f",
        "flv",

        RESTREAM_RTMP
    ]

    try:
        ffmpeg_process = subprocess.Popen(
            command,
            stdin=streamlink.stdout,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            bufsize=0
        )

        return ffmpeg_process

    except Exception as e:
        log(f"[ERROR] Could not start FFmpeg: {e}")
        return None


# ============================================================
# READ STDERR WITHOUT BLOCKING
# ============================================================

def read_streamlink_errors():
    if streamlink_process is None:
        return

    try:
        while True:
            line = streamlink_process.stderr.readline()

            if not line:
                break

            text = line.decode(
                "utf-8",
                errors="replace"
            ).strip()

            if text:
                log(text)

    except Exception:
        pass


def read_ffmpeg_errors():
    if ffmpeg_process is None:
        return

    try:
        while True:
            line = ffmpeg_process.stderr.readline()

            if not line:
                break

            text = line.decode(
                "utf-8",
                errors="replace"
            ).strip()

            if text:
                log(text)

    except Exception:
        pass


# ============================================================
# RUN ONE RELAY SESSION
# ============================================================

def run_session():
    global streamlink_process
    global ffmpeg_process

    streamlink_process = None
    ffmpeg_process = None

    log("")
    log("=" * 60)
    log("[SYSTEM] Starting relay session")
    log("=" * 60)

    # --------------------------------------------------------
    # Start Streamlink
    # --------------------------------------------------------

    streamlink_process = start_streamlink()

    if streamlink_process is None:
        return False

    # --------------------------------------------------------
    # Wait for Streamlink output
    # --------------------------------------------------------

    log("[SYSTEM] Waiting for REAL YouTube stream data...")

    start_time = time.time()

    while not shutdown_requested:

        # Streamlink died
        if streamlink_process.poll() is not None:

            read_streamlink_errors()

            log(
                f"[SYSTEM] Streamlink exited "
                f"with code {streamlink_process.returncode}"
            )

            return False

        # Start FFmpeg once Streamlink has actual output
        try:
            first_data = streamlink_process.stdout.peek(1)

            if first_data:
                break

        except Exception:
            break

        # Don't block forever
        if time.time() - start_time > 120:

            log(
                "[SYSTEM] YouTube stream did not provide "
                "data within 120 seconds."
            )

            return False

        time.sleep(0.2)

    if shutdown_requested:
        return False

    log("[SYSTEM] YouTube stream detected.")

    # --------------------------------------------------------
    # Start FFmpeg
    # --------------------------------------------------------

    ffmpeg_process = start_ffmpeg(streamlink_process)

    if ffmpeg_process is None:
        return False

    log("[SYSTEM] Stream is RUNNING.")

    # Close parent copy of stdout after handing it to FFmpeg
    try:
        streamlink_process.stdout.close()
    except Exception:
        pass

    # --------------------------------------------------------
    # Monitor both processes
    # --------------------------------------------------------

    while not shutdown_requested:

        streamlink_code = streamlink_process.poll()
        ffmpeg_code = ffmpeg_process.poll()

        # FFmpeg stopped
        if ffmpeg_code is not None:

            log(
                f"[SYSTEM] FFmpeg stopped "
                f"with code {ffmpeg_code}"
            )

            read_ffmpeg_errors()

            return False

        # Streamlink stopped
        if streamlink_code is not None:

            log(
                f"[SYSTEM] Streamlink stopped "
                f"with code {streamlink_code}"
            )

            read_streamlink_errors()

            # FFmpeg should eventually receive EOF.
            # Stop it ourselves to restart the complete pipeline.
            return False

        time.sleep(1)

    return False


# ============================================================
# MAIN 24/7 LOOP
# ============================================================

def main():

    global shutdown_requested

    log("")
    log("=" * 60)
    log("       YouTube 24/7 -> Restream -> TikTok")
    log("=" * 60)

    log(f"YouTube        : {YOUTUBE_URL}")
    log("Destination    : Restream")
    log("Cookies        : OFF")
    log("Video          : COPY")
    log("Video Encode   : OFF")
    log("Crop           : OFF")
   
