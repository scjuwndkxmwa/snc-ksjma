import os
import sys
import time
import base64
import subprocess

# ============================================================
# CONFIG
# ============================================================

YOUTUBE_URL = "https://www.youtube.com/live/cJFeAw3pkek?si=_JAHZD_-haE6JgRo"
YOUTUBE_STREAM_KEY = "70w6-cwe2-g22v-kz95-161h"
YOUTUBE_RTMP = "rtmp://a.rtmp.youtube.com/live2/" + YOUTUBE_STREAM_KEY

VIDEO_FILE = "/tmp/video.mp4"
COOKIES_FILE = "/tmp/youtube_cookies.txt"

SEP = "=" * 60
DASH = "-" * 60


# ============================================================
# LOG
# ============================================================

def log(message):
    print(message, flush=True)


# ============================================================
# COOKIES
# ============================================================

def prepare_cookies():
    cookies_b64 = os.getenv("YOUTUBE_COOKIES_B64")

    if not cookies_b64:
        log("[COOKIES] OFF")
        return None

    try:
        data = base64.b64decode(cookies_b64, validate=True)
        with open(COOKIES_FILE, "wb") as f:
            f.write(data)

        log(f"[COOKIES] Decoded: {len(data)} bytes")

        with open(COOKIES_FILE, "rb") as f:
            lines = f.readlines()

        cookie_lines = []
        for line in lines:
            line_str = line.decode("utf-8", errors="replace").strip()
            if line_str and not line_str.startswith("#"):
                cookie_lines.append(line_str)

        log(f"[COOKIES] Actual cookie entries: {len(cookie_lines)}")

        if len(cookie_lines) == 0:
            log("[COOKIES] WARNING: No actual cookies found.")
            log("[COOKIES] Continuing WITHOUT cookies.")
            return None

        first_line = lines[0].decode("utf-8", errors="replace").strip()
        if first_line not in ("# HTTP Cookie File", "# Netscape HTTP Cookie File"):
            log("[COOKIES] Invalid Netscape format.")
            return None

        log("[COOKIES] Format: OK")
        return COOKIES_FILE

    except Exception as e:
        log(f"[COOKIES] ERROR: {e}")
        return None


# ============================================================
# RUNTIME
# ============================================================

def check_runtime():
    log(SEP)
    log("[SYSTEM] Runtime check")
    log(SEP)

    try:
        res = subprocess.run(["/usr/local/bin/deno", "--version"], capture_output=True, text=True)
        log("[DENO] " + (res.stdout.strip() or res.stderr.strip()))
    except Exception as e:
        log(f"[DENO] ERROR: {e}")
        return False

    try:
        res = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True)
        log("[yt-dlp] " + (res.stdout.strip() or res.stderr.strip()))
    except Exception as e:
        log(f"[yt-dlp] ERROR: {e}")
        return False

    try:
        res = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        first_line = res.stdout.strip().splitlines()[0] if res.stdout.strip() else res.stderr.strip()
        log("[FFmpeg] " + first_line)
    except Exception as e:
        log(f"[FFmpeg] ERROR: {e}")
        return False

    return True


# ============================================================
# BUILD YT-DLP COMMAND
# ============================================================

def build_ytdlp_command(cookies, client_mode):
    command = [
        "yt-dlp",
        "--no-playlist",
        "--no-warnings",
        "--js-runtimes", "deno",
        "--remote-components", "ejs:npm",
        "--no-check-certificates",
        "--retries", "5",
        "--extractor-retries", "5",
        "--socket-timeout", "60"
    ]

    if client_mode == "default":
        log("[CLIENT] default")
    elif client_mode == "web_safari":
        command.extend([
            "--extractor-args", "youtube:player_client=default,web_safari",
            "--extractor-args", "youtube:webpage_client=web_safari"
        ])
        log("[CLIENT] default + web_safari")
    elif client_mode == "android_vr":
        command.extend(["--extractor-args", "youtube:player_client=android_vr"])
        log("[CLIENT] android_vr")
    elif client_mode == "tv":
        command.extend(["--extractor-args", "youtube:player_client=tv"])
        log("[CLIENT] tv")
    elif client_mode == "web_embedded":
        command.extend(["--extractor-args", "youtube:player_client=web_embedded"])
        log("[CLIENT] web_embedded")

    if cookies:
        command.extend(["--cookies", cookies])
        log("[COOKIES] ON")
    else:
        log("[COOKIES] OFF")

    command.append(YOUTUBE_URL)
    return command


