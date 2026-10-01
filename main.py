import os
import time
import signal
import subprocess
from pathlib import Path

# ============================================================
# YOUTUBE VIDEOS - SAME ORDER
# ============================================================

VIDEOS = [
    "https://youtu.be/pNd2amw7ZAo",
    "https://youtu.be/tFA3mH8kTJ0",
    "https://youtu.be/UWzGxlZWimE",
    "https://youtu.be/iCnj6QwmtwA",
    "https://youtu.be/03cpj3iwNnY",
    "https://youtu.be/RHnm5zuprrk",
    "https://youtu.be/UfiLhGZ9J-A",
    "https://youtu.be/6Pc97lWbxN8",
]

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
# SETTINGS
# ============================================================

MEDIA_DIR = Path("/tmp/youtube_videos")
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

# أعلى جودة متاحة حتى 1080p
FORMAT = (
    "bestvideo[height<=1080]+bestaudio/"
    "best[height<=1080]/"
    "bestvideo+bestaudio/"
    "best"
)

# الصوت فقط يتم ترميزه
AUDIO_BITRATE = "128k"
AUDIO_RATE = "44100"
AUDIO_CHANNELS = "2"

DOWNLOAD_RETRIES = 10
FRAGMENT_RETRIES = 10
SOCKET_TIMEOUT = 30

RECONNECT_DELAY = 10

shutdown_requested = False
ffmpeg_process = None


# ============================================================
# LOG
# ============================================================

def log(message=""):
    print(message, flush=True)


# ============================================================
# SIGNALS
# ============================================================

def handle_signal(signum, frame):
    global shutdown_requested

    shutdown_requested = True

    log("")
    log("=" * 70)
    log("[SYSTEM] Shutdown requested...")
    log("=" * 70)


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


# ============================================================
# DOWNLOAD ONE VIDEO
# ============================================================

def download_video(index, url):

    output_template = str(
        MEDIA_DIR / f"video_{index:02d}.%(ext)s"
    )

    existing_files = [
        p for p in MEDIA_DIR.glob(f"video_{index:02d}.*")
        if not p.name.endswith(".part")
    ]

    if existing_files:
        log(
            f"[VIDEO {index}] Cached file found: "
            f"{existing_files[0].name}"
        )
        return existing_files[0]

    log("")
    log("=" * 70)
    log(f"[VIDEO {index}] Downloading")
    log(f"[VIDEO {index}] {url}")
    log("=" * 70)

    command = [
        "yt-dlp",

        "--no-playlist",

        "--format",
        FORMAT,

        "--merge-output-format",
        "mkv",

        "--retries",
        str(DOWNLOAD_RETRIES),

        "--fragment-retries",
        str(FRAGMENT_RETRIES),

        "--socket-timeout",
        str(SOCKET_TIMEOUT),

        "--concurrent-fragments",
        "2",

        "--output",
        output_template,

        url,
    ]

    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=None,
            stderr=None,
        )

    except Exception as e:
        log(f"[ERROR] Video {index} download error: {e}")
        return None

    if result.returncode != 0:
        log(
            f"[ERROR] Video {index} download failed "
            f"(exit code {result.returncode})"
        )
        return None

    files = [
        p for p in MEDIA_DIR.glob(f"video_{index:02d}.*")
        if not p.name.endswith(".part")
    ]

    if not files:
        log(f"[ERROR] Video {index}: downloaded file not found.")
        return None

    log(
        f"[VIDEO {index}] Ready: "
        f"{files[0].name}"
    )

    return files[0]


# ============================================================
# PREPARE ALL VIDEOS
# ============================================================

def prepare_videos():

    log("")
    log("=" * 70)
    log("PREPARING YOUTUBE VIDEOS")
    log("=" * 70)

    video_files = []

    for index, url in enumerate(VIDEOS, start=1):

        if shutdown_requested:
            return []

        file_path = download_video(
            index,
            url
        )

        if file_path is None:
            log(
                f"[ERROR] Could not prepare video {index}."
            )
            return []

        video_files.append(file_path)

    log("")
    log("=" * 70)
    log(
        f"[SYSTEM] {len(video_files)} videos prepared successfully."
    )
    log("=" * 70)

    return video_files


# ============================================================
# CREATE CONCAT FILE
# ============================================================

def create_concat_file(video_files):

    concat_path = MEDIA_DIR / "playlist.txt"

    try:

        with open(
            concat_path,
            "w",
            encoding="utf-8"
        ) as f:

            for video in video_files:

                absolute_path = video.resolve()

                path = str(
                    absolute_path
                ).replace(
                    "\\",
                    "/"
                )

                f.write(
                    "file '"
                    + path.replace("'", "'\\''")
                    + "'\n"
                )

        return concat_path

    except Exception as e:

        log(
            f"[ERROR] Could not create concat file: {e}"
        )

        return None


# ============================================================
# BUILD FFMPEG COMMAND
# ============================================================

def build_ffmpeg_command(concat_file):

    return [
        "ffmpeg",

        "-hide_banner",

        "-loglevel",
        "warning",

        "-stats",

        # Play at normal speed
        "-re",

        # One input containing the complete ordered playlist
        "-f",
        "concat",

        "-safe",
        "0",

        "-stream_loop",
        "-1",

        "-i",
        str(concat_file),

        # ====================================================
        # VIDEO
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
        "aac",

        "-b:a",
        AUDIO_BITRATE,

        "-ar",
        AUDIO_RATE,

        "-ac",
        AUDIO_CHANNELS,

        # ====================================================
        # TIMESTAMPS
        # ====================================================

        "-fflags",
        "+genpts+discardcorrupt",

        "-avoid_negative_ts",
        "make_zero",

        "-max_interleave_delta",
        "0",

        # ====================================================
        # OUTPUT
        # ====================================================

        "-f",
        "flv",

        RESTREAM_RTMP,
    ]


