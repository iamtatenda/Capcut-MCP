<div align="center">
  <img src="./assets/logo.svg" alt="CapCut MCP Logo" width="90" height="90" />
  <h1>CapCut MCP</h1>
  <p><strong>Direct video edits inside CapCut using plain conversational language.</strong></p>
  <p>Turn raw footage into polished, broadcast-ready videos through your AI coding agent.</p>
</div>

---

## What is this?

Most AI video tools fall into two frustrating categories: gimmicky generators that produce surreal morphing clips, or complex video editors with hundreds of confusing timeline menus.

This repository packages the **CapCut Model Context Protocol (MCP)** together with the production directing skills that teach AI models how human editors actually cut footage.

Connect this MCP to your favorite AI coding assistant (Google Antigravity, Claude Code, Claude Desktop, Cursor, Windsurf, or Cline). Point it at a folder of raw footage, describe the pacing and structure you want, and let the agent assemble the timeline, sync edits to vocal pauses, sandwich bold typography behind cutout subjects, and balance the sound mix.

---

## What You Can Do

- **Edit With Words**: Ask for a punchy 30-second teaser. The agent drafts a structured Scene Blueprint, uploads local footage, submits the cut to CapCut AI Lab, and returns the interactive review card.
- **Directing Intelligence**: The included skills enforce professional cutting discipline. No robotic 2.5-second cuts on a rigid metronome, no whoosh spam on routine cuts, and no ugly karaoke subtitles clashing over title cards.
- **Zero-Dependency Media Uploader**: Includes a standalone Node.js client (`skills/capcut-upload/scripts/capcut-upload.mjs`) that streams local `.mp4`, `.mov`, and images directly to ByteDance VOD and ImageX servers with chunking and CRC32 checks.
- **Multimodal Template Discovery**: Feed an existing video or reference image to find matching CapCut templates, complete with signed cover previews and direct links.
- **Desktop Draft Automation**: Reverse-engineers CapCut Desktop's local draft project structure (`draft_content.json`) on Windows and macOS for programmatic timeline assembly.

---

## 3-Minute Quickstart

### Step 1: Clone the Repository

```bash
git clone https://github.com/your-username/capcut-mcp.git
cd capcut-mcp
```

### Step 2: Grab Your CapCut Bearer Token (30 Seconds)

1. Open [capcut.com](https://www.capcut.com) in Chrome or Edge and sign in.
2. Press `F12` (or right-click anywhere and select **Inspect**) to open Developer Tools.
3. Switch to the **Network** tab and filter by `api`.
4. Click into any project or folder on CapCut to trigger an API call.
5. Click on any network request going to `capcut.com/api/...`. In the **Request Headers** section on the right, find `Authorization`.
6. Copy everything after `Bearer ` (it will look like a long string of random characters).

> [!IMPORTANT]
> **US IP Address Notice**: ByteDance restricts CapCut API access from US IP addresses. If you run your agent from the United States, route your connection through a VPN or proxy located in Canada, the UK, Europe, or Asia before calling the API.

---

### Step 3: Connect to Your Agent

#### Option A: Google Antigravity / Gemini CLI

Add the servers to `~/.gemini/config/mcp_config.json`:

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
    }
  }
}
```

Or run the CLI command:

```bash
agy mcp add --header "Authorization: Bearer YOUR_CAPCUT_BEARER_TOKEN" capcut_creation https://www.capcut.com/api/external_mcp
agy mcp add capcut_creation_resource https://www.capcut.com/api/external_mcp/resource
```

#### Option B: Claude Desktop

Add this to your Claude Desktop configuration (`claude_desktop_config.json`):

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
    }
  }
}
```

#### Option C: Cursor & Windsurf

