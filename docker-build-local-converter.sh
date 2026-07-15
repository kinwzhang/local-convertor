#!/bin/sh
set -e
docker build --no-cache -t zwj808/clash-local-converter:latest -f Dockerfile .
docker push zwj808/clash-local-converter:latest
