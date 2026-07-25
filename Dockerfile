FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ASSAY_DB=/data/assay.sqlite \
    ASSAY_HOST=0.0.0.0 \
    ASSAY_PORT=8080

WORKDIR /app
COPY pyproject.toml setup.py README.md LICENSE ./
COPY src ./src
RUN python -m pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 assay \
    && mkdir -p /data \
    && chown -R assay:assay /data
USER assay

VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import json,urllib.request; assert json.load(urllib.request.urlopen('http://127.0.0.1:8080/readyz', timeout=2))['status']=='ready'"]

CMD ["assay", "serve", "--seed-demo"]
