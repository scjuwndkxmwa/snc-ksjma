import os
import time
import signal
import subprocess
import base64
import threading
from pathlib import Path


# ============================================================
# CONFIG
# ============================================================

YOUTUBE_PLAYLIST_URL = (
    "https://youtube.com/playlist?list="
    "PLHevKCZsj31yChzIFaLbYvTlMsqAft51L"
)

PLAYLIST_LOOP = True
PLAYLIST_REFRESH_EVERY_LOOP = True


# ============================================================
# RESTREAM
# ============================================================

RESTREAM_STREAM_KEY = (
    "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9"
)

RESTREAM_RTMP = (
    f"rtmp://live.restream.io/live/{RESTREAM_STREAM_KEY}"
)


# ============================================================
# STREAM
# ============================================================

QUALITY = "best"

RINGBUFFER_SIZE = "32M"

HLS_LIVE_EDGE = "3"

RETRY_STREAMS = "5"
RETRY_MAX = "0"

SEGMENT_ATTEMPTS = "5"
SEGMENT_THREADS = "1"
SEGMENT_TIMEOUT = "20"

STREAM_TIMEOUT = "60"

PLAYLIST_RELOAD_ATTEMPTS = "8"


# ============================================================
# AUDIO
# ============================================================

AUDIO_BITRATE = "128k"
AUDIO_RATE = "44100"
AUDIO_CHANNELS = "2"


# ============================================================
# RECONNECT
# ============================================================

RECONNECT_DELAY = 5
MAX_RECONNECT_DELAY = 60

VIDEO_RETRIES = 3

BETWEEN_VIDEOS_DELAY = 3


# ============================================================
# PLAYLIST
# ============================================================

PLAYLIST_COMMAND_TIMEOUT = 120

PLAYLIST_CACHE_PATH = (
    "/tmp/youtube_playlist_cache.txt"
)


# ============================================================
# COOKIES
# ============================================================

COOKIES_PATH = (
    "/tmp/youtube_cookies.txt"
)


# ============================================================
# GLOBALS
# ============================================================

streamlink_process = None
ffmpeg_process = None

shutdown_requested = False

cookies_file = None

last_data_time = 0
data_received = False

data_lock = threading.Lock()


# ============================================================
# LOG
# ============================================================

def log(text=""):
    print(text, flush=True)


# ============================================================
# SIGNAL
# ============================================================

def handle_signal(signum, frame):

    global shutdown_requested

    shutdown_requested = True

    log("")
    log("[SYSTEM] Shutdown requested...")


signal.signal(
    signal.SIGINT,
    handle_signal
)

signal.signal(
    signal.SIGTERM,
    handle_signal
)


# ============================================================
# COOKIES
# ============================================================

def prepare_youtube_cookies():

    global cookies_file

    encoded = os.environ.get(
        "YOUTUBE_COOKIES_B64",
        ""
    ).strip()

    if not encoded:

        log("[SYSTEM] YouTube Cookies: OFF")

        return None

    try:

        decoded = base64.b64decode(
            encoded,
            validate=True
        )

        if not decoded:

            raise ValueError(
                "Cookie data is empty."
            )

        path = COOKIES_PATH

        with open(path, "wb") as f:
            f.write(decoded)

        with open(
            path,
            "r",
            encoding="utf-8",
            errors="ignore"
        ) as f:

            first_lines = f.read(4096)

        if (
            "# Netscape HTTP Cookie File"
            not in first_lines
            and
            "# HTTP Cookie File"
            not in first_lines
        ):

            log(
                "[WARNING] Cookie file does not "
                "look like a Netscape cookies.txt file."
            )

        cookies_file = path

        log("[SYSTEM] YouTube Cookies: ON")
        log("[SYSTEM] Cookie file prepared.")

        return path

    except Exception as e:

        log(
            "[ERROR] Could not decode "
            f"YOUTUBE_COOKIES_B64: {e}"
        )

        return None


