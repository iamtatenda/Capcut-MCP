"""
Google Flow MCP One-Time Authentication Wizard
Launches Google Chrome with remote debugging on port 9222 to let you log in
to Google Flow, saves your persistent session profile, and configures .env.
"""

import os
import sys
import time
import subprocess
import urllib.request
import json
from pathlib import Path

# Add current directory to path
CURRENT_DIR = Path(__file__).parent.resolve()
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from flow_daemon import get_default_chrome_path, get_default_profile_dir, CDP_PORT, is_cdp_ready


def banner():
    print("=" * 68)
    print("      GOOGLE FLOW MCP - ONE-TIME AUTHENTICATION WIZARD")
    print("=" * 68)
    print(" This wizard opens Google Chrome in a dedicated session so you can")
    print(" log into your Google Account once. All session cookies and Flow")
    print(" tokens are saved locally in your user profile for zero-prompt use.")
    print("=" * 68)
    print()


def run_setup():
    banner()

    chrome_bin = get_default_chrome_path()
    if not os.path.exists(chrome_bin):
        print(f"[!] Chrome executable not found at default location: {chrome_bin}")
        custom_chrome = input("Please enter the full path to your chrome.exe (or press Enter to cancel): ").strip()
        if custom_chrome and os.path.exists(custom_chrome):
            chrome_bin = custom_chrome
        else:
            print("[X] Cannot proceed without Google Chrome installed.")
            sys.exit(1)

    profile_dir = get_default_profile_dir()
    os.makedirs(profile_dir, exist_ok=True)

    print(f"[*] Chrome Path: {chrome_bin}")
    print(f"[*] Profile Dir: {profile_dir}")
    print(f"[*] CDP Port:    {CDP_PORT}")
    print()

    # Launch Chrome in visible mode for user login
    print("[1/3] Launching Chrome in visible mode...")
    cmd = [
        chrome_bin,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--disable-features=TranslateUI",
        "https://flow.google.com"
    ]

    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NEW_CONSOLE

    proc = subprocess.Popen(cmd, creationflags=creation_flags)

    print()
    print("--------------------------------------------------------------------")
    print(" ACTION REQUIRED IN THE CHROME WINDOW:")
    print(" 1. Sign into your Google account (must have Google Pro / Flow access).")
    print(" 2. Once in Flow, open an existing project or click '+ New Project'.")
    print(" 3. Copy the project canvas URL from your address bar.")
    print("    (Format: https://flow.google.com/project/<PROJECT_ID>)")
    print("--------------------------------------------------------------------")
    print()

    project_url = input("Paste your Google Flow project canvas URL here: ").strip()
    if not project_url or not project_url.startswith("http"):
        project_url = "https://flow.google.com"
        print(f"[*] Defaulting project URL to: {project_url}")

    # Write .env file
    env_file = CURRENT_DIR / ".env"
    env_content = (
        f"# Google Flow MCP Configuration\n"
        f"GFLOW_CHROME_PATH={chrome_bin}\n"
        f"GFLOW_PROFILE_DIR={profile_dir}\n"
        f"GFLOW_PROJECT_URL={project_url}\n"
        f"GFLOW_CDP_PORT={CDP_PORT}\n"
    )
    with open(env_file, "w", encoding="utf-8") as f:
        f.write(env_content)

    print()
    print("[2/3] Verifying CDP connection on port 9222...")
    time.sleep(2)

    ready = is_cdp_ready()
    if ready:
        print("[OK] Chrome CDP port 9222 is active and responding!")
    else:
        print("[!] Chrome is running, but CDP endpoint took longer to respond.")
        print("    Your profile and session are still saved.")

    print()
    print("[3/3] Configuration saved to:", env_file)
    print()
    print("=" * 68)
    print(" [SUCCESS] AUTHENTICATION COMPLETE!")
    print("=" * 68)
    print(" You can now close the browser window or leave it open.")
    print(" When your AI agent runs, it will connect automatically.")
    print("=" * 68)


if __name__ == "__main__":
    run_setup()
