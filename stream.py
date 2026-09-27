import os
import sys
import time
import signal
import subprocess


# ============================================================
# CONFIG
# ============================================================

YOUTUBE_URL = os.environ.get(
    "YOUTUBE_URL",
    "https://www.youtube.com/live/7DHNbnPMNiM"
)

# Restream RTMP
RESTREAM_RTMP_URL = os.environ.get(
    "RESTREAM_RTMP_URL",
    "rtmp://live.restream.io/live"
)

# Restream Stream Key
RESTREAM_STREAM_KEY = os.environ.get(
    "RESTREAM_STREAM_KEY",
    "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9"
)

RESTREAM_URL = f"{RESTREAM_RTMP_URL.rstrip('/')}/{RESTREAM_STREAM_KEY}"


# ============================================================
# STREAM SETTINGS
# ============================================================

QUALITY = "best"

VIDEO_COPY = True

AUDIO_CODEC = "aac"
AUDIO_BITRATE = "128k"
AUDIO_RATE = "44100"
AUDIO_CHANNELS = "2"

# No video processing
CROP = False
RESIZE = False
FPS_CONVERT = False

# Automatic reconnect
RECONNECT_DELAY = 5

# Streamlink network settings
HTTP_TIMEOUT = "30"

# HLS settings
HLS_LIVE_EDGE = "2"
RINGBUFFER_SIZE = "64M"

# Retry fetching stream
RETRY_STREAMS = "10"
RETRY_MAX = "0"

# Retry HLS segments
SEGMENT_ATTEMPTS = "10"
SEGMENT_TIMEOUT = "30"

# Number of seconds to wait before deciding the complete
# relay session has failed
PROCESS_START_TIMEOUT = 30


# ============================================================
# GLOBAL PROCESSES
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
# STOP PROCESS
# ============================================================

def terminate_process(process, name, timeout=5):

    if process is None:
        return

    if process.poll() is not None:
        return

    log(f"[SYSTEM] Stopping {name}...")

    try:
        process.terminate()
    except Exception:
        pass

    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:

        log(f"[SYSTEM] Killing {name}...")

        try:
            process.kill()
        except Exception:
            pass

        try:
            process.wait(timeout=3)
        except Exception:
            pass


# ============================================================
# STOP EVERYTHING
# ============================================================

def stop_processes():

    global streamlink_process
    global ffmpeg_process

    # FFmpeg first
    if ffmpeg_process is not None:
        terminate_process(
            ffmpeg_process,
            "FFmpeg"
        )

    ffmpeg_process = None

    # Streamlink second
    if streamlink_process is not None:
        terminate_process(
            streamlink_process,
            "Streamlink"
        )

    streamlink_process = None


# ============================================================
# STREAMLINK COMMAND
# ============================================================

def build_streamlink_command():

    cmd = [
        "streamlink",

        # Disable automatic version checks using the VALID
        # Streamlink option.
        "--auto-version-check", "no",

        # Don't use configuration files from the container.
        "--no-config",

        # HTTP
        "--http-timeout", HTTP_TIMEOUT,

        # HLS
        "--hls-live-edge", HLS_LIVE_EDGE,

        # Buffer
        "--ringbuffer-size", RINGBUFFER_SIZE,

        # Retry finding the live stream
        "--retry-streams", RETRY_STREAMS,
        "--retry-max", RETRY_MAX,

        # Retry HLS segments
        "--stream-segment-attempts", SEGMENT_ATTEMPTS,
        "--stream-segment-timeout", SEGMENT_TIMEOUT,

        # Send actual stream bytes to stdout
        "--stdout",

        YOUTUBE_URL,
        QUALITY,
    ]

    return cmd


# ============================================================
# FFMPEG COMMAND
# ============================================================