# ============================================================
# STOP PROCESS
# ============================================================

def stop_process(process, name):

    if process is None:
        return

    try:

        if process.poll() is None:

            log(
                f"[SYSTEM] Stopping {name}..."
            )

            try:
                process.terminate()
            except Exception:
                pass

            try:

                process.wait(
                    timeout=5
                )

            except subprocess.TimeoutExpired:

                log(
                    f"[SYSTEM] Killing {name}..."
                )

                try:
                    process.kill()
                except Exception:
                    pass

                try:
                    process.wait(
                        timeout=3
                    )
                except Exception:
                    pass

    except Exception as e:

        log(
            f"[SYSTEM] Error stopping "
            f"{name}: {e}"
        )


# ============================================================
# STOP ALL
# ============================================================

def stop_all():

    global streamlink_process
    global ffmpeg_process

    if ffmpeg_process is not None:

        stop_process(
            ffmpeg_process,
            "FFmpeg"
        )

    ffmpeg_process = None

    if streamlink_process is not None:

        stop_process(
            streamlink_process,
            "Streamlink"
        )

    streamlink_process = None


# ============================================================
# YT-DLP PLAYLIST COMMAND
# ============================================================

def build_playlist_command():

    command = [

        "yt-dlp",

        "--flat-playlist",

        "--ignore-errors",

        "--no-warnings",

        "--skip-download",

        "--print",
        "%(id)s"
    ]

    if cookies_file:

        command.extend(
            [
                "--cookies",
                cookies_file
            ]
        )

    command.append(
        YOUTUBE_PLAYLIST_URL
    )

    return command


# ============================================================
# LOAD PLAYLIST CACHE
# ============================================================

def load_playlist_cache():

    path = Path(
        PLAYLIST_CACHE_PATH
    )

    if not path.exists():
        return []

    try:

        items = []

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:

            for line in f:

                video_id = line.strip()

                if not video_id:
                    continue

                if video_id in items:
                    continue

                items.append(video_id)

        return items

    except Exception as e:

        log(
            "[WARNING] Could not read "
            f"playlist cache: {e}"
        )

        return []


# ============================================================
# SAVE PLAYLIST CACHE
# ============================================================

def save_playlist_cache(items):

    try:

        with open(
            PLAYLIST_CACHE_PATH,
            "w",
            encoding="utf-8"
        ) as f:

            for video_id in items:

                f.write(
                    video_id + "\n"
                )

    except Exception as e:

        log(
            "[WARNING] Could not save "
            f"playlist cache: {e}"
        )


# ============================================================
# GET PLAYLIST ITEMS
# ============================================================

def get_playlist_items():

    log("")
    log("=" * 60)
    log("[PLAYLIST] Reading YouTube Playlist...")
    log("=" * 60)

    command = build_playlist_command()

    try:

        result = subprocess.run(

            command,

            stdout=subprocess.PIPE,

            stderr=subprocess.PIPE,

            text=True,

            encoding="utf-8",

            errors="replace",

            timeout=PLAYLIST_COMMAND_TIMEOUT
        )

    except subprocess.TimeoutExpired:

        log(
            "[PLAYLIST] yt-dlp timed out."
        )

        cached = load_playlist_cache()

        if cached:

            log(
                "[PLAYLIST] Using cached list: "
                f"{len(cached)} videos."
            )

            return cached

        return []

    except Exception as e:

        log(
            "[PLAYLIST] yt-dlp error: "
            f"{e}"
        )

        cached = load_playlist_cache()

        if cached:

            log(
                "[PLAYLIST] Using cached list: "
                f"{len(cached)} videos."
            )

            return cached

        return []

    items = []

    for line in result.stdout.splitlines():

        video_id = line.strip()

        if not video_id:
            continue

        if len(video_id) < 6:
            continue

        if video_id in items:
            continue

        items.append(video_id)

    if items:

        save_playlist_cache(items)

        log(
            "[PLAYLIST] Found "
            f"{len(items)} videos."
        )

        return items

    if result.stderr:

        log(
            "[PLAYLIST] yt-dlp did not "
            "return playlist items."
        )

    cached = load_playlist_cache()

    if cached:

        log(
            "[PLAYLIST] Using previous "
            f"cache: {len(cached)} videos."
        )

        return cached

    log(
        "[PLAYLIST] No videos found."
    )

    return []


