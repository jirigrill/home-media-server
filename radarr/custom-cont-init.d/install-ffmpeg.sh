#!/usr/bin/with-contenv bash

echo "**** Installing ffmpeg for sample detection ****"

# Check if ffmpeg is already installed
if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
    echo "**** ffmpeg already installed, skipping ****"
    exit 0
fi

# Install ffmpeg using apk
apk add --no-cache ffmpeg

echo "**** ffmpeg installation complete ****"
