#!/usr/bin/env bash

if [ -n "${UV_CACHE_DIR:-}" ]; then
  mkdir -p "${UV_CACHE_DIR}"
  export UV_CACHE_DIR
  return 0 2>/dev/null || exit 0
fi

if [ -n "${XDG_CACHE_HOME:-}" ]; then
  UV_CACHE_DIR="${XDG_CACHE_HOME}/uv"
elif [ -n "${HOME:-}" ]; then
  UV_CACHE_DIR="${HOME}/.cache/uv"
else
  UV_CACHE_DIR="/tmp/uv-cache-$(id -u)"
fi

mkdir -p "${UV_CACHE_DIR}"
export UV_CACHE_DIR
