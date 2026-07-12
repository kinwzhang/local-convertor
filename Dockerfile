FROM python:3.12-slim

WORKDIR /app

RUN groupadd -r appuser && useradd -r -g appuser appuser

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY . .

RUN mkdir -p /data/database /data/subscriptions \
    && chown -R appuser:appuser /app /data

USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')"

CMD ["/bin/sh", "-c", "flask db upgrade && exec gunicorn -w 1 -b 0.0.0.0:5000 main:app"]