# ============================================================
# VIDEO URL
# ============================================================

def make_video_url(video_id):

    return (
        "https://www.youtube.com/watch?v="
        + video_id
    )


# ============================================================
# STREAMLINK COMMAND
# ============================================================

def build_streamlink_command(video_url):

    command = [

        "streamlink",

        "--loglevel",
        "info",

        "--retry-streams",
        RETRY_STREAMS,

        "--retry-max",
        RETRY_MAX,

        "--retry-open",
        "5",

        "--ringbuffer-size",
        RINGBUFFER_SIZE,

        "--hls-live-edge",
        HLS_LIVE_EDGE,

        "--hls-playlist-reload-attempts",
        PLAYLIST_RELOAD_ATTEMPTS,

        "--stream-segment-attempts",
        SEGMENT_ATTEMPTS,

        "--stream-segment-threads",
        SEGMENT_THREADS,

        "--stream-segment-timeout",
        SEGMENT_TIMEOUT,

        "--stream-timeout",
        STREAM_TIMEOUT,

        "--stdout",

        video_url,

        QUALITY
    ]

    if cookies_file:

        stdout_index = command.index(
            "--stdout"
        )

        command.insert(
            stdout_index,
            cookies_file
        )

        command.insert(
            stdout_index,
            "--http-cookies-file"
        )

    return command


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

        "-thread_queue_size",
        "64",

        "-i",
        "-",

        # VIDEO COPY
        "-map",
        "0:v:0",

        "-c:v",
        "copy",

        # AUDIO
        "-map",
        "0:a:0?",

        "-c:a",
        "aac",

        "-b:a",
        AUDIO_BITRATE,

        "-ar",
        AUDIO_RATE,

        "-ac",
        AUDIO_CHANNELS,

        "-af",
        "aresample="
        "async=1000:"
        "min_hard_comp=0.100:"
        "first_pts=0",

        # TIMESTAMPS
        "-fflags",
        "+genpts+discardcorrupt",

        "-err_detect",
        "ignore_err",

        "-max_interleave_delta",
        "0",

        # OUTPUT
        "-f",
        "flv",

        RESTREAM_RTMP
    ]


# ============================================================
# STREAMLINK -> FFMPEG PIPE
# ============================================================

def pipe_streamlink_to_ffmpeg():

    global last_data_time
    global data_received

    try:

        while not shutdown_requested:

            if streamlink_process is None:
                break

            if ffmpeg_process is None:
                break

            stdout = (
                streamlink_process.stdout
            )

            stdin = (
                ffmpeg_process.stdin
            )

            if stdout is None:
                break

            if stdin is None:
                break

            data = stdout.read(
                64 * 1024
            )

            if not data:
                break

            try:

                stdin.write(data)
                stdin.flush()

            except (
                BrokenPipeError,
                OSError
            ):

                break

            with data_lock:

                last_data_time = (
                    time.time()
                )

                data_received = True

    except Exception as e:

        if not shutdown_requested:

            log(
                f"[PIPE] Error: {e}"
            )

    finally:

        try:

            if (
                ffmpeg_process is not None
                and
                ffmpeg_process.stdin
            ):

                ffmpeg_process.stdin.close()

        except Exception:
            pass


# ============================================================
# START VIDEO SESSION
# ============================================================

