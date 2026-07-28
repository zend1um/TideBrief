FROM python:3.12-slim AS wheels

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt


FROM python:3.12-slim

LABEL org.opencontainers.image.title="TideBrief" \
      org.opencontainers.image.description="知潮：自托管交易信息筛选与财经日历"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 tidebrief \
    && useradd --uid 10001 --gid tidebrief --create-home --shell /usr/sbin/nologin tidebrief

WORKDIR /app
COPY --from=wheels /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels
COPY . .
RUN chmod +x /app/docker-entrypoint.sh \
    && mkdir -p /app/data /app/logs /vault \
    && chown -R tidebrief:tidebrief /app /vault

USER tidebrief
EXPOSE 8765
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "main.py", "ui", "--host", "0.0.0.0", "--port", "8765"]
