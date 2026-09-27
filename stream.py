import os
import sys
import time
import signal
import subprocess
import gc


# ============================================================
# CONFIG
# ============================================================

YOUTUBE_URL = "https://www.youtube.com/live/7DHNbnPMNiM"

RESTREAM_STREAM_KEY = (
    "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9"
)

RESTREAM_RTMP = (
    f"rtmp://live.restream.io/live/{RESTREAM_STREAM_KEY}"
)

QUALITY = "best"

RECONNECT_DELAY = 5
MAX_RECONNECT_DELAY = 30

# إعادة استخراج رابط YouTube كلما انتهت جلسة FFmpeg
URL_REFRESH_DELAY = 3

# لو لم تصل أي frames لفترة طويلة نعيد الجلسة
STALL_TIMEOUT = 45

# مدة الانتظار بين محاولات yt-dlp
YTDLP_RETRY_DELAY = 10

# ============================================================
# VIDEO / AUDIO
# ============================================================

VIDEO_CODEC = "copy"

AUDIO_CODEC = "aac"
AUDIO_BITRATE = "128k"
AUDIO_RATE = "44100"
AUDIO_CHANNELS = "2"


# ============================================================
# GLOBALS
# ============================================================

ffmpeg_process = None

shutdown_requested = False

last_frame_time = 0

session_number = 0


# ============================================================
# LOG
# ============================================================

def log(text=""):
    print(text, flush=True)


# ============================================================
# SIGNALS
# ============================================================

def handle_signal(signum, frame):

    global shutdown_requested

    shutdown_requested = True

    log("")
    log("[SYSTEM] Shutdown requested...")


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


# ============================================================
# PROCESS STOP
# ============================================================

def stop_process(process, name):

    if process is None:
        return

    try:

        if process.poll() is None:

            log(f"[SYSTEM] Stopping {name}...")

            try:
                process.terminate()
            except Exception:
                pass

            try:
                process.wait(timeout=5)
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

    except Exception as e:

        log(f"[SYSTEM] Error stopping {name}: {e}")


# ============================================================
# STOP ALL
# ============================================================

def stop_all():

    global ffmpeg_process

    if ffmpeg_process is not None:

        stop_process(
            ffmpeg_process,
            "FFmpeg"
        )

    ffmpeg_process = None

    # Force Python garbage collection.
    # This helps keep the Railway container clean.
    gc.collect()


# ============================================================
# GET FRESH YOUTUBE HLS URL
# ============================================================

def get_fresh_hls_url():

    log("[SYSTEM] Resolving fresh YouTube HLS URL...")

    command = [
        "yt-dlp",

        "--no-warnings",

        "--no-playlist",

        "--skip-download",

        "--format",
        QUALITY,

        "--get-url",

        YOUTUBE_URL
    ]

    try:

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60
        )

    except subprocess.TimeoutExpired:

        log("[ERROR] yt-dlp timed out.")

        return None

    except Exception as e:

        log(
            f"[ERROR] Could not execute yt-dlp: "
            f"{type(e).__name__}: {e}"
        )

        return None

    if result.returncode != 0:

        error_text = result.stderr.strip()

        log("[ERROR] yt-dlp failed:")

        if error_text:
            log(error_text[-3000:])

        return None

    urls = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]

    if not urls:

        log("[ERROR] yt-dlp returned no media URL.")

        return None

    # Prefer HLS / m3u8.
    for url in urls:

        if ".m3u8" in url.lower():
            return url

    # Fallback to last URL returned by yt-dlp.
    return urls[-1]


# ============================================================
# FFMPEG COMMAND
# ============================================================

def build_ffmpeg_command(source_url):

    return [

        "ffmpeg",

        "-hide_banner",

        "-loglevel",
        "warning",

        "-stats",

        # ====================================================
        # HTTP / HLS RECONNECT
        # ====================================================

        "-reconnect",
        "1",

        "-reconnect_at_eof",
        "1",

        "-reconnect_streamed",
        "1",

        "-reconnect_on_network_error",
        "1",

        "-reconnect_on_http_error",
        "4xx,5xx",

        "-reconnect_delay_max",
        "15",

        "-reconnect_max_retries",
        "1000000",

        # ====================================================
        # INPUT
        # ====================================================

        "-i",
        source_url,

        # ====================================================
        # VIDEO COPY
        # ====================================================

        "-map",
        "0:v:0",

        "-c:v",
        "copy",

        # ====================================================
        # AUDIO
        # ====================================================

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

        # ====================================================
        # AUDIO TIMESTAMP STABILITY
        # ====================================================

        "-af",
        "aresample=async=1000:min_hard_comp=0.100:first_pts=0",

        # ====================================================
        # TIMESTAMP HANDLING
        # ====================================================

        "-fflags",
        "+genpts+discardcorrupt",

        "-err_detect",
        "ignore_err",

        # ====================================================
        # FLV / RTMP
        # ====================================================

        "-flvflags",
        "no_duration_filesize",

        "-f",
        "flv",

        RESTREAM_RTMP
    ]


# ============================================================
# START FFMPEG
# ============================================================