def start_video_session(
    video_id,
    video_number,
    total_videos
):

    global streamlink_process
    global ffmpeg_process
    global last_data_time
    global data_received

    video_url = make_video_url(
        video_id
    )

    stop_all()

    with data_lock:

        last_data_time = time.time()
        data_received = False

    log("")
    log("=" * 60)

    log(
        f"[VIDEO] {video_number}/{total_videos}"
    )

    log(
        f"[VIDEO] ID: {video_id}"
    )

    log(
        f"[VIDEO] URL: {video_url}"
    )

    log("=" * 60)

    command = build_streamlink_command(
        video_url
    )

    log(
        "[SYSTEM] Starting Streamlink..."
    )

    log(
        f"[SYSTEM] Quality: {QUALITY.upper()}"
    )

    log(
        "[SYSTEM] Video: COPY"
    )

    log(
        "[SYSTEM] Video Encode: OFF"
    )

    log(
        f"[SYSTEM] Audio: AAC {AUDIO_BITRATE}"
    )

    log(
        "[SYSTEM] Memory Mode: LOW"
    )

    if cookies_file:

        log(
            "[SYSTEM] YouTube Cookies: ON"
        )

    else:

        log(
            "[SYSTEM] YouTube Cookies: OFF"
        )

    log(
        "[SYSTEM] Waiting for YouTube..."
    )

    try:

        streamlink_process = subprocess.Popen(

            command,

            stdout=subprocess.PIPE,

            stderr=None,

            stdin=subprocess.DEVNULL,

            bufsize=0
        )

    except Exception as e:

        log(
            "[ERROR] Could not start "
            f"Streamlink: {e}"
        )

        streamlink_process = None

        return False

    time.sleep(3)

    if shutdown_requested:

        stop_all()

        return False

    if (
        streamlink_process.poll()
        is not None
    ):

        code = (
            streamlink_process.returncode
        )

        log(
            "[ERROR] Streamlink exited "
            f"(exit code: {code})"
        )

        streamlink_process = None

        return False

    log(
        "[SYSTEM] Streamlink process is alive."
    )

    # ========================================================
    # FFMPEG
    # ========================================================

    ffmpeg_command = (
        build_ffmpeg_command()
    )

    log(
        "[SYSTEM] Starting FFmpeg..."
    )

    log(
        "[SYSTEM] Video: COPY"
    )

    log(
        "[SYSTEM] Video Encode: OFF"
    )

    log(
        f"[SYSTEM] Audio: AAC {AUDIO_BITRATE}"
    )

    log(
        "[SYSTEM] Sending YouTube -> Restream..."
    )

    try:

        ffmpeg_process = subprocess.Popen(

            ffmpeg_command,

            stdin=subprocess.PIPE,

            stdout=subprocess.DEVNULL,

            stderr=None,

            bufsize=0
        )

    except Exception as e:

        log(
            "[ERROR] Could not start "
            f"FFmpeg: {e}"
        )

        stop_all()

        return False

    # ========================================================
    # PIPE
    # ========================================================

    pipe_thread = threading.Thread(
        target=pipe_streamlink_to_ffmpeg,
        daemon=True
    )

    pipe_thread.start()

    # ========================================================
    # WAIT FOR REAL DATA
    # ========================================================

    start_wait = time.time()

    while not shutdown_requested:

        time.sleep(1)

        if (
            ffmpeg_process is None
            or
            ffmpeg_process.poll()
            is not None
        ):

            code = (
                ffmpeg_process.returncode
                if ffmpeg_process is not None
                else "unknown"
            )

            log(
                "[ERROR] FFmpeg exited "
                f"(exit code: {code})"
            )

            return False

        if (
            streamlink_process is None
            or
            streamlink_process.poll()
            is not None
        ):

            code = (
                streamlink_process.returncode
                if streamlink_process is not None
                else "unknown"
            )

            log(
                "[ERROR] Streamlink exited "
                f"(exit code: {code})"
            )

            return False

        with data_lock:

            received = data_received

        if received:

            log(
                "[SYSTEM] YouTube -> FFmpeg: CONNECTED"
            )

            log(
                "[SYSTEM] FFmpeg -> Restream: CONNECTED"
            )

            log(
                "[SYSTEM] Stream is RUNNING."
            )

            return True

        if (
            time.time() - start_wait
            >= 120
        ):

            log(
                "[ERROR] No stream data "
                "received for 120 seconds."
            )

            return False

    return False


