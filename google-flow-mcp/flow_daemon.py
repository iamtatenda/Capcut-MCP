"""
Flow Daemon Manager
Maintains a persistent, lightweight background Chrome process running on port 9222.
Eliminates ephemeral Playwright browser launches, prevents RAM bloat,
and provides instant (<50ms) CDP attachment.
"""

import os
import sys
import time
import subprocess
import urllib.request
import json
from pathlib import Path

# Load local .env if present
ENV_PATH = Path(__file__).parent / ".env"
if ENV_PATH.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_PATH)
    except ImportError:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

CDP_PORT = int(os.environ.get("GFLOW_CDP_PORT", 9222))
CDP_URL = f"http://127.0.0.1:{CDP_PORT}/json/version"


def get_default_profile_dir() -> str:
    """Resolve default persistent Chrome profile directory across operating systems."""
    custom = os.environ.get("GFLOW_PROFILE_DIR")
    if custom:
        return custom
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
        return os.path.join(local_app_data, "google-flow", "profile_default")
    elif sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/google-flow/profile_default")
    else:
        return os.path.expanduser("~/.config/google-flow/profile_default")


def get_default_chrome_path() -> str:
    """Find Chrome executable path across operating systems."""
    custom = os.environ.get("GFLOW_CHROME_PATH")
    if custom and os.path.exists(custom):
        return custom

    candidates = []
    if sys.platform == "win32":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
    elif sys.platform == "darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ]
    else:
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
        ]

    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0] if candidates else "chrome"


DEFAULT_PROFILE = get_default_profile_dir()
CHROME_PATH = get_default_chrome_path()
DEFAULT_PROJECT_URL = os.environ.get("GFLOW_PROJECT_URL", "https://flow.google.com")


def is_cdp_ready() -> bool:
    """Check if Chrome is already running with remote debugging enabled."""
    try:
        req = urllib.request.Request(CDP_URL, headers={"User-Agent": "FlowDaemon/1.0"})
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return "webSocketDebuggerUrl" in data or "Browser" in data
    except Exception:
        return False
    return False


def get_open_tabs() -> list:
    """Retrieve list of currently open tabs from the CDP endpoint."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}/json/list", headers={"User-Agent": "FlowDaemon/1.0"})
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []
    return []


def ensure_flow_daemon(project_url: str = None, headless: bool = True) -> bool:
    """
    Ensure the Chrome CDP daemon is running and ready.
    If not running, launch it in the background as a detached process.
    """
    target_url = project_url or DEFAULT_PROJECT_URL
    if is_cdp_ready():
        return True

    chrome_bin = get_default_chrome_path()
    if not os.path.exists(chrome_bin):
        raise FileNotFoundError(
            f"Chrome executable not found at '{chrome_bin}'. "
            "Please install Google Chrome or set GFLOW_CHROME_PATH."
        )

    profile_dir = get_default_profile_dir()
    os.makedirs(profile_dir, exist_ok=True)

    cmd = [
        chrome_bin,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--disable-features=TranslateUI",
        "--restore-last-session",
    ]
    if headless:
        cmd.append("--headless=new")
    cmd.append(target_url)

    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    subprocess.Popen(
        cmd,
        creationflags=creation_flags,
        close_fds=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    # Poll until ready (up to 8 seconds)
    start_time = time.time()
    while time.time() - start_time < 8.0:
        if is_cdp_ready():
            return True
        time.sleep(0.3)

    return is_cdp_ready()


if __name__ == "__main__":
    ready = ensure_flow_daemon()
    print(f"Flow Daemon ready on port {CDP_PORT}: {ready}")
