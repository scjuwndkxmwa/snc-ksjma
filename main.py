# -*- coding: utf-8 -*-
import json
import os
import re
import shutil
import subprocess
import sys
import time

# ==========================================================
# رابط الفيديو ومفتاح بث يوتيوب
# ==========================================================
YOUTUBE_URL = "https://www.youtube.com/live/dNcDvu-LOx4?si=5uhpaqDkpY1a8Rj0"
STREAM_KEY = "50vb-qw3d-zvth-x1tg-acjw"
RTMP_SERVER = "rtmp://a.rtmp.youtube.com/live2"
# ==========================================================

SOCKS_PORT = "40000"
HTTP_PORT = "40001"
WGCF_DIR = "/tmp/wgcf"
WIREPROXY_CONF = "/tmp/wireproxy.conf"
WARP_ENDPOINTS = [
    "162.159.192.1:2408",
    "162.159.193.1:4500",
    "162.159.195.1:500",
]

YT_CLIENT_SETS = [
    [],
    ["--extractor-args", "youtube:player_client=tv_downgraded,web_safari,mweb"],
    ["--extractor-args", "youtube:player_client=android_vr,visionos,ios"],
]

_wireproxy_proc = None


def log(msg):
    print(msg, flush=True)


def verify_warp_proxy(retries=5):
    """التأكد من أن بروكسي WARP يمرر البيانات فعلياً."""
    for _ in range(retries):
        r = subprocess.run(
            [
                "curl", "-4", "-s", "--max-time", "8",
                "-x", f"socks5h://127.0.0.1:{SOCKS_PORT}",
                "https://www.cloudflare.com/cdn-cgi/trace",
            ],
            capture_output=True, text=True,
        )
        if r.returncode == 0 and "warp=" in r.stdout:
            ip_m = re.search(r"ip=([^\s]+)", r.stdout)
            warp_ip = ip_m.group(1) if ip_m else "OK"
            log(f"[WARP-Proxy] ✓ شغال بنجاح (IP: {warp_ip})")
            return True
        time.sleep(1.5)
    return False


