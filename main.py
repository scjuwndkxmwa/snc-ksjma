import os
import sys
import time
import base64
import subprocess

YOUTUBE_URL = "https://youtu.be/c3YZbShLyBM"

RESTREAM_STREAM_KEY = "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9"
RESTREAM_RTMP = "rtmp://live.restream.io/live/" + RESTREAM_STREAM_KEY

VIDEO_FILE = "/tmp/video.mp4"
COOKIES_FILE = "/tmp/youtube_cookies.txt"


def log(message):
    print(message, flush=True)


def prepare_cookies():
    cookies_b64 = os.getenv("YOUTUBE_COOKIES_B64")

    if not cookies_b64:
        log("[SYSTEM] YouTube cookies: OFF")
        return None

    try:
        data = base64.b64decode(cookies_b64)
        with open(COOKIES_FILE, "wb") as f:
            f.write(data)

        log("[SYSTEM] YouTube cookies: ON")
        return COOKIES_FILE

    except Exception as e:
        log(f"[WARN] Could not prepare cookies: {e}")
        return None


def download_video():
    if os.path.exists(VIDEO_FILE):
        try:
            if os.path.getsize(VIDEO_FILE) > 10 * 1024 * 1024:
                log("[SYSTEM] Existing video found.")
                return True
        except Exception:
            pass

    try:
        if os.path.exists(VIDEO_FILE):
            os.remove(VIDEO_FILE)
    except Exception:
        pass

    log("============================================================")
    log("[SYSTEM] Downloading YouTube video")
    log("============================================================")
    log(f"[SOURCE] {YOUTUBE_URL}")

    cookies = prepare_cookies()

    format_selector = (
        "bestvideo[height<=1080][fps<=60][vcodec^=avc1]+"
        "bestaudio[ext=m4a]/"
        "best[height<=1080][fps<=60][vcodec^=avc1]/"
        "bestvideo[height<=1080][fps<=60][vcodec^=avc1]+"
        "bestaudio/"
        "best[height<=1080][fps<=60]/"
        "best"
    )

    command = [
        "yt-dlp",
        "--no-playlist",
        "-f",
        format_selector,
        "--merge-output-format",
        "mp4",
        "-o",
        VIDEO_FILE,
        "--no-part",
        "--retries",
        "10",
        "--fragment-retries",
        "10",
        "--socket-timeout",
        "60",
        "--concurrent-fragments",
        "4",
    ]

    if cookies:
        command.extend(["--cookies", cookies])

    command.append(YOUTUBE_URL)

    log("[SYSTEM] Selecting best compatible quality...")
    log("[SYSTEM] Target: up to 1080p / 60 FPS / H.264")

    result = subprocess.run(command)

    if result.returncode != 0:
        log("[ERROR] yt-dlp failed.")
        return False

    if not os.path.exists(VIDEO_FILE):
        log("[ERROR] Video file was not created.")
        return False

    size = os.path.getsize(VIDEO_FILE)

    if size < 10 * 1024 * 1024:
        log("[ERROR] Downloaded file is too small.")
        return False

    log(f"[SYSTEM] Download completed: {size / (1024 * 1024):.2f} MB")
    return True


def show_video_info():
    log("============================================================")
    log("[SYSTEM] Video information")
    log("============================================================")

    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,width,height,r_frame_rate",
        "-of",
        "default=noprint_wrappers=1",
        VIDEO_FILE,
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
        )

        if result.stdout.strip():
            log(result.stdout.strip())

    except Exception as e:
        log(f"[WARN] ffprobe failed: {e}")


def start_stream():
    log("============================================================")
    log("[SYSTEM] Starting 24/7 stream")
    log("============================================================")
    log("[VIDEO] COPY - NO VIDEO ENCODING")
    log("[AUDIO] AAC 128k / 44100 Hz / Stereo")
    log("[LOOP] INFINITE")
    log("============================================================")

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-re",
        "-stream_loop",
        "-1",
        "-i",
        VIDEO_FILE,
        "-map",
        "0:v:0",
        "-c:v",
        "copy",
        "-map",
        "0:a:0?",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-fflags",
        "+genpts",
        "-avoid_negative_ts",
        "make_zero",
        "-f",
        "flv",
        RESTREAM_RTMP,
    ]

    while True:
        process = None

        try:
            log("[SYSTEM] Connecting to Restream...")
            process = subprocess.Popen(command)
            return_code = process.wait()
            log(f"[SYSTEM] FFmpeg stopped. Exit code: {return_code}")

        except KeyboardInterrupt:
            log("[SYSTEM] Stopping...")
            if process:
                try:
                    process.terminate()
                except Exception:
                    pass
            sys.exit(0)

        except Exception as e:
            log(f"[ERROR] FFmpeg error: {e}")

        log("[SYSTEM] Reconnecting in 10 seconds...")
        time.sleep(10)


def main():
    log("============================================================")
    log(" YouTube -> Restream 24/7")
    log("============================================================")

    if not download_video():
        log("[FATAL] Could not download YouTube video.")
        sys.exit(1)

    show_video_info()
    start_stream()


if __name__ == "__main__":
    main()