# ============================================================
# MONITOR
# ============================================================

def monitor_video():

    global streamlink_process
    global ffmpeg_process

    last_heartbeat = time.time()

    while not shutdown_requested:

        time.sleep(3)

        # STREAMLINK
        if streamlink_process is None:

            log(
                "[ERROR] Streamlink process missing."
            )

            return False

        streamlink_code = (
            streamlink_process.poll()
        )

        if streamlink_code is not None:

            log(
                "[SYSTEM] Streamlink stopped "
                f"(exit code: {streamlink_code})"
            )

            return False

        # FFMPEG
        if ffmpeg_process is None:

            log(
                "[ERROR] FFmpeg process missing."
            )

            return False

        ffmpeg_code = (
            ffmpeg_process.poll()
        )

        if ffmpeg_code is not None:

            log(
                "[SYSTEM] FFmpeg stopped "
                f"(exit code: {ffmpeg_code})"
            )

            return False

        # DATA WATCHDOG
        with data_lock:

            current_last_data = (
                last_data_time
            )

            received = data_received

        if received:

            no_data_for = (
                time.time()
                - current_last_data
            )

            if no_data_for >= 120:

                log(
                    "[ERROR] No data received "
                    f"for {int(no_data_for)} seconds."
                )

                return False

        # HEARTBEAT
        if (
            time.time()
            - last_heartbeat
            >= 60
        ):

            log(
                "[SYSTEM] Relay is still RUNNING."
            )

            last_heartbeat = time.time()

    return False


# ============================================================
# RUN VIDEO
# ============================================================

def run_video(
    video_id,
    video_number,
    total_videos
):

    reconnect_delay = (
        RECONNECT_DELAY
    )

    for attempt in range(
        1,
        VIDEO_RETRIES + 1
    ):

        if shutdown_requested:

            return False

        log("")

        log(
            f"[VIDEO] Attempt "
            f"{attempt}/{VIDEO_RETRIES}"
        )

        success = start_video_session(
            video_id,
            video_number,
            total_videos
        )

        if shutdown_requested:

            stop_all()

            return False

        if success:

            reconnect_delay = (
                RECONNECT_DELAY
            )

            monitor_video()

            if shutdown_requested:

                stop_all()

                return False

            # انتهاء طبيعي للفيديو
            if (
                streamlink_process is not None
                and
                streamlink_process.poll()
                == 0
            ):

                log(
                    "[VIDEO] Video finished normally."
                )

                stop_all()

                return True

        stop_all()

        if attempt < VIDEO_RETRIES:

            log(
                "[VIDEO] Failed."
            )

            log(
                f"[VIDEO] Retrying in "
                f"{reconnect_delay} seconds..."
            )

            time.sleep(
                reconnect_delay
            )

            reconnect_delay = min(
                reconnect_delay * 2,
                MAX_RECONNECT_DELAY
            )

    log(
        "[VIDEO] Failed after all retries."
    )

    log(
        "[VIDEO] Skipping this video."
    )

    stop_all()

    return True


# ============================================================
# MAIN
# ============================================================

