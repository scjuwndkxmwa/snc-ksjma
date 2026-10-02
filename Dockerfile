FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DENO_INSTALL=/usr/local
ENV PATH="/usr/local/bin:${PATH}"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
        curl \
        tini \
        unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Deno in /usr/local/bin and VERIFY it during Docker build.
RUN curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh \
    && /usr/local/bin/deno --version \
    && test -x /usr/local/bin/deno

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Final runtime verification.
RUN /usr/local/bin/deno --version \
    && yt-dlp --version

ENTRYPOINT ["/usr/bin/tini", "--"]

CMD ["python", "-u", "main.py"]
