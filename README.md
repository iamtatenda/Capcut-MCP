<div align="center">
  <img src="./assets/logo.svg" alt="CapCut MCP Logo" width="90" height="90" />
  <h1>CapCut & Google Flow MCP</h1>
  <p><strong>Generate cinematic video assets and direct CapCut edits using plain conversational prompts.</strong></p>
  <p>An end-to-end autonomous video studio inside your AI coding agent.</p>
</div>

---

## What is this?

Most AI video workflows force you to juggle fragmented tools: generating raw clips on web dashboards, manually downloading files, and fighting complex timeline menus in an editor.

This repository combines two core systems into a single protocol:
1. **Google Flow MCP**: Autonomous 16:9 cinematic video and image generation with camera motility, character continuity, and clean studio backdrops.
2. **CapCut MCP & Directing Suite**: Autonomous timeline assembly, split-cut pacing, 2.5D depth layering, audio leveling, and local draft file automation.

Connect this package to your AI assistant (Google Antigravity, Claude Code, Claude Desktop, Cursor, Windsurf, or Cline). Describe your narrative, let the agent generate matching footage with Google Flow, push the files into CapCut, and receive a completed draft timeline ready for export.

---

## Key Capabilities

- **Autonomous Generation (Google Flow)**: Prompt 16:9 cinematic b-roll, character plates on Royal Blue backdrops for clean chroma keys, and multi-shot continuous sequences via persistent Chrome DevTools Protocol.
- **Edit With Words (CapCut AI Lab)**: Ask for a punchy 30-second commercial. The agent drafts a Scene Blueprint, ingests media, triggers the edit, and returns interactive review cards.
- **Human Directing Standards**: Built-in skills enforce professional editing rules. No robotic 2.5-second cuts on a rigid clock, no whoosh spam on routine cuts, and no ugly karaoke subtitles clashing over title cards.
- **One-Click Google Flow Auth**: A self-contained auth wizard (`setup_auth.bat` / `setup_auth.sh`) creates an isolated Chrome profile, lets you sign in once, and keeps your session ready for headless automation.
- **Zero-Dependency Media Uploader**: Includes a standalone script (`skills/capcut-upload/scripts/capcut-upload.mjs`) that streams local `.mp4`, `.mov`, and images directly to ByteDance VOD and ImageX servers with chunking and CRC32 checks.
- **CapCut Desktop Draft Automation**: Reverse-engineers local desktop projects (`draft_content.json`) on Windows and macOS for programmatic timeline manipulation.

---

## Quickstart

### 1. Clone the Repository

```bash
git clone https://github.com/iamtatenda/Capcut-MCP.git
cd Capcut-MCP
```

### 2. Set Up Google Flow (Asset Generation)

Google Flow handles video and image creation through a local background daemon. 

1. Install Python dependencies:
   ```bash
   pip install -r google-flow-mcp/requirements.txt
   ```

2. Run the one-time authentication wizard:
   - **Windows**: Double-click `google-flow-mcp\setup_auth.bat` (or run `python google-flow-mcp/setup_auth.py`).
   - **macOS / Linux**: Run `bash google-flow-mcp/setup_auth.sh` (or `python3 google-flow-mcp/setup_auth.py`).

3. The wizard launches a dedicated Chrome instance at [labs.google/fx/tools/flow](https://labs.google/fx/tools/flow). Sign into your Google account (standard or Pro).
4. Once you see the Google Flow project workspace, return to your terminal and press **Enter**.
5. Your authentication session is saved to `.flow_profile/` in the repo root. You do not need to sign in again.

> [!TIP]
> You can launch the background daemon manually anytime using `google-flow-mcp\launch_daemon.bat` (or `launch_daemon.sh`). If the daemon is not running when an agent calls a generation tool, the MCP server starts it automatically.

---

### 3. Grab Your CapCut Token (Editing Suite)

1. Open [capcut.com](https://www.capcut.com) in your browser and sign in.
2. Press `F12` (or right-click anywhere and select **Inspect**) to open Developer Tools.
3. Switch to the **Network** tab and filter by `api`.
4. Click into any project or folder on CapCut to trigger network activity.
5. Click on any request going to `capcut.com/api/...`. Under **Request Headers**, find `Authorization`.
6. Copy everything after `Bearer ` (a string of letters and numbers).

> [!IMPORTANT]
> **US IP Notice**: ByteDance restricts CapCut API access from US IP addresses. If you run your agent from the United States, route your connection through a VPN or proxy in Canada, the UK, Europe, or Asia before calling the API.

---

## Client Setup

Copy the configuration block for your tool:

### Option A: Google Antigravity / Gemini CLI

Add to `~/.gemini/config/mcp_config.json`:

```json
{
  "mcpServers": {
    "capcut_creation": {
      "serverUrl": "https://www.capcut.com/api/external_mcp",
      "headers": {
        "Authorization": "Bearer YOUR_CAPCUT_BEARER_TOKEN"
      }
    },
    "capcut_creation_resource": {
      "serverUrl": "https://www.capcut.com/api/external_mcp/resource"
    },
    "google-flow": {
      "command": "python",
      "args": ["google-flow-mcp/server.py"]
    }
  }
}
```

### Option B: Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "capcut_creation": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://www.capcut.com/api/external_mcp",
        "--header",
        "Authorization: Bearer YOUR_CAPCUT_BEARER_TOKEN"
      ]
    },
    "capcut_creation_resource": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://www.capcut.com/api/external_mcp/resource"
      ]
    },
    "google-flow": {
      "command": "python",
      "args": [
        "/path/to/Capcut-MCP/google-flow-mcp/server.py"
      ]
    }
  }
}
```

### Option C: Cursor & Windsurf

Add to `.cursor/mcp.json` or `.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "capcut_creation": {
      "url": "https://www.capcut.com/api/external_mcp",
      "headers": {
        "Authorization": "Bearer YOUR_CAPCUT_BEARER_TOKEN"
      }
    },
    "capcut_creation_resource": {
      "url": "https://www.capcut.com/api/external_mcp/resource"
    },
    "google-flow": {
      "command": "python",
      "args": ["google-flow-mcp/server.py"]
    }
  }
}
```

---

## Example Prompts & Studio Workflows

### 1. The Full Studio Pipeline (Flow Generation to CapCut Cut)
> *"Generate 3 clips with Google Flow showing an athlete running along an ocean cliffside at sunrise, shot on 35mm with slow forward tracking motility. Take those generated clips, upload them to CapCut, and cut a 20-second cinematic intro. Put bold serif titles sandwiched behind the runner, and add a single subtle sub-bass sine drop on the final title card."*

### 2. Character Cutout with Non-Colliding Chroma Key
> *"Generate an isolated subject in Google Flow: a founder in casual denim explaining a product, shot against a solid Royal Blue backdrop (`#0047AB`). Then import that clip into CapCut, remove the blue screen, and place them over a blurred office background plate with a 2.5D parallax push."*

