import os
import sys
import time
import signal
import subprocess


# ============================================================
# CONFIG
# ============================================================

YOUTUBE_URL = "https://www.youtube.com/live/7DHNbnPMNiM"

RESTREAM_RTMP = (
    "rtmp://live.restream.io/live/"
    "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9"
)

QUALITY = "best"

RECONNECT_DELAY = 5

# Streamlink stability
HLS_LIVE_EDGE = 3
RINGBUFFER_SIZE = "128M"

STREAM_SEGMENT_ATTEMPTS = 8
STREAM_SEGMENT_TIMEOUT = 30
STREAM_SEGMENT_THREADS = 2

HLS_PLAYLIST_RELOAD_ATTEMPTS = 8

# FFmpeg
AUDIO_BITRATE = "128k"
AUDIO_SAMPLE_RATE = "44100"

# Graceful shutdown
SHUTDOWN_TIMEOUT = 8


# ============================================================
# GLOBALS
# ============================================================

streamlink_process = None
ffmpeg_process = None

shutdown_requested = False


# ============================================================
# LOGGING
# ============================================================

def log(message):
    print(f"[SYSTEM] {message}", flush=True)


def separator():
    print("=" * 60, flush=True)


# ============================================================
# SIGNAL HANDLER
# ============================================================

def handle_signal(signum, frame):
    global shutdown_requested

    if shutdown_requested:
        return

    shutdown_requested = True

    separator()
    log("Shutdown requested...")
    stop_processes()


# ============================================================
# STOP PROCESS
# ============================================================

def stop_process(process, name):
    if process is None:
        return

    try:
        if process.poll() is None:
            log(f"Stopping {name}...")

            process.terminate()

            try:
                process.wait(timeout=SHUTDOWN_TIMEOUT)
            except subprocess.TimeoutExpired:
                log(f"Killing {name}...")
                process.kill()

                try:
                    process.wait(timeout=3)
                except Exception:
                    pass

    except Exception as e:
        log(f"Error stopping {name}: {e}")


def stop_processes():
    global streamlink_process
    global ffmpeg_process

    stop_process(ffmpeg_process, "FFmpeg")
    stop_process(streamlink_process, "Streamlink")

    ffmpeg_process = None
    streamlink_process = None


# ============================================================
# HEADER
# ============================================================

def print_header():
    separator()
    print("       YouTube LIVE -> Restream", flush=True)
    separator()

    print(f"YouTube        : {YOUTUBE_URL}", flush=True)
    print("Destination    : Restream", flush=True)
    print("Cookies        : OFF", flush=True)
    print("Video          : COPY", flush=True)
    print("Video Encode   : OFF", flush=True)
    print("Crop           : OFF", flush=True)
    print("Resize         : OFF", flush=True)
    print("FPS Convert    : OFF", flush=True)
    print(f"Audio          : AAC {AUDIO_BITRATE}", flush=True)
    print("Auto-Reconnect : ON", flush=True)
    print("Status         : STARTING", flush=True)

    separator()


# ============================================================
# STREAMLINK COMMAND
# ============================================================

def build_streamlink_command():

    return [
        "streamlink",

        # Don't use unsupported old options
        "--no-config",

        # Disable automatic version checking
        "--auto-version-check",
        "no",

        # Output raw stream to stdout
        "--stdout",

        # HLS stability
        "--hls-live-edge",
        str(HLS_LIVE_EDGE),

        "--ringbuffer-size",
        RINGBUFFER_SIZE,

        # Current Streamlink option names
        "--stream-segment-attempts",
        str(STREAM_SEGMENT_ATTEMPTS),

        "--stream-segment-timeout",
        str(STREAM_SEGMENT_TIMEOUT),

        "--stream-segment-threads",
        str(STREAM_SEGMENT_THREADS),

        "--stream-timeout",
        "90",

        "--hls-playlist-reload-attempts",
        str(HLS_PLAYLIST_RELOAD_ATTEMPTS),

        # Retry finding the stream
        "--retry-streams",
        "10",

        "--retry-max",
        "0",

        # YouTube URL
        YOUTUBE_URL,

        # Quality
        QUALITY,
    ]


# ============================================================
# FFMPEG COMMAND
# ============================================================

