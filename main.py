FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
        tini \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir \
    --upgrade pip \
    && pip install --no-cache-dir \
    -r requirements.txt

COPY main.py .

ENTRYPOINT ["/usr/bin/tini", "--"]

CMD ["python", "-u", "main.py"]