def start_warp_proxy(force_new_account=True):
    """تسجيل هوية Cloudflare WARP وتشغيل wireproxy كـ SOCKS5 + HTTP Proxy."""
    global _wireproxy_proc

    if _wireproxy_proc and _wireproxy_proc.poll() is None:
        _wireproxy_proc.terminate()
        _wireproxy_proc.wait(timeout=5)

    os.makedirs(WGCF_DIR, exist_ok=True)
    acc_file = os.path.join(WGCF_DIR, "wgcf-account.toml")
    prof_file = os.path.join(WGCF_DIR, "wgcf-profile.conf")

    if force_new_account or not os.path.isfile(prof_file):
        for f in (acc_file, prof_file):
            if os.path.isfile(f):
                os.remove(f)

        registered = False
        for i in range(4):
            r = subprocess.run(["wgcf", "register", "--accept-tos"], cwd=WGCF_DIR, capture_output=True, text=True)
            if r.returncode == 0:
                registered = True
                break
            time.sleep(2 * (i + 1))

        if not registered:
            log("⚠️ فشل تسجيل حساب wgcf، جاري إعادة المحاولة...")
            return False

        r = subprocess.run(["wgcf", "generate"], cwd=WGCF_DIR, capture_output=True, text=True)
        if r.returncode != 0 or not os.path.isfile(prof_file):
            log("⚠️ فشل توليد ملف إعدادات WARP.")
            return False

    with open(prof_file, encoding="utf-8") as f:
        base_conf = f.read()

    # تنظيف الإعدادات لتكون IPv4 فقط ومتوافقة مع wireproxy
    cleaned_lines = []
    for line in base_conf.splitlines():
        if line.startswith("DNS ="):
            continue
        if line.startswith("Address =") and ":" in line:
            continue
        if line.startswith("AllowedIPs =") and ":" in line:
            continue
        cleaned_lines.append(line)
    cleaned_base = "\n".join(cleaned_lines)

    # تجربة بورتات Cloudflare WARP (2408 / 4500 / 500) لضمان الاتصال على Railway
    for ep in WARP_ENDPOINTS:
        conf_text = re.sub(r"Endpoint\s*=\s*.*", f"Endpoint = {ep}", cleaned_base)
        conf_text += f"\n\n[Socks5]\nBindAddress = 127.0.0.1:{SOCKS_PORT}\n\n[http]\nBindAddress = 127.0.0.1:{HTTP_PORT}\n"
        with open(WIREPROXY_CONF, "w", encoding="utf-8") as f:
            f.write(conf_text)

        if _wireproxy_proc and _wireproxy_proc.poll() is None:
            _wireproxy_proc.terminate()
            _wireproxy_proc.wait(timeout=5)

        _wireproxy_proc = subprocess.Popen(
            ["wireproxy", "-c", WIREPROXY_CONF],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(2)
        if verify_warp_proxy(retries=4):
            return True

    return False


def is_blocked(text):
    return bool(re.search(
        r"confirm you.{0,3}re not a bot|HTTP Error 429|Too Many Requests|Sign in to confirm",
        text or "", re.I,
    ))


def extract_stream_urls(url, client_idx):
    """استخراج روابط البث المباشرة بأعلى جودة H.264 عبر WARP Proxy فقط."""
    fmt = "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/bv*[vcodec^=avc1]+ba/b[vcodec^=avc1]/bv*+ba/b"
    cmd = [
        "yt-dlp", "--ignore-config", "--no-playlist", "--no-warnings",
        "--force-ipv4",
        "--proxy", f"socks5h://127.0.0.1:{SOCKS_PORT}",
        "-f", fmt, "-j",
        "--socket-timeout", "30", "--retries", "5",
    ]
    if shutil.which("node"):
        cmd += ["--js-runtimes", "node"]
    cmd += YT_CLIENT_SETS[client_idx % len(YT_CLIENT_SETS)]
    cmd += ["--", url]

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    lines = (r.stdout + "\n" + r.stderr).splitlines()
    for line in reversed(lines):
        if line.startswith("{"):
            try:
                info = json.loads(line)
                req_fmts = info.get("requested_formats")
                if req_fmts and len(req_fmts) >= 2:
                    v_url = req_fmts[0]["url"]
                    a_url = req_fmts[1]["url"]
                    headers = req_fmts[0].get("http_headers") or info.get("http_headers") or {}
                    return [v_url, a_url], headers, info.get("title", ""), ""
                elif info.get("url"):
                    headers = info.get("http_headers") or {}
                    return [info["url"]], headers, info.get("title", ""), ""
            except Exception:
                continue

    errs = [s.strip() for s in lines if "ERROR" in s]
    return None, {}, "", (" | ".join(errs[-2:]) or "فشل استخراج الروابط")


def relay_stream(stream_urls, headers, rtmp_target):
    """نقل الفيديو بأعلى جودة زي ما هو (-c:v copy) إلى YouTube Live."""
    hdr_str = "".join(f"{k}: {v}\r\n" for k, v in headers.items() if k.lower() != "host")

    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-stats"]

    for u in stream_urls:
        cmd += ["-http_proxy", f"http://127.0.0.1:{HTTP_PORT}"]
        if hdr_str:
            cmd += ["-headers", hdr_str]
        cmd += [
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            "-re",
            "-i", u,
        ]

    if len(stream_urls) >= 2:
        cmd += ["-map", "0:v:0", "-map", "1:a:0"]
    else:
        cmd += ["-map", "0:v:0", "-map", "0:a:0"]

    cmd += [
        "-c:v", "copy",
        "-fps_mode", "passthrough",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-ac", "2",
        "-af", "aresample=async=1000",
        "-f", "flv",
        rtmp_target,
    ]

    proc = subprocess.run(cmd)
    return proc.returncode


if __name__ == "__main__":
    url = (os.environ.get("YOUTUBE_URL") or YOUTUBE_URL).strip()
    key = (os.environ.get("STREAM_KEY") or STREAM_KEY).strip()
    rtmp = (os.environ.get("RTMP_SERVER") or RTMP_SERVER).strip().rstrip("/")

    if not url:
        log("❌ ضع رابط اليوتيوب في YOUTUBE_URL أولاً.")
        sys.exit(1)
    if not key:
        log("❌ ضع مفتاح بث يوتيوب في STREAM_KEY أولاً.")
        sys.exit(1)

    rtmp_target = f"{rtmp}/{key}"

    while not start_warp_proxy(force_new_account=True):
        log("⚠️ تعذر تشغيل WARP Proxy، إعادة المحاولة بعد 5 ثوانٍ...")
        time.sleep(5)

    client_idx = 0
    while True:
        log(f"\n🔍 [WARP-Proxy] جاري سحب أعلى جودة للرابط (client_set={client_idx % len(YT_CLIENT_SETS)})...")
        urls, headers, title, err = extract_stream_urls(url, client_idx)

        if not urls:
            log(f"⚠️ فشل الاستخراج عبر [WARP-Proxy]: {err[:160]}")
            if is_blocked(err) or "Connection refused" in err:
                log("[WARP-Proxy] جاري تغيير الـ IP والحصول على هوية جديدة...")
                start_warp_proxy(force_new_account=True)
            client_idx += 1
            time.sleep(3)
            continue

        log(f"✅ العنوان: {title}")
        log("🚀 بدأ النقل المباشر بأعلى جودة (Copy) إلى يوتيوب عبر [WARP-Proxy]...")
        rc = relay_stream(urls, headers, rtmp_target)

        if rc == 0:
            log("✅ انتهى البث/الفيديو بشكل طبيعي.")
            break

        log(f"⚠️ توقف البث (كود {rc})، جاري تحديث الروابط وإعادة الاتصال...")
        client_idx += 1
        time.sleep(3)
