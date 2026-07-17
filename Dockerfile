FROM python:3.12-slim
# libolm-dev + gcc are needed to build python-olm (matrix-nio[e2e]).
COPY requirements.txt /tmp/requirements.txt
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libolm-dev \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && apt-get purge -y gcc && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -r bot && mkdir -p /data/store && chown -R bot:bot /data
WORKDIR /app
COPY bot.py .
USER bot
CMD ["python", "-u", "bot.py"]
