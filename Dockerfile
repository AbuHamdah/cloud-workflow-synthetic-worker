FROM python:3.12-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
RUN apt-get update && apt-get install -y --no-install-recommends montage=6.1+dfsg-1+b1 maq=0.7.1-10 time ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY worker.py /app/worker.py
EXPOSE 8900
CMD ["python", "/app/worker.py"]
