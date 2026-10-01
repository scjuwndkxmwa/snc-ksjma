```python
import os
import time
import signal
import subprocess
import sys
from pathlib import Path

# ============================================================
# SETTINGS
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
# QUALITY
# ============================================================

# Highest available video up to 1080p
VIDEO_FORMAT = (
    "bestvideo[height<=1080]+bestaudio/"
    "best[height<=1080]/"
    "bestvideo+bestaudio/"
    "best"
)

AUDIO_BITRATE = "128k"
AUDIO_RATE = "44100"
AUDIO_CHANNELS = "2"

# ============================================================
# STORAGE
# ============================================================

MEDIA_DIR = Path("/tmp/youtube_playlist")

MEDIA_DIR.mkdir(
    parents=True,
    exist_ok=True
)

# ============================================================
# DOWNLOAD SETTINGS
# ============================================================

DOWNLOAD_RETRIES = 10
FRAGMENT_RETRIES = 10
SOCKET_TIMEOUT = 30

# ============================================================
# LOOP
# ============================================================

BETWEEN_VIDEOS = 1
RETRY_DELAY = 10

shutdown_requested = False
ffmpeg_process = None


# ============================================================
# LOG
# ============================================================

def log(message=""):
    print(message, flush=True)


# ============================================================
# SIGNAL
# ============================================================

def handle_signal(signum, frame):
    global shutdown_requested

    shutdown_requested = True

    log("")
    log("=" * 70)
    log("[SYSTEM] Shutdown requested...")
    log("=" * 70)


signal.signal(
    signal.SIGINT,
    handle_signal
)

signal.signal(
    signal.SIGTERM,
    handle_signal
)


# ============================================================
# RUN COMMAND
# ============================================================

def run_command(command):

    log("")
    log("[COMMAND]")
    log(" ".join(command))
    log("")

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=None,
            text=True
        )

        return result.returncode

    except Exception as e:

        log(
            f"[ERROR] Command failed: {e}"
        )

        return -1


# ============================================================
# GET VIDEO FILE
# ============================================================

def get_video_file(index, url):

    output_template = str(
        MEDIA_DIR / f"video_{index:02d}.%(ext)s"
    )

    # Existing files
    existing = list(
        MEDIA_DIR.glob(
            f"video_{index:02d}.*"
        )
    )

    if existing:

        # Ignore temporary files
        valid = [
            p for p in existing
            if not p.name.endswith(".part")
        ]

        if valid:

            log(
                f"[VIDEO {index}] "
                f"Using cached file: {valid[0]}"
            )

            return valid[0]

    log("")
    log("=" * 70)
    log(
        f"[VIDEO {index}] Downloading highest available quality"
    )
    log(f"[VIDEO {index}] {url}")
    log("=" * 70)

    command = [
        "yt-dlp",

        "--no-playlist",

        "--format",
        VIDEO_FORMAT,

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

        "--no-part",

        "--output",
        output_template,

        url
    ]

    return_code = run_command(
        command
    )

    if return_code != 0:

        log(
            f"[VIDEO {index}] "
            "Download failed."
        )

        return None

    files = list(
        MEDIA_DIR.glob(
            f"video_{index:02d}.*"
        )
    )

    valid = [
        p for p in files
        if not p.name.endswith(".part")
    ]

    if not valid:

        log(
            f"[VIDEO {index}] "
            "Downloaded file not found."
        )

        return None

    return valid[0]


# ============================================================
# DOWNLOAD ALL VIDEOS
# ============================================================

def prepare_videos():

    log("")
    log("=" * 70)
    log("       PREPARING 8 YOUTUBE VIDEOS")
    log("=" * 70)

    video_files = []

    for index, url in enumerate(
        VIDEOS,
        start=1
    ):

        if shutdown_requested:
            return []

        file_path = get_video_file(
            index,
            url
        )

        if file_path is None:

            log(
                f"[VIDEO {index}] "
                "Could not prepare video."
            )

            return []

        video_files.append(
            file_path
        )

    log("")
    log("=" * 70)
    log(
        f"[SYSTEM] All {len(video_files)} videos are ready."
    )
    log("=" * 70)

    return video_files


# ============================================================
# CREATE CONCAT FILE
# ============================================================

def create_concat_file(video_files):

    concat_file = (
        MEDIA_DIR / "playlist.txt"
    )

    try:

        with open(
            concat_file,
            "w",
            encoding="utf-8"
        ) as f:

            for video in video_files:

                path = str(
                    video
                ).replace(
                    "\\",
                    "/"
                )

                path = path.replace(
                    "'",
                    "'\\''"
                )

                f.write(
                    f"file '{path}'\n"
                )

        return concat_file

    except Exception as e:

        log(
            f"[ERROR] "
            f"Could not create concat file: {e}"
        )

        return None


# ============================================================
# BUILD FFMPEG
# ============================================================

def build_ffmpeg_command(
    concat_file
):

    return [

        "ffmpeg",

        "-hide_banner",

        "-loglevel",
        "warning",

        "-stats",

        "-re",

        "-f",
        "concat",

        "-safe",
        "0",

        "-stream_loop",
        "-1",

        "-i",
        str(concat_file),

        # -------------------------
        # VIDEO
        # -------------------------

        "-map",
        "0:v:0",

        "-c:v",
        "copy",

        # -------------------------
        # AUDIO
        # -------------------------

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

        # -------------------------
        # TIMESTAMPS
        # -------------------------

        "-fflags",
        "+genpts+discardcorrupt",

        "-avoid_negative_ts",
        "make_zero",

        "-max_interleave_delta",
        "0",

        # -------------------------
        # FLV / RTMP
        # -------------------------

        "-f",
        "flv",

        RESTREAM_RTMP
    ]


# ============================================================
# START BROADCAST
# ============================================================

def start_broadcast(
    concat_file
):

    global ffmpeg_process

    command = build_ffmpeg_command(
        concat_file
    )

    log("")
    log("=" * 70)
    log("       STARTING ONE CONTINUOUS BROADCAST")
    log("=" * 70)

    log("[SYSTEM] Destination : Restream")
    log("[SYSTEM] Videos      : 8")
    log("[SYSTEM] Order       : 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8")
    log("[SYSTEM] Loop        : 8 -> 1")
    log("[SYSTEM] Video       : COPY")
    log("[SYSTEM] Video Encode: OFF")
    log(
        f"[SYSTEM] Audio       : AAC {AUDIO_BITRATE}"
    )
    log("[SYSTEM] Resolution  : Highest available <= 1080p")
    log("[SYSTEM] RTMP        : ONE CONTINUOUS CONNECTION")
    log("=" * 70)

    try:

        ffmpeg_process = subprocess.Popen(
            command,

            stdin=subprocess.DEVNULL,

            stdout=subprocess.DEVNULL,

            stderr=None
        )

    except Exception as e:

        log(
            f"[ERROR] "
            f"Could not start FFmpeg: {e}"
        )

        ffmpeg_process = None

        return False

    log("")
    log(
        "[SYSTEM] FFmpeg started."
    )

    log(
        "[SYSTEM] YouTube -> FFmpeg -> Restream"
    )

    log(
        "[SYSTEM] ONE BROADCAST SESSION"
    )

    log("")

    while not shutdown_requested:

        time.sleep(5)

        if ffmpeg_process.poll() is not None:

            code = (
                ffmpeg_process.returncode
            )

            log("")
            log(
                "[ERROR] FFmpeg stopped."
            )

            log(
                f"[ERROR] Exit code: {code}"
            )

            return False

        log(
            "[SYSTEM] Broadcast is RUNNING..."
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
                    "[SYSTEM] Killing FFmpeg..."
                )

                ffmpeg_process.kill()

                ffmpeg_process.wait(
                    timeout=5
                )

    except Exception as e:

        log(
            f"[SYSTEM] "
            f"FFmpeg stop error: {e}"
        )

    ffmpeg_process = None


# ============================================================
# MAIN
# ============================================================

def main():

    global shutdown_requested

    log("")
    log("=" * 70)
    log("       YOUTUBE 8 VIDEOS 24/7")
    log("       -> ONE FFMPEG -> RESTREAM")
    log("=" * 70)

    log("")
    log("VIDEO ORDER:")

    for index, url in enumerate(
        VIDEOS,
        start=1
    ):

        log(
            f"  {index}. {url}"
        )

    log("")
    log(
        "[SYSTEM] Highest quality: ENABLED"
    )

    log(
        "[SYSTEM] Maximum resolution: 1080p"
    )

    log(
        "[SYSTEM] Video copy: ENABLED"
    )

    log(
        "[SYSTEM] Audio encode: AAC 128k"
    )

    log(
        "[SYSTEM] Continuous RTMP: ENABLED"
    )

    log(
        "[SYSTEM] 24/7 LOOP: ENABLED"
    )

    log("=" * 70)

    # ---------------------------------
    # Prepare videos
    # ---------------------------------

    video_files = prepare_videos()

    if not video_files:

        log(
            "[ERROR] "
            "Could not prepare videos."
        )

        return

    # ---------------------------------
    # Create concat playlist
    # ---------------------------------

    concat_file = create_concat_file(
        video_files
    )

    if concat_file is None:

        return

    # ---------------------------------
    # Start one continuous RTMP
    # ---------------------------------

    while not shutdown_requested:

        success = start_broadcast(
            concat_file
        )

        if shutdown_requested:
            break

        stop_ffmpeg()

        if success:

            log(
                "[SYSTEM] Broadcast stopped."
            )

        else:

            log(
                "[SYSTEM] Broadcast failed."
            )

        log(
            f"[SYSTEM] Reconnecting in "
            f"{RETRY_DELAY} seconds..."
        )

        time.sleep(
            RETRY_DELAY
        )

    stop_ffmpeg()

    log("")
    log("=" * 70)
    log("[SYSTEM] Relay stopped.")
    log("=" * 70)


# ============================================================
# ENTRY
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

        log("")
        log("=" * 70)
        log("[SYSTEM] UNEXPECTED ERROR")
        log(
            f"[SYSTEM] "
            f"{type(e).__name__}: {e}"
        )
        log("=" * 70)

    finally:

        stop_ffmpeg()
```