def main():

    global shutdown_requested

    log("=" * 60)

    log(
        "       YouTube Playlist 24/7"
    )

    log(
        "       -> Restream -> TikTok"
    )

    log("=" * 60)

    log(
        f"Playlist      : "
        f"{YOUTUBE_PLAYLIST_URL}"
    )

    log(
        "Destination    : Restream"
    )

    log(
        "Playlist Mode  : LOOP 24/7"
    )

    log(
        "Extractor      : Streamlink"
    )

    log(
        "Cookies        : "
        + (
            "ON"
            if cookies_file
            else
            "OFF"
        )
    )

    log(
        "Quality        : BEST"
    )

    log(
        "Video          : COPY"
    )

    log(
        "Video Encode   : OFF"
    )

    log(
        "Crop           : OFF"
    )

    log(
        "Resize         : OFF"
    )

    log(
        "FPS Convert    : OFF"
    )

    log(
        f"Audio          : AAC {AUDIO_BITRATE}"
    )

    log(
        "Memory Mode    : LOW"
    )

    log(
        "Auto-Reconnect : ON"
    )

    log(
        "Status         : STARTING"
    )

    log("=" * 60)

    # ========================================================
    # INITIAL PLAYLIST
    # ========================================================

    playlist_items = []

    while (
        not playlist_items
        and
        not shutdown_requested
    ):

        playlist_items = (
            get_playlist_items()
        )

        if playlist_items:

            break

        log(
            "[PLAYLIST] No playlist items."
        )

        log(
            "[PLAYLIST] Retrying in "
            "30 seconds..."
        )

        time.sleep(30)

    # ========================================================
    # PLAYLIST LOOP
    # ========================================================

    playlist_round = 0

    while (
        not shutdown_requested
        and
        playlist_items
    ):

        playlist_round += 1

        log("")
        log("=" * 60)

        log(
            f"[PLAYLIST] Starting round "
            f"#{playlist_round}"
        )

        log(
            f"[PLAYLIST] Videos: "
            f"{len(playlist_items)}"
        )

        log("=" * 60)

        # ----------------------------------------------------
        # PLAY VIDEOS IN ORDER
        # ----------------------------------------------------

        for index, video_id in enumerate(
            playlist_items,
            start=1
        ):

            if shutdown_requested:
                break

            log("")
            log(
                f"[PLAYLIST] Playing "
                f"{index}/{len(playlist_items)}"
            )

            run_video(
                video_id,
                index,
                len(playlist_items)
            )

            if shutdown_requested:
                break

            log(
                f"[PLAYLIST] Waiting "
                f"{BETWEEN_VIDEOS_DELAY} seconds..."
            )

            time.sleep(
                BETWEEN_VIDEOS_DELAY
            )

        if shutdown_requested:
            break

        # ----------------------------------------------------
        # REFRESH PLAYLIST
        # ----------------------------------------------------

        if PLAYLIST_REFRESH_EVERY_LOOP:

            log("")
            log(
                "[PLAYLIST] Refreshing playlist..."
            )

            new_items = (
                get_playlist_items()
            )

            if new_items:

                playlist_items = (
                    new_items
                )

                log(
                    "[PLAYLIST] Playlist updated."
                )

        # ----------------------------------------------------
        # LOOP
        # ----------------------------------------------------

        if PLAYLIST_LOOP:

            log("")
            log("=" * 60)

            log(
                "[PLAYLIST] Reached the end."
            )

            log(
                "[PLAYLIST] Starting again "
                "from the first video."
            )

            log("=" * 60)

            continue

        break

    stop_all()

    log(
        "[SYSTEM] Relay stopped."
    )


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    try:

        prepare_youtube_cookies()

        main()

    except KeyboardInterrupt:

        shutdown_requested = True

        log(
            "[SYSTEM] Keyboard interrupt."
        )

    except Exception as e:

        log("")
        log("=" * 60)

        log(
            "[SYSTEM] UNEXPECTED ERROR"
        )

        log(
            f"[SYSTEM] "
            f"{type(e).__name__}: {e}"
        )

        log("=" * 60)

    finally:

        stop_all()

        log(
            "[SYSTEM] Relay stopped."
        )