def build_ffmpeg_command():

    cmd = [
        "ffmpeg",

        "-hide_banner",
        "-loglevel", "warning",
        "-stats",

        # Input from Streamlink
        "-i", "-",

        # Generate timestamps if required
        "-fflags", "+genpts+discardcorrupt",

        # Ignore minor input errors
        "-err_detect", "ignore_err",

        # Video COPY - NO RE-ENCODE
        "-map", "0:v:0",
        "-c:v", "copy",

        # Audio AAC
        "-map", "0:a:0?",
        "-c:a", AUDIO_CODEC,
        "-b:a", AUDIO_BITRATE,
        "-ar", AUDIO_RATE,
        "-ac", AUDIO_CHANNELS,

        # Audio timestamp correction
        "-af",
        "aresample=async=1000:first_pts=0",

        # FLV output for RTMP
        "-f", "flv",

        RESTREAM_URL
    ]

    return cmd


# ============================================================
# START STREAMLINK
# ============================================================

def start_streamlink():

    global streamlink_process

    cmd = build_streamlink_command()

    log("[SYSTEM] Starting Streamlink...")
    log("[SYSTEM] Cookies: OFF")
    log(f"[SYSTEM] Quality: {QUALITY.upper()}")
    log("[SYSTEM] Video source: COPY")
    log("[SYSTEM] Waiting for real YouTube stream data...")

    try:

        streamlink_process = subprocess.Popen(
            cmd,

            # IMPORTANT:
            # stdout contains ONLY stream data.
            # stderr contains Streamlink logs.
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,

            bufsize=0
        )

    except Exception as e:

        log(f"[ERROR] Could not start Streamlink: {e}")
        streamlink_process = None
        return False

    return True


# ============================================================
# START FFMPEG
# ============================================================

def start_ffmpeg():

    global ffmpeg_process

    if streamlink_process is None:
        return False

    if streamlink_process.stdout is None:
        return False

    cmd = build_ffmpeg_command()

    log("[SYSTEM] Starting FFmpeg...")
    log("[SYSTEM] Video: COPY")
    log("[SYSTEM] Video Encode: OFF")
    log(f"[SYSTEM] Audio: AAC {AUDIO_BITRATE}")
    log("[SYSTEM] Sending stream to Restream...")

    try:

        ffmpeg_process = subprocess.Popen(
            cmd,

            # Streamlink stdout -> FFmpeg stdin
            stdin=streamlink_process.stdout,

            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,

            bufsize=0
        )

    except Exception as e:

        log(f"[ERROR] Could not start FFmpeg: {e}")
        ffmpeg_process = None
        return False

    return True


# ============================================================
# READ STREAMLINK LOGS
# ============================================================

def read_streamlink_logs():

    if streamlink_process is None:
        return

    if streamlink_process.stderr is None:
        return

    # Non-blocking isn't portable with normal Python pipes,
    # so this function is intentionally not used as a blocking
    # reader. Streamlink logs remain available from the container.
    pass


# ============================================================
# CHECK PIPELINE
# ============================================================

def pipeline_running():

    if streamlink_process is None:
        return False

    if ffmpeg_process is None:
        return False

    streamlink_code = streamlink_process.poll()
    ffmpeg_code = ffmpeg_process.poll()

    # Streamlink died
    if streamlink_code is not None:

        log(
            f"[SYSTEM] Streamlink stopped "
            f"(exit code: {streamlink_code})."
        )

        return False

    # FFmpeg died
    if ffmpeg_code is not None:

        log(
            f"[SYSTEM] FFmpeg stopped "
            f"(exit code: {ffmpeg_code})."
        )

        return False

    return True


# ============================================================
# WAIT FOR STREAM
# ============================================================

def wait_for_real_stream():

    global streamlink_process

    start_time = time.time()

    while not shutdown_requested:

        if streamlink_process is None:
            return False

        # Streamlink itself exited
        if streamlink_process.poll() is not None:

            code = streamlink_process.returncode

            log(
                f"[SYSTEM] Streamlink exited "
                f"while waiting for stream "
                f"(exit code: {code})."
            )

            return False

        # Don't falsely say that the stream exists just because
        # the Streamlink process is alive.
        #
        # FFmpeg will receive data through the pipe once Streamlink
        # actually opens the HLS stream.

        elapsed = time.time() - start_time

        if elapsed >= PROCESS_START_TIMEOUT:

            # If process is alive after timeout, let FFmpeg decide
            # whether actual media data is arriving.
            return True

        time.sleep(0.5)

    return False


