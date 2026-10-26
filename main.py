import os
import time
import base64
import subprocess

# ============================================================
# CONFIG
# ============================================================

YOUTUBE_URL = "https://www.youtube.com/live/cJFeAw3pkek"
YOUTUBE_STREAM_KEY = "70w6-cwe2-g22v-kz95-161h"
YOUTUBE_RTMP = "rtmp://a.rtmp.youtube.com/live2/" + YOUTUBE_STREAM_KEY

LOOP = False  # True = يكرر الفيديو بدون توقف

VIDEO_FILE = "/tmp/video.mp4"
COOKIES_FILE = "/tmp/youtube_cookies.txt"

SEP = "=" * 60
DASH = "-" * 60

CLIENTS = ["default", "web_safari", "android_vr", "tv", "web_embedded"]


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

        lines = data.decode("utf-8", errors="replace").splitlines()
        entries = [l for l in lines if l.strip() and not l.startswith("#")]
        log(f"[COOKIES] Actual cookie entries: {len(entries)}")

        if not entries:
            log("[COOKIES] No cookies found. Continuing WITHOUT cookies.")
            return None

        first = lines[0].strip() if lines else ""
        if first not in ("# HTTP Cookie File", "# Netscape HTTP Cookie File"):
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

def run_version(name, cmd):
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        out = (res.stdout.strip() or res.stderr.strip()).splitlines()
        log(f"[{name}] " + (out[0] if out else "ok"))
        return True
    except Exception as e:
        log(f"[{name}] ERROR: {e}")
        return False


def check_runtime():
    log(SEP)
    log("[SYSTEM] Runtime check")
    log(SEP)
    ok = run_version("yt-dlp", ["yt-dlp", "--version"])
    ok = run_version("FFmpeg", ["ffmpeg", "-version"]) and ok
    run_version("DENO", ["deno", "--version"])
    return ok


# ============================================================
# YT-DLP
# ============================================================

def client_args(client):
    if client == "web_safari":
        return ["--extractor-args", "youtube:player_client=default,web_safari",
                "--extractor-args", "youtube:webpage_client=web_safari"]
    if client in ("android_vr", "tv", "web_embedded"):
        return ["--extractor-args", f"youtube:player_client={client}"]
    return []


def base_ytdlp(cookies, client):
    cmd = [
        "yt-dlp", "--no-playlist", "--no-warnings",
        "--js-runtimes", "deno",
        "--remote-components", "ejs:npm",
        "--no-check-certificates",
        "--retries", "5", "--extractor-retries", "5",
        "--socket-timeout", "60",
    ]
    cmd += client_args(client)
    if cookies:
        cmd += ["--cookies", cookies]
    return cmd


def test_youtube_access(cookies):
    log(SEP)
    log("[SYSTEM] Testing YouTube access")
    log(SEP)

    for client in CLIENTS:
        log(DASH)
        log(f"[TEST] Trying client: {client}")
        cmd = base_ytdlp(cookies, client) + ["--simulate", YOUTUBE_URL]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            log(f"[SUCCESS] Client works: {client}")
            return client

        log(f"[FAILED] Client {client}")
        log((result.stdout + "\n" + result.stderr).strip()[-1000:])
        time.sleep(2)

    log("[FATAL] All YouTube clients failed.")
    return None


def download_video(cookies, client):
    if os.path.exists(VIDEO_FILE):
        size = os.path.getsize(VIDEO_FILE)
        if size > 10 * 1024 * 1024:
            log(f"[SYSTEM] Existing video found: {size / 1024 / 1024:.2f} MB")
            return True
        os.remove(VIDEO_FILE)

    log(SEP)
    log("[SYSTEM] Downloading video (max 720p, H.264 preferred)")
    log(SEP)

    fmt = (
        "bv*[height<=720][vcodec^=avc1]+ba[ext=m4a]/"
        "bv*[height<=720]+ba/b[height<=720]/b"
    )

    cmd = base_ytdlp(cookies, client) + [
        "-f", fmt,
        "--merge-output-format", "mp4",
        "-o", VIDEO_FILE,
        "--no-part",
        "--fragment-retries", "10",
        "--concurrent-fragments", "4",
        YOUTUBE_URL,
    ]

    result = subprocess.run(cmd)
    if result.returncode != 0 or not os.path.exists(VIDEO_FILE):
        log("[ERROR] yt-dlp download failed.")
        return False

    size = os.path.getsize(VIDEO_FILE)
    if size < 1024 * 1024:
        log("[ERROR] Video file too small.")
        return False

    log(f"[SUCCESS] Downloaded {size / 1024 / 1024:.2f} MB")
    return True


# ============================================================
# VIDEO INFO
# ============================================================

def show_video_info():
    log(SEP)
    log("[SYSTEM] Video information")
    log(SEP)

    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height,r_frame_rate",
        "-of", "default=noprint_wrappers=1",
        VIDEO_FILE,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        log(result.stdout.strip() or result.stderr.strip())
    except Exception as e:
        log(f"[FFPROBE] ERROR: {e}")


# ============================================================
# STREAM
# ============================================================

def stream_video():
    log(SEP)
    log(f"[SYSTEM] Starting YouTube LIVE (loop={'ON' if LOOP else 'OFF'})")
    log(SEP)

    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-re"]
    if LOOP:
        cmd += ["-stream_loop", "-1"]
    cmd += [
        "-i", VIDEO_FILE,
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,fps=30,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast",
        "-b:v", "2500k", "-maxrate", "2500k", "-bufsize", "5000k",
        "-g", "60", "-keyint_min", "60",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-f", "flv", YOUTUBE_RTMP,
    ]

    result = subprocess.run(cmd)
    log(f"[SYSTEM] FFmpeg exited with code {result.returncode}")
    return result.returncode == 0


# ============================================================
# MAIN
# ============================================================

def main():
    if not check_runtime():
        return 1

    cookies = prepare_cookies()

    client = test_youtube_access(cookies)
    if not client:
        return 1

    if not download_video(cookies, client):
        return 1

    show_video_info()

    while True:
        ok = stream_video()
        if ok and not LOOP:
            log("[SYSTEM] Stream finished.")
            return 0
        log("[SYSTEM] Stream stopped, retrying in 10s...")
        time.sleep(10)


if __name__ == "__main__":
    raise SystemExit(main())