### 3. Directing Existing Footage
> *"Take the footage in `./raw_clips/product_demo/`. Build a 30-second teaser. Cut on dialogue breath breaks, lead track 1 with a 300ms J-cut, suppress karaoke subtitles over graphic cards, and use tactile clicks at section boundaries."*

### 4. Template Matching
> *"Inspect `./references/moodboard.png`. Find CapCut templates that match this energetic pace with 9:16 vertical ratio and electronic synth audio."*

---

## Directing Standards

Amateur video edits look cheap because they follow bad habits: cutting on a fixed 2.5-second clock, spamming whoosh sound effects, placing subtitles over full-frame graphics, and treating images as flat slides.

The skills in `skills/` enforce production habits:

1. **Audio Cadence Over Clock**: Edits cut on breath breaks, vocal pauses, or emphatic consonants, never on an arbitrary timer.
2. **Split-Cut Logic**: Employs J-cuts (dialogue leads visual cuts by 250ms to 400ms) and L-cuts (ambient audio trails past the cut) to eliminate harsh transitions.
3. **2.5D Parallax Layering**: Splits scenes into 4 planes: background plate (slow push), sandwiched typography, isolated foreground subject (faster push with drop shadow), and subtle atmospheric grain.
4. **Strict SFX Budget**: Total ban on whoosh spam. Transitions use subtle tactile clicks (`ui_tap.wav`, 0.07s) and a hard cap of 3 sub-bass sine drops per video for pivotal moments.
5. **Smart Chroma Selection**: Never default to green screen when subjects wear earth, khaki, or olive tones (which creates green edge bleed). Instructs generation on Royal Blue (`#0047AB`), Neutral Grey (`#808080`), or Magenta (`#FF00FF`).

---

## Repository Structure

```text
Capcut MCP/
├── assets/                         # Vector branding assets
├── clients/                        # Client configs (Antigravity, Claude, Cursor)
│   ├── antigravity_config.json
│   ├── claude_desktop_config.json
│   └── cursor_mcp.json
├── google-flow-mcp/                # Google Flow generation engine
│   ├── batch_engine.py             # Concurrent & chained batch manager
│   ├── flow_cdp_client.py          # Chrome DevTools Protocol client
│   ├── flow_daemon.py              # Background headless browser runner
│   ├── launch_daemon.bat           # Windows background daemon launcher
│   ├── launch_daemon.sh            # macOS/Linux daemon launcher
│   ├── presets.py                  # Directing styles, shot scales & backdrops
│   ├── requirements.txt            # Python dependencies
│   ├── server.py                   # FastMCP server exposing generation tools
│   ├── setup_auth.bat              # One-click Windows authentication wizard
│   ├── setup_auth.py               # Cross-platform interactive auth script
│   └── setup_auth.sh               # One-click macOS/Linux auth wizard
├── schemas/                        # CapCut MCP tool schemas & docs
├── skills/                         # Directing skills & upload engines
│   ├── ai-video-editing/           # The flagship "Edit with Words" workflow
│   ├── capcut-desktop/             # Desktop draft automation & sync
│   ├── capcut-mcp-auth/            # Auth setup & token inspection guide
│   ├── capcut-upload/              # Direct-to-ByteDance VOD upload script
│   ├── google-flow/                # Visual generation prompt rules & styles
│   └── search-templates/           # Template discovery & multimodal query
├── mcp_config.example.json         # Example MCP configuration
├── mcp_config.json                 # Pre-configured endpoints
├── package.json                    # Project manifest
├── plugin.json                     # Antigravity plugin manifest
├── LICENSE                         # MIT License
└── README.md                       # Documentation
```

---

## Standalone Media Uploader

To upload media files directly from your terminal without opening an AI chat:

```bash
# Upload a single video (outputs clean JSON with public Vid)
node skills/capcut-upload/scripts/capcut-upload.mjs \
  --file ./clip.mp4 \
  --client-id video-1 \
  --upload-session '<SESSION_JSON>' \
  --json

# Upload a single image
node skills/capcut-upload/scripts/capcut-upload.mjs \
  --file ./cover.png \
  --client-id image-1 \
  --upload-session '<SESSION_JSON>' \
  --json
```

---

## License

This project is licensed under the [MIT License](LICENSE).
