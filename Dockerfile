FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    curl \
    gnupg \
    ca-certificates \
    lsb-release \
    proxychains4 \
    && curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | gpg --yes --dearmor --output /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ $(lsb_release -cs) main" > /etc/apt/sources.list.d/cloudflare-client.list \
    && apt-get update && apt-get install -y --no-install-recommends cloudflare-warp \
    && rm -rf /var/lib/apt/lists/*

# ضبط proxychains4 على بورت WARP المحلي
RUN printf "strict_chain\nproxy_dns\n[ProxyList]\nsocks5 127.0.0.1 40000\n" > /etc/proxychains4.conf

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -U pip && pip install --no-cache-dir -U -r requirements.txt

COPY main.py .

CMD ["python", "-u", "main.py"]