# ============================================================
# RUN ONE SESSION
# ============================================================

def run_session():

    global streamlink_process
    global ffmpeg_process

    log("")
    log("============================================================")
    log("[SYSTEM] Starting relay session")
    log("============================================================")

    streamlink_process = None
    ffmpeg_process = None

    # --------------------------------------------------------
    # Streamlink
    # --------------------------------------------------------

    if not start_streamlink():

        return False

    # --------------------------------------------------------
    # Give Streamlink a moment to resolve YouTube
    # --------------------------------------------------------

    time.sleep(1)

    if shutdown_requested:
        return False

    if streamlink_process.poll() is not None:

        code = streamlink_process.returncode

        log(
            f"[SYSTEM] Streamlink failed immediately "
            f"(exit code: {code})."
        )

        return False

    log("[SYSTEM] Streamlink process is alive.")

    # --------------------------------------------------------
    # FFmpeg
    # --------------------------------------------------------

    if not start_ffmpeg():

        return False

    log("[SYSTEM] FFmpeg pipeline started.")
    log("[SYSTEM] Waiting for actual media data...")
    log("[SYSTEM] Stream will RUN once FFmpeg receives media.")

    # --------------------------------------------------------
    # Monitor
    # --------------------------------------------------------

    running_message_printed = False

    while not shutdown_requested:

        # Streamlink died
        if streamlink_process.poll() is not None:

            code = streamlink_process.returncode

            log(
                f"[SYSTEM] Streamlink stopped "
                f"(exit code: {code})."
            )

            return False

        # FFmpeg died
        if ffmpeg_process.poll() is not None:

            code = ffmpeg_process.returncode

            log(
                f"[SYSTEM] FFmpeg stopped "
                f"(exit code: {code})."
            )

            return False

        # Once FFmpeg has survived a few seconds, consider the
        # pipeline established.
        if not running_message_printed:

            log("[SYSTEM] Stream pipeline is RUNNING.")
            running_message_printed = True

        time.sleep(1)

    return False


# ============================================================
# MAIN 24/7 LOOP
# ============================================================

def main():

    global shutdown_requested

    signal.signal(
        signal.SIGINT,
        signal_handler
    )

    signal.signal(
        signal.SIGTERM,
        signal_handler
    )

    log("============================================================")
    log("       YouTube 24/7 -> Restream -> TikTok")
    log("============================================================")
    log(f"YouTube        : {YOUTUBE_URL}")
    log("Destination    : Restream")
    log("Cookies        : OFF")
    log("Video          : COPY")
    log("Video Encode   : OFF")
    log("Crop           : OFF")
    log("Resize         : OFF")
    log("FPS Convert    : OFF")
    log(f"Audio          : AAC {AUDIO_BITRATE}")
    log("Auto-Reconnect : ON")
    log("Status         : STARTING")
    log("============================================================")
    log("[SYSTEM] Starting 24/7 relay...")
    log("============================================================")

    while not shutdown_requested:

        try:

            result = run_session()

        except KeyboardInterrupt:

            shutdown_requested = True
            break

        except Exception as e:

            log(f"[ERROR] Relay exception: {e}")
            result = False

        # ----------------------------------------------------
        # Clean up failed session
        # ----------------------------------------------------

        if not shutdown_requested:

            log("[SYSTEM] Relay session ended.")
            log("[SYSTEM] Cleaning up processes...")

            stop_processes()

            log("")
            log("============================================================")
            log(
                f"[SYSTEM] Reconnecting in "
                f"{RECONNECT_DELAY} seconds..."
            )
            log("============================================================")

            for _ in range(RECONNECT_DELAY):

                if shutdown_requested:
                    break

                time.sleep(1)

    # --------------------------------------------------------
    # Final cleanup
    # --------------------------------------------------------

    stop_processes()

    log("")
    log("============================================================")
    log("[SYSTEM] Relay stopped.")
    log("============================================================")


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