def build_ffmpeg_command():

    return [
        "ffmpeg",

        "-hide_banner",
        "-loglevel",
        "warning",
        "-stats",

        # Read from Streamlink stdout
        "-thread_queue_size",
        "1024",

        "-i",
        "-",

        # Generate timestamps when possible
        "-fflags",
        "+genpts+discardcorrupt",

        "-err_detect",
        "ignore_err",

        # ----------------------------------------------------
        # VIDEO
        # ----------------------------------------------------

        "-map",
        "0:v:0",

        # IMPORTANT:
        # Video is copied. No re-encoding.
        "-c:v",
        "copy",

        # ----------------------------------------------------
        # AUDIO
        # ----------------------------------------------------

        "-map",
        "0:a:0?",

        "-c:a",
        "aac",

        "-b:a",
        AUDIO_BITRATE,

        "-ar",
        AUDIO_SAMPLE_RATE,

        "-ac",
        "2",

        # Help FFmpeg deal with live audio timestamp changes
        "-af",
        "aresample=async=1000:min_hard_comp=0.100:first_pts=0",

        # ----------------------------------------------------
        # OUTPUT
        # ----------------------------------------------------

        "-f",
        "flv",

        RESTREAM_RTMP,
    ]


# ============================================================
# START STREAMLINK
# ============================================================

def start_streamlink():

    global streamlink_process

    command = build_streamlink_command()

    log("Starting Streamlink...")
    log("Cookies: OFF")
    log(f"Quality: {QUALITY.upper()}")
    log("Video source: COPY")
    log("Waiting for YouTube stream data...")

    try:

        streamlink_process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=None,
            bufsize=0,
        )

    except Exception as e:
        log(f"Failed to start Streamlink: {e}")
        streamlink_process = None
        return False

    time.sleep(1)

    if streamlink_process.poll() is not None:

        log(
            f"Streamlink exited immediately "
            f"(exit code: {streamlink_process.returncode})"
        )

        streamlink_process = None
        return False

    log("Streamlink process is alive.")

    return True


# ============================================================
# START FFMPEG
# ============================================================

def start_ffmpeg():

    global ffmpeg_process

    command = build_ffmpeg_command()

    log("Starting FFmpeg...")
    log("Video: COPY")
    log("Video Encode: OFF")
    log(f"Audio: AAC {AUDIO_BITRATE}")
    log("Sending YouTube -> Restream.")

    try:

        ffmpeg_process = subprocess.Popen(
            command,
            stdin=streamlink_process.stdout,
            stdout=subprocess.DEVNULL,
            stderr=None,
        )

    except Exception as e:

        log(f"Failed to start FFmpeg: {e}")
        ffmpeg_process = None

        return False

    try:
        streamlink_process.stdout.close()
    except Exception:
        pass

    log("FFmpeg is connected to Streamlink.")
    log("Stream is RUNNING.")

    return True


# ============================================================
# RUN ONE RELAY SESSION
# ============================================================

def run_session():

    global streamlink_process
    global ffmpeg_process

    separator()
    log("Starting relay session")
    separator()

    if not start_streamlink():

        stop_processes()

        return False

    # Give Streamlink a moment to establish the stream.
    time.sleep(2)

    if streamlink_process is None:
        return False

    if streamlink_process.poll() is not None:

        log(
            "Streamlink exited before media was available "
            f"(exit code: {streamlink_process.returncode})."
        )

        stop_processes()

        return False

    log("Starting FFmpeg pipeline...")

    if not start_ffmpeg():

        stop_processes()

        return False

    # --------------------------------------------------------
    # Monitor both processes
    # --------------------------------------------------------

    while not shutdown_requested:

        ffmpeg_code = ffmpeg_process.poll()
        streamlink_code = streamlink_process.poll()

        # FFmpeg stopped
        if ffmpeg_code is not None:

            log(
                f"FFmpeg stopped "
                f"(exit code: {ffmpeg_code})."
            )

            stop_process(streamlink_process, "Streamlink")

            streamlink_process = None
            ffmpeg_process = None

            return False

        # Streamlink stopped
        if streamlink_code is not None:

            log(
                f"Streamlink stopped "
                f"(exit code: {streamlink_code})."
            )

            stop_process(ffmpeg_process, "FFmpeg")

            streamlink_process = None
            ffmpeg_process = None

            return False

        time.sleep(2)

    return False


# ============================================================
# MAIN 24/7 LOOP
# ============================================================

def main():

    global shutdown_requested

    print_header()

    log("Starting 24/7 relay...")
    separator()

    while not shutdown_requested:

        try:

            success = run_session()

            if shutdown_requested:
                break

            separator()
            log("Stream ended or connection lost.")
            log(
                f"Reconnecting in "
                f"{RECONNECT_DELAY} seconds..."
            )
            separator()

            stop_processes()

            time.sleep(RECONNECT_DELAY)

        except KeyboardInterrupt:

            shutdown_requested = True
            break

        except Exception as e:

            separator()
            log(f"Unexpected error: {e}")
            log(
                f"Reconnecting in "
                f"{RECONNECT_DELAY} seconds..."
            )
            separator()

            stop_processes()

            time.sleep(RECONNECT_DELAY)

    stop_processes()

    separator()
    log("Relay stopped.")
    separator()


# ============================================================
# SIGNALS
# ============================================================

signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