Add this to `.cursor/mcp.json` or `.codeium/windsurf/mcp_config.json`:

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
    }
  }
}
```

---

## Step 4: Talk to Your Agent

Once configured, your agent can edit videos naturally. Here are real prompts that work:

### Example 1: Directing an Edit from Scratch
> *"Take the footage in `./footage/gym_session/`. I need a 30-second high-velocity commercial. Cut on the vocal rhythm of the narrator, add title cards with bold typography behind the athlete, and keep sound design subtle with crisp clicks at chapter shifts."*

### Example 2: Finding Matching Styles
> *"Look at `./references/product_shot.jpg`. Search CapCut templates for high-energy tech hardware launches with 9:16 vertical ratio and electronic synth music."*

### Example 3: Rebuilding a Local Desktop Timeline
> *"Open my local CapCut project `draft_1788545083`. Re-time track 1 to lead dialogue by 300ms using a J-cut, remove the repetitive b-roll on scene 3, and add a subtle 1.0 to 1.05 slow scale push to the background plate."*

---

## Directing Standards Built Into This Repo

Amateur video edits look cheap because they follow bad habits: cutting on a fixed 2.5-second clock, spamming whoosh sound effects, placing subtitles over full-frame graphics, and treating images as flat slides.

The skills bundled in `skills/` enforce professional editing rules:

1. **Audio Cadence Over Clock**: Edits cut on breath breaks, vocal pauses, or emphatic consonants, never on an arbitrary timer.
2. **The Split-Cut Imperative**: Uses J-cuts (dialogue leads visual change by 250ms to 400ms) and L-cuts (environment audio trails past the cut) to keep transitions natural.
3. **2.5D Parallax Layering**: Splits scenes into 4 planes: background plate (slow push), sandwiched typography, isolated foreground subject (faster push with drop shadow), and subtle atmospheric grain.
4. **Strict SFX Budgeting**: Total ban on whoosh spam. Transitions use subtle tactile clicks (`ui_tap.wav`, 0.07s) and a hard limit of 3 sub-bass sine drops per video for epiphany moments.
5. **Non-Colliding Chroma Keying**: Avoids green screen when subjects wear khaki, earth tones, or olive gear (which creates green spill on clothing). Instructs generation on Royal Blue (`#0047AB`), Neutral Grey (`#808080`), or Magenta (`#FF00FF`).

---

## Repository Structure

```text
Capcut MCP/
├── assets/
│   └── logo.svg                    # Vector CapCut branding asset
├── clients/                        # Ready-to-paste configurations
│   ├── antigravity_config.json     # Antigravity & Gemini CLI snippet
│   ├── claude_desktop_config.json  # Claude Desktop snippet
│   └── cursor_mcp.json             # Cursor & Windsurf snippet
├── schemas/                        # CapCut MCP tool definitions
│   ├── editing_plan.json           # Interactive plan card schema
│   ├── video_preview.json          # Final render card schema
│   ├── templates_preview.json      # Template search schema
│   ├── templates_preview_v2.json   # Preferred template search renderer
│   ├── background_music.json       # Music selection schema
│   ├── capcut_report_event.json    # Event telemetry schema
│   └── instructions.md             # MCP server runtime instructions
├── skills/                         # Agent instructions & scripts
│   ├── ai-video-editing/           # The flagship "Edit with Words" workflow
│   ├── capcut-desktop/             # Local desktop draft automation & dual-sync
│   ├── capcut-mcp-auth/            # Auth setup & token inspection guide
│   ├── capcut-upload/              # Local file upload engine & 1,691-line script
│   └── search-templates/           # Template discovery & multimodal query pipeline
├── mcp_config.example.json         # Example MCP configuration file
├── mcp_config.json                 # Pre-configured endpoints for plugin loading
├── package.json                    # Node scripts and testing commands
├── plugin.json                     # Antigravity / Gemini plugin manifest
├── LICENSE                         # MIT License
└── README.md                       # Documentation
```

---

## Media Upload Script

If you want to upload media files manually from your terminal without the AI agent:

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

The uploader requires zero external npm packages and runs on any standard Node.js 18+ runtime.

---

## Contributing & License

Contributions, bug reports, and pull requests are welcome. This project is released under the [MIT License](LICENSE).