# ============================================================
# START ONE CONTINUOUS BROADCAST
# ============================================================

def start_broadcast(concat_file):

    global ffmpeg_process

    command = build_ffmpeg_command(
        concat_file
    )

    log("")
    log("=" * 70)
    log("STARTING ONE CONTINUOUS RESTREAM BROADCAST")
    log("=" * 70)

    log("[SYSTEM] Videos       : 8")
    log("[SYSTEM] Order        : 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8")
    log("[SYSTEM] Loop         : 8 -> 1")
    log("[SYSTEM] Video        : COPY")
    log("[SYSTEM] Video Encode : OFF")
    log("[SYSTEM] Audio        : AAC 128k")
    log("[SYSTEM] Audio Rate   : 44100 Hz")
    log("[SYSTEM] Channels     : Stereo")
    log("[SYSTEM] Max Quality  : 1080p")
    log("[SYSTEM] RTMP         : ONE CONNECTION")
    log("[SYSTEM] Destination  : Restream")
    log("=" * 70)

    try:

        ffmpeg_process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=None,
        )

    except Exception as e:

        log(
            f"[ERROR] Could not start FFmpeg: {e}"
        )

        ffmpeg_process = None

        return False

    log("")
    log("[SYSTEM] FFmpeg started.")
    log("[SYSTEM] Restream connection is being established...")
    log("")

    while not shutdown_requested:

        time.sleep(5)

        if ffmpeg_process.poll() is not None:

            exit_code = (
                ffmpeg_process.returncode
            )

            log("")
            log(
                "[ERROR] FFmpeg stopped."
            )

            log(
                f"[ERROR] Exit code: {exit_code}"
            )

            return False

        log(
            "[SYSTEM] ONE broadcast is RUNNING..."
        )

    return True


# ============================================================
# STOP FFMPEG
# ============================================================

def stop_ffmpeg():

    global ffmpeg_process

    if ffmpeg_process is None:
        return

    try:

        if ffmpeg_process.poll() is None:

            log(
                "[SYSTEM] Stopping FFmpeg..."
            )

            ffmpeg_process.terminate()

            try:

                ffmpeg_process.wait(
                    timeout=10
                )

            except subprocess.TimeoutExpired:

                log(
                    "[SYSTEM] FFmpeg did not stop."
                )

                log(
                    "[SYSTEM] Killing FFmpeg..."
                )

                ffmpeg_process.kill()

                try:
                    ffmpeg_process.wait(
                        timeout=5
                    )
                except Exception:
                    pass

    except Exception as e:

        log(
            f"[SYSTEM] FFmpeg stop error: {e}"
        )

    ffmpeg_process = None


# ============================================================
# MAIN
# ============================================================

def main():

    global shutdown_requested

    log("")
    log("=" * 70)
    log("       YOUTUBE 8 VIDEOS -> RESTREAM -> TIKTOK")
    log("=" * 70)

    log("")
    log("VIDEO ORDER:")

    for index, url in enumerate(
        VIDEOS,
        start=1
    ):
        log(
            f"{index}. {url}"
        )

    log("")
    log("[SYSTEM] Mode        : 24/7")
    log("[SYSTEM] Video       : COPY")
    log("[SYSTEM] Video Encode: OFF")
    log("[SYSTEM] Quality     : BEST <= 1080p")
    log("[SYSTEM] Audio       : AAC 128k")
    log("[SYSTEM] RTMP        : ONE CONTINUOUS SESSION")
    log("=" * 70)

    # ========================================================
    # PREPARE VIDEOS
    # ========================================================

    video_files = prepare_videos()

    if shutdown_requested:
        return

    if len(video_files) != len(VIDEOS):

        log("")
        log(
            "[ERROR] Not all videos were prepared."
        )

        return

    # ========================================================
    # CONCAT FILE
    # ========================================================

    concat_file = create_concat_file(
        video_files
    )

    if concat_file is None:
        return

    log("")
    log(
        f"[SYSTEM] Playlist file: {concat_file}"
    )

    # ========================================================
    # START FOREVER
    # ========================================================

    while not shutdown_requested:

        start_broadcast(
            concat_file
        )

        if shutdown_requested:
            break

        stop_ffmpeg()

        log("")
        log(
            f"[SYSTEM] Reconnecting in "
            f"{RECONNECT_DELAY} seconds..."
        )

        time.sleep(
            RECONNECT_DELAY
        )

    stop_ffmpeg()

    log("")
    log("=" * 70)
    log("[SYSTEM] Relay stopped.")
    log("=" * 70)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        shutdown_requested = True

        log(
            "[SYSTEM] Keyboard interrupt."
        )

    except Exception as e:

        shutdown_requested = True

        log("")
        log("=" * 70)
        log("[SYSTEM] UNEXPECTED ERROR")
        log(
            f"[SYSTEM] {type(e).__name__}: {e}"
        )
        log("=" * 70)

    finally:

        stop_ffmpeg()
