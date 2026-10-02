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
        log("[COOKIES] OFF - YOUTUBE_COOKIES_B64 is not set.")
        return None

    try:
        data = base64.b64decode(cookies_b64, validate=True)

        with open(COOKIES_FILE, "wb") as f:
            f.write(data)

        size = len(data)
        log(f"[COOKIES] File decoded successfully: {size} bytes")

        with open(COOKIES_FILE, "rb") as f:
            first_line = f.readline().decode("utf-8", errors="replace").strip()

        if first_line not in (
            "# HTTP Cookie File",
            "# Netscape HTTP Cookie File",
        ):
            log("[COOKIES] ERROR: File is not Mozilla/Netscape cookies format.")
            log(f"[COOKIES] First line received: {first_line[:120]}")
            return None

        log("[COOKIES] Format check: OK")
        return COOKIES_FILE

    except Exception as e:
        log(f"[COOKIES] ERROR: Cannot decode/check cookies: {e}")
        return None


def check_runtime():
    log("============================================================")
    log("[SYSTEM] Runtime check")
    log("============================================================")

    try:
        deno = subprocess.run(
            ["deno", "--version"],
            capture_output=True,
            text=True,
        )
        log("[DENO]")
        log(deno.stdout.strip() or deno.stderr.strip())
    except Exception as e:
        log(f"[DENO] ERROR: {e}")
        return False

    try:
        ytdlp = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True,
            text=True,
        )
        log(f"[yt-dlp] {ytdlp.stdout.strip() or ytdlp.stderr.strip()}")
    except Exception as e:
        log(f"[yt-dlp] ERROR: {e}")
        return False

    return True


def test_youtube_access(cookies):
    log("============================================================")
    log("[SYSTEM] Testing YouTube access before download")
    log("============================================================")

    command = [
        "yt-dlp",
        "--no-playlist",
        "--simulate",
        "--no-warnings",
        "--js-runtimes",
        "deno",
        "--no-check-certificates",
    ]

    if cookies:
        command.extend(["--cookies", cookies])

    user_agent = os.getenv("YOUTUBE_USER_AGENT", "").strip()
    if user_agent:
        command.extend(["--user-agent", user_agent])
        log("[TEST] Custom browser User-Agent: ON")
    else:
        log("[TEST] Custom browser User-Agent: OFF")

    command.append(YOUTUBE_URL)

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    combined = (result.stdout + "\n" + result.stderr).strip()

    if result.returncode == 0:
        log("[TEST] YouTube extraction test: PASS")
        return True

    log("[TEST] YouTube extraction test: FAILED")
    log("")
    log(combined[-6000:])
    log("")

    if "Sign in to confirm you're not a bot" in combined:
        if cookies:
            log("[TEST] YouTube still rejected the request with the supplied cookies.")
            log("[TEST] This can be caused by expired/invalid cookies, mismatched browser session/User-Agent,")
            log("[TEST] or Railway's current IP being challenged by YouTube.")
        else:
            log("[TEST] YouTube is challenging the Railway request and no cookies were supplied.")

    return False


def download_video(cookies):
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
        "--js-runtimes",
        "deno",
    ]

    if cookies:
        command.extend(["--cookies", cookies])

    user_agent = os.getenv("YOUTUBE_USER_AGENT", "").strip()
    if user_agent:
        command.extend(["--user-agent", user_agent])

    command.append(YOUTUBE_URL)

    log("[SYSTEM] Selecting best compatible quality...")
    log("[SYSTEM] Target: up to 1080p / 60 FPS / H.264")

    result = subprocess.run(command)

    if result.returncode != 0:
        log("[ERROR] yt-dlp download failed.")
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
    log(" Deno + yt-dlp cookies test")
    log("============================================================")

    if not check_runtime():
        log("[FATAL] Runtime check failed.")
        sys.exit(1)

    cookies = prepare_cookies()

    if os.getenv("YOUTUBE_COOKIES_B64") and not cookies:
        log("[FATAL] YOUTUBE_COOKIES_B64 exists but the cookie file failed validation.")
        sys.exit(1)

    if not test_youtube_access(cookies):
        log("[FATAL] YouTube access test failed. Download will NOT start.")
        log("[FATAL] This prevents Railway from repeatedly crashing without a useful diagnosis.")
        sys.exit(1)

    if not download_video(cookies):
        log("[FATAL] Could not download YouTube video.")
        sys.exit(1)

    show_video_info()
    start_stream()


if __name__ == "__main__":
    main()
