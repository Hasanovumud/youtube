#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

# FFmpeg static build yükləyirik
mkdir -p bin
curl -L https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz | tar -xJ --strip-components=1 -C bin