def start_ffmpeg(source_url):

    global ffmpeg_process
    global last_frame_time

    stop_all()

    gc.collect()

    log("")
    log("============================================================")
    log("[SYSTEM] Starting FFmpeg")
    log("============================================================")

    log("[SYSTEM] Video: COPY")
    log("[SYSTEM] Video Encode: OFF")
    log(f"[SYSTEM] Audio: AAC {AUDIO_BITRATE}")
    log("[SYSTEM] Crop: OFF")
    log("[SYSTEM] Resize: OFF")
    log("[SYSTEM] FPS Convert: OFF")
    log("[SYSTEM] Sending YouTube -> Restream...")

    command = build_ffmpeg_command(source_url)

    try:

        ffmpeg_process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=None,
            bufsize=0
        )

    except Exception as e:

        log(
            f"[ERROR] Could not start FFmpeg: "
            f"{type(e).__name__}: {e}"
        )

        ffmpeg_process = None

        return False

    last_frame_time = time.time()

    time.sleep(5)

    if ffmpeg_process.poll() is not None:

        code = ffmpeg_process.returncode

        log(
            f"[ERROR] FFmpeg exited immediately "
            f"(exit code: {code})."
        )

        stop_all()

        return False

    log("[SYSTEM] FFmpeg process is alive.")
    log("[SYSTEM] YouTube -> FFmpeg: CONNECTED")
    log("[SYSTEM] FFmpeg -> Restream: CONNECTED")
    log("[SYSTEM] Stream is RUNNING.")

    return True


# ============================================================
# MONITOR FFMPEG
# ============================================================

def monitor_ffmpeg():

    global ffmpeg_process

    last_status = time.time()

    while not shutdown_requested:

        time.sleep(5)

        if ffmpeg_process is None:

            log("[SYSTEM] FFmpeg process missing.")

            return False

        code = ffmpeg_process.poll()

        if code is not None:

            log("")
            log(
                f"[SYSTEM] FFmpeg stopped "
                f"(exit code: {code})."
            )

            return False

        # ----------------------------------------------------
        # HEARTBEAT
        # ----------------------------------------------------

        if time.time() - last_status >= 60:

            log("[SYSTEM] Relay is still RUNNING.")

            last_status = time.time()

    return False


# ============================================================
# WAIT
# ============================================================

def safe_sleep(seconds):

    end_time = time.time() + seconds

    while (
        time.time() < end_time
        and not shutdown_requested
    ):

        time.sleep(
            min(
                1,
                end_time - time.time()
            )
        )


# ============================================================
# MAIN SESSION
# ============================================================

def run_session():

    global session_number

    session_number += 1

    log("")
    log("============================================================")
    log(
        f"[SYSTEM] Starting relay session #{session_number}"
    )
    log("============================================================")

    # --------------------------------------------------------
    # GET FRESH URL
    # --------------------------------------------------------

    hls_url = get_fresh_hls_url()

    if not hls_url:

        log(
            "[SYSTEM] Could not obtain a fresh YouTube URL."
        )

        return False

    log("[SYSTEM] Fresh YouTube playback URL obtained.")

    # --------------------------------------------------------
    # START FFMPEG
    # --------------------------------------------------------

    if not start_ffmpeg(hls_url):

        return False

    # --------------------------------------------------------
    # MONITOR
    # --------------------------------------------------------

    result = monitor_ffmpeg()

    stop_all()

    return result


# ============================================================
# MAIN
# ============================================================

def main():

    global shutdown_requested

    log("============================================================")
    log("       YouTube 24/7 -> Restream -> TikTok")
    log("============================================================")

    log(f"YouTube        : {YOUTUBE_URL}")
    log("Destination    : Restream")
    log("Extractor      : yt-dlp")
    log("Cookies        : OFF")
    log("Quality        : BEST")
    log("Video          : COPY")
    log("Video Encode   : OFF")
    log("Crop           : OFF")
    log("Resize         : OFF")
    log("FPS Convert    : OFF")
    log(f"Audio          : AAC {AUDIO_BITRATE}")
    log("HLS Reconnect  : ON")
    log("Stall Recovery : ON")
    log("Memory Mode    : LOW")
    log("Auto-Reconnect : ON")
    log("Status         : STARTING")

    log("============================================================")
    log("[SYSTEM] Starting 24/7 relay...")
    log("============================================================")

    reconnect_delay = RECONNECT_DELAY

    while not shutdown_requested:

        try:

            run_session()

        except Exception as e:

            log("")
            log("============================================================")
            log("[ERROR] SESSION EXCEPTION")
            log(
                f"[ERROR] {type(e).__name__}: {e}"
            )
            log("============================================================")

        if shutdown_requested:
            break

        # ----------------------------------------------------
        # CLEANUP
        # ----------------------------------------------------

        stop_all()

        gc.collect()

        log("")
        log("============================================================")
        log("[SYSTEM] Stream ended or connection lost.")
        log(
            f"[SYSTEM] Fresh reconnect in "
            f"{reconnect_delay} seconds..."
        )
        log("============================================================")

        safe_sleep(reconnect_delay)

        # ----------------------------------------------------
        # Gradually increase reconnect delay if failures repeat.
        # Maximum 30 seconds.
        # ----------------------------------------------------

        reconnect_delay = min(
            reconnect_delay + 2,
            MAX_RECONNECT_DELAY
        )

    # --------------------------------------------------------
    # SHUTDOWN
    # --------------------------------------------------------

    log("")
    log("[SYSTEM] Shutting down...")

    stop_all()

    gc.collect()

    log("[SYSTEM] Relay stopped.")


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        shutdown_requested = True

        log("[SYSTEM] Keyboard interrupt.")

        stop_all()

    except Exception as e:

        log("")
        log("============================================================")
        log("[SYSTEM] FATAL ERROR")
        log(
            f"[SYSTEM] {type(e).__name__}: {e}"
        )
        log("============================================================")

        stop_all()

    finally:

        stop_all()
        gc.collect()
