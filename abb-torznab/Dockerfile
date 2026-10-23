FROM python:3.12-alpine

WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY app.py .

EXPOSE 8088

HEALTHCHECK --interval=60s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8088/healthz',timeout=4)"

CMD ["python", "-u", "app.py"]
