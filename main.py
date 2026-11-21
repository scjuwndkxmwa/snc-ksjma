import base64
import glob
import os
import shutil
import subprocess
import time

# ============================================================
# CONFIG
# ============================================================
YOUTUBE_URL = os.getenv("YOUTUBE_URL", "https://www.youtube.com/live/dNcDvu-LOx4")
YOUTUBE_STREAM_KEY = "50vb-qw3d-zvth-x1tg-acjw"
YOUTUBE_RTMP = "rtmp://a.rtmp.youtube.com/live2/" + YOUTUBE_STREAM_KEY
LOOP = os.getenv("LOOP", "0") == "1"
WORK_DIR = "/data" if os.path.isdir("/data") and os.access("/data", os.W_OK) else "/tmp"
VIDEO_BASE = os.path.join(WORK_DIR, "video")  # final file: video.mp4
VIDEO_FILE = VIDEO_BASE + ".mp4"
COOKIES_FILE = "/tmp/youtube_cookies.txt"
SEP = "=" * 60
CLIENTS = ["default", "web_safari", "tv", "android_vr", "web_embedded"]


def log(m):
    print(m, flush=True)


def prepare_cookies():
    b64 = os.getenv("YOUTUBE_COOKIES_B64")
    if not b64:
        log("[COOKIES] OFF")
        return None
    try:
        data = base64.b64decode(b64)
        text = data.decode("utf-8", errors="replace")
        entries = [l for l in text.splitlines() if l.strip() and not l.startswith("#")]
        if not entries:
            log("[COOKIES] empty, continuing without")
            return None
        with open(COOKIES_FILE, "wb") as f:
            f.write(data)
        log(f"[COOKIES] OK ({len(entries)} entries)")
        return COOKIES_FILE
    except Exception as e:
        log(f"[COOKIES] ERROR: {e}")
        return None


def ver(name, cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
        out = (r.stdout.strip() or r.stderr.strip()).splitlines()
        log(f"[{name}] " + (out[0] if out else "ok"))
        return True
    except Exception as e:
        log(f"[{name}] ERROR: {e}")
        return False


def check_runtime():
    log(SEP)
    du = shutil.disk_usage(WORK_DIR)
    log(f"[DISK] {WORK_DIR} free={du.free / 1024**3:.2f} GiB")
    ok = ver("yt-dlp", ["yt-dlp", "--version"])
    ok = ver("FFmpeg", ["ffmpeg", "-version"]) and ok
    ver("DENO", ["deno", "--version"])
    return ok


def client_args(client):
    if client == "web_safari":
        return ["--extractor-args", "youtube:player_client=default,web_safari"]
    if client in ("android_vr", "tv", "web_embedded"):
        return ["--extractor-args", f"youtube:player_client={client}"]
    return []


def base_ytdlp(cookies, client):
    cmd = [
        "yt-dlp", "--no-playlist", "--no-warnings",
        "--js-runtimes", "deno", "--remote-components", "ejs:npm",
        "--retries", "10", "--extractor-retries", "5",
        "--socket-timeout", "60",
    ]
    cmd += client_args(client)
    if cookies:
        cmd += ["--cookies", cookies]
    return cmd


def probe(path):
    """Return (width, height, duration_seconds) or None."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height:format=duration",
             "-of", "default=noprint_wrappers=1", path],
            capture_output=True, text=True)
        d = dict(l.split("=", 1) for l in r.stdout.split() if "=" in l)
        return int(d["width"]), int(d["height"]), float(d.get("duration", 0) or 0)
    except Exception:
        return None


def cleanup_partials():
    for f in glob.glob(VIDEO_BASE + ".*"):
        if f != VIDEO_FILE:
            os.remove(f)


def download_video(cookies):
    if os.path.exists(VIDEO_FILE):
        p = probe(VIDEO_FILE)
        if p and os.path.getsize(VIDEO_FILE) > 10 * 1024 * 1024 and p[2] > 0:
            log(f"[SYSTEM] Using cached video {p[0]}x{p[1]} {p[2] / 60:.1f} min")
            return True
        os.remove(VIDEO_FILE)

    log(SEP)
    log("[SYSTEM] Downloading FULL video at 720p")
    log(SEP)

    for client in CLIENTS:
        log(f"[YT-DLP] client={client}")
        cmd = base_ytdlp(cookies, client) + [
            # 720p: res = SHORTER side, so 720x1280 (vertical) or 1280x720 both match
            "-f", "bv*+ba/b",
            "-S", "res:720,fps,vcodec:h264,acodec:aac",
            "--live-from-start",       # if still live: from the beginning
            "--merge-output-format", "mp4",
            "-o", VIDEO_FILE, "--continue",
            "--fragment-retries", "30",
            "--concurrent-fragments", "4",
            "--newline", "--progress-delta", "15",
            YOUTUBE_URL,
        ]
        r = subprocess.run(cmd)
        if r.returncode == 0 and os.path.exists(VIDEO_FILE):
            p = probe(VIDEO_FILE)
            if p and p[2] > 0:
                log(f"[SUCCESS] {p[0]}x{p[1]}, {p[2] / 60:.1f} min, "
                    f"{os.path.getsize(VIDEO_FILE) / 1024**2:.1f} MB")
                return True
        log(f"[YT-DLP] failed with {client}, trying next")
        time.sleep(3)
    cleanup_partials()
    log("[ERROR] all clients failed")
    return False


def stream_video():
    w, h, dur = probe(VIDEO_FILE) or (0, 0, 0)
    # keep the EXACT source dimensions: no scale, no pad, no crop
    ow, oh = w, h
    vbr = "4500k"
    vf = "setsar=1,fps=30,format=yuv420p"
    log(SEP)
    log(f"[SYSTEM] Streaming {ow}x{oh} @ {vbr}, full length {dur / 60:.1f} min")
    log(SEP)

    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-re"]
    if LOOP:
        cmd += ["-stream_loop", "-1"]
    bs = str(int(vbr[:-1]) * 2) + "k"
    cmd += [
        "-i", VIDEO_FILE, "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast",
        "-b:v", vbr, "-maxrate", vbr, "-bufsize", bs,
        "-g", "60", "-keyint_min", "60",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-f", "flv", YOUTUBE_RTMP,
    ]
    r = subprocess.run(cmd)
    log(f"[SYSTEM] FFmpeg exited with code {r.returncode}")
    return r.returncode == 0


def main():
    if not check_runtime():
        return 1
    if not download_video(prepare_cookies()):
        return 1
    while True:
        if stream_video() and not LOOP:
            log("[SYSTEM] Stream finished.")
            return 0
        log("[SYSTEM] Stream stopped, retrying in 10s...")
        time.sleep(10)


if __name__ == "__main__":
    raise SystemExit(main())
