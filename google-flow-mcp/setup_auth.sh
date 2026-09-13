#!/usr/bin/env bash
# Google Flow MCP One-Time Authentication Launcher
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
python3 setup_auth.py
