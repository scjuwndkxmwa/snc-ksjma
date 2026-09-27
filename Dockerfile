FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install current Deno runtime for yt-dlp JavaScript challenge solving
RUN curl -fsSL https://deno.land/install.sh | sh \
    && mv /root/.deno/bin/deno /usr/local/bin/deno \
    && chmod +x /usr/local/bin/deno

WORKDIR /app

COPY requirements.txt .

# Nightly is recommended by yt-dlp for current site breakages
RUN pip install --no-cache-dir --pre -r requirements.txt

COPY stream.py .

CMD ["python", "-u", "stream.py"]
