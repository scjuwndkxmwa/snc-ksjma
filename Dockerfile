FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# تثبيت wgcf و wireproxy (Userspace Cloudflare WARP Proxy بدون حاجة لصلاحيات كيرنل)
RUN ARCH=$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/') \
    && WGCF_TAG=$(curl -fsSLI -o /dev/null -w '%{url_effective}' https://github.com/ViRb3/wgcf/releases/latest | awk -F/ '{print $NF}') \
    && curl -fsSL "https://github.com/ViRb3/wgcf/releases/download/${WGCF_TAG}/wgcf_${WGCF_TAG#v}_linux_${ARCH}" -o /usr/local/bin/wgcf \
    && chmod +x /usr/local/bin/wgcf \
    && curl -fsSL "https://github.com/pufferffish/wireproxy/releases/latest/download/wireproxy_linux_${ARCH}.tar.gz" -o /tmp/wireproxy.tar.gz \
    && tar -xzf /tmp/wireproxy.tar.gz -C /usr/local/bin wireproxy \
    && chmod +x /usr/local/bin/wireproxy \
    && rm -f /tmp/wireproxy.tar.gz

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -U pip && pip install --no-cache-dir -U -r requirements.txt

COPY main.py .

CMD ["python", "-u", "main.py"]
