#!/usr/bin/env bash
# Google Flow Persistent Chrome CDP Daemon Launcher
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
python3 flow_daemon.py