# ============================================================
# TEST YOUTUBE
# ============================================================

def test_youtube_access(cookies):
    log(SEP)
    log("[SYSTEM] Testing YouTube access")
    log(SEP)

    clients = ["default", "web_safari", "android_vr", "tv", "web_embedded"]

    for client in clients:
        log("")
        log(DASH)
        log(f"[TEST] Trying client: {client}")
        log(DASH)

        command = build_ytdlp_command(cookies, client)
        command.insert(2, "--simulate")

        result = subprocess.run(command, capture_output=True, text=True)
        combined = (result.stdout + "\n" + result.stderr).strip()

        if result.returncode == 0:
            log(f"[SUCCESS] YouTube client works: {client}")
            return client

        log(f"[FAILED] Client {client}")
        log(combined[-1000:])
        time.sleep(2)

    log("")
    log(SEP)
    log("[FATAL] All YouTube clients failed.")
    log(SEP)
    return None


# ============================================================
# DOWNLOAD
# ============================================================

def download_video(cookies, working_client):
    if os.path.exists(VIDEO_FILE):
        try:
            size = os.path.getsize(VIDEO_FILE)
            if size > 10 * 1024 * 1024:
                log(f"[SYSTEM] Existing video found: {size / 1024 / 1024:.2f} MB")
                return True
        except Exception:
            pass

    try:
        if os.path.exists(VIDEO_FILE):
            os.remove(VIDEO_FILE)
    except Exception:
        pass

    log(SEP)
    log("[SYSTEM] Downloading YouTube video")
    log(SEP)
    log(f"[SOURCE] {YOUTUBE_URL}")

    format_selector = (
        "bestvideo[height=720]+bestaudio/best[height=720]/"
        "bestvideo[height<=720]+bestaudio/best[height<=720]"
    )

    command = [
        "yt-dlp",
        "--no-playlist",
        "-f", format_selector,
        "--merge-output-format", "mp4",
        "-o", VIDEO_FILE,
        "--no-part",
        "--retries", "10",
        "--fragment-retries", "10",
        "--extractor-retries", "10",
        "--socket-timeout", "60",
        "--concurrent-fragments", "4",
        "--js-runtimes", "deno",
        "--remote-components", "ejs:npm",
        "--no-check-certificates"
    ]

    if working_client == "web_safari":
        command.extend([
            "--extractor-args", "youtube:player_client=default,web_safari",
            "--extractor-args", "youtube:webpage_client=web_safari"
        ])
    elif working_client == "android_vr":
        command.extend(["--extractor-args", "youtube:player_client=android_vr"])
    elif working_client == "tv":
        command.extend(["--extractor-args", "youtube:player_client=tv"])
    elif working_client == "web_embedded":
        command.extend(["--extractor-args", "youtube:player_client=web_embedded"])

    if cookies:
        command.extend(["--cookies", cookies])

    command.append(YOUTUBE_URL)

    log("[SYSTEM] Target: 720p Resolution Only")
    log(f"[SYSTEM] Using client: {working_client}")

    result = subprocess.run(command)

    if result.returncode != 0 or not os.path.exists(VIDEO_FILE):
        log("[ERROR] yt-dlp download failed.")
        return False

    size = os.path.getsize(VIDEO_FILE)
    if size < 10 * 1024 * 1024:
        log("[ERROR] Video file too small.")
        return False

    log(f"[SUCCESS] Download completed. Size: {size / 1024 / 1024:.2f} MB")
    return True


# ============================================================
# VIDEO INFO
# ============================================================

def show_video_info():
    log(SEP)
    log("[SYSTEM] Video information")
    log(SEP)

    command = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height,r_frame_rate",
        "-of", "default=noprint_wrappers=1",
        VIDEO_FILE
    ]

    try:
        result = subprocess.run(command, capture_output=True, text=True)
        log(result.stdout.strip() or result.stderr.strip())
