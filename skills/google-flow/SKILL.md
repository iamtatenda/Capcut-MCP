---
name: google-flow
description: Autonomous, high-fidelity image and video generation using Google Flow and Google Pro unmetered accounts. Use whenever generating 16:9 cinematic visuals, documentary b-roll, motion video clips, thumbnails, app presentation graphics, or character-consistent visuals tagged with @Character.
---

# Google Flow Autonomous Asset Generator

This skill enables autonomous, high-resolution 16:9 image and video generation via Google Flow using authenticated Google Pro accounts (unmetered generation quota, bypassing standard third-party API rate limits and token costs).

---

## 1. High-Speed Architecture

1. **Persistent CDP Engine**: Connects to a warm background Chrome daemon on port 9222. Eliminates ephemeral browser launches and memory thrashing.
2. **Instant In-Page Injection (<10ms)**: Bypasses character-by-character simulated keystrokes by directly executing in-page DOM text insertion commands.
3. **Zero-Disk Screenshot Latency**: Operates purely through CDP state inspection and network payload interception. Does not write temporary debug screenshots to disk.
4. **Flow Workspace Agent Integration**: Interacts directly with Google Flow's internal workspace agent (`gflow_prompt_agent`), dispatching multi-shot storyboards across multiple canvas tiles concurrently.
5. **Direct Network Harvester**: Intercepts `aisandbox-pa.googleapis.com` render payloads and downloads completed image and video assets directly via session-authenticated streaming (`gflow_harvest_assets`).
6. **Character Continuity via `@Character` Tags**: Maintains facial, structural, and wardrobe continuity across scenes by referencing character embeddings (e.g. `@TheNarrator`, `@Marcus`).

---

## 2. Directing & Asset Rules (Mandatory)

### A. Video Priority Over Static Images
- When generating action sequences (walking, working, lifting, athletic movement, emotional shifts), **generate dynamic `.mp4` video clips**, not static `.jpeg` frames.
- In timeline assembly, never substitute a generated action video with a static frame.

### B. Cinematographic Shot Grammar
Specify camera scale and motility explicitly on every prompt:
- **`shot_scale`**:
  - `macro_detail`: Extreme close-up on physical textures, eyes, parchment, watch hands, micro-contractions.
  - `intimate_close_up`: Tight portrait framing from collarbones up, capturing nuanced facial expression.
  - `medium_action`: Waist-up framing showing physical movement, hands, and immediate surroundings.
  - `wide_epic`: Full environmental context with the subject grounded in landscape geometry.
  - `low_angle_hero`: Upward perspective adding visual authority and gravitas to the subject.
- **`motility`**:
  - `slow_push_in`: Slow forward camera movement building emotional tension.
  - `tracking_lateral`: Smooth Steadicam pan tracking parallel to subject motion.
  - `locked_off`: Rock-solid tripod framing for deliberate, monumental stillness.
  - `orbital_arc`: Smooth rotational arc around subject.
  - `subtle_handheld`: Natural organic breathing motion with zero erratic shaking.

### C. Color-Safe Chroma Keying (No Green-Screen Accidents)
When generating subjects intended for 2.5D multi-plane cutout compositing in CapCut, set `chroma_backdrop` intentionally:
- **`chroma_royal_blue` (`#0047AB`)**: **Mandatory for warm subjects**, khaki uniforms, leather, desert gear, yellow clothing, or blonde hair. Green screen causes spill that destroys khaki fabric and yellow accents.
- **`chroma_magenta` (`#FF00FF`)**: Mandatory when the subject wears blue denim, navy suits, or cool-toned gear.
- **`chroma_emerald` (`#00C853`)**: Standard green backdrop, used only when the subject wears neutral dark charcoal, red, or purple.
- **`chroma_high_key_white` (`#FFFFFF`)**: Clean solid white cyclorama for modern editorial cutouts.

### D. Lighting Direction and Color Temperature Matching
Always pass `lighting_match` to align isolated subjects with their target background plates:
- Desert / Sunset: `45-degree top-right direct sunlight, 3200K warm golden-hour glow`
- High-Tech / Lab: `overhead cool diffused fluorescent lighting, 5600K clean daylight`
- Dramatic Interior: `high-contrast Rembrandt key light camera-left, deep shadow falloff camera-right`

---

## 3. MCP Tool Reference (`ServerName: google-flow`)

### 1. Generate Video (`gflow_generate_video`)
Supports Image-to-Video generation conditioned on a reference still or character:
```python
call_mcp_tool(
    ServerName="google-flow",
    ToolName="gflow_generate_video",
    Arguments={
        "prompt": "Solitary traveler walking across windblown desert dunes",
        "output_path": "C:/assets/scenes/scene_01_desert_walk.mp4",
        "reference_asset": "Traveler",
        "style": "documentary",
        "shot_scale": "wide_epic",
        "motility": "tracking_lateral",
        "lighting_match": "warm 3200K afternoon sunlight from upper-right",
        "duration_seconds": 10
    }
)
```

### 2. Generate Image Plate or Cutout Subject (`gflow_generate_image`)
Supports character persistence and wardrobe consistency via `@` ingredient injection:
```python
# Generate an isolated subject against Royal Blue for clean chroma keying:
call_mcp_tool(
    ServerName="google-flow",
    ToolName="gflow_generate_image",
    Arguments={
        "prompt": "Middle-aged cartographer in leather coat examining an ancient brass sextant",
        "output_path": "C:/assets/scenes/scene_02_cartographer_isolated.png",
        "reference_asset": "Cartographer",
        "style": "character_portrait",
        "shot_scale": "intimate_close_up",
        "chroma_backdrop": "chroma_royal_blue",
        "lighting_match": "45-degree key light camera-right, 3200K tungsten"
    }
)
```

### 3. List Available Canvas Ingredients (`gflow_list_canvas_ingredients`)
Inspects all active canvas assets, character cards, and ingredients available for `@` injection:
```python
call_mcp_tool(
    ServerName="google-flow",
    ToolName="gflow_list_canvas_ingredients",
    Arguments={}
)
```

### 4. Generate 3-Angle Character Reference Sheet (`gflow_generate_character_sheet`)
Generates front, 45-degree, and profile reference plates with color-safe studio backdrops:
```python
call_mcp_tool(
    ServerName="google-flow",
    ToolName="gflow_generate_character_sheet",
    Arguments={
        "character_description": "Cyberpunk ramen vendor with bionic left arm and bandana",
        "output_path": "C:/assets/characters/vendor_sheet.jpeg",
        "wardrobe": "distressed leather apron over neon orange techwear",
        "chroma_backdrop": "chroma_royal_blue"
    }
)
```

### 5. Prompt Google Flow Workspace Agent (`gflow_prompt_agent`)
Directs Flow's internal agent to generate multiple canvas cards simultaneously:
```python
call_mcp_tool(
    ServerName="google-flow",
    ToolName="gflow_prompt_agent",
    Arguments={
        "prompt": "Create 4 cinematic 16:9 video clips: 1) Aerial view of ancient desert ruins at dawn; 2) Close up of compass needle spinning frantically; 3) Heavy stone temple doors slowly creaking open; 4) Macro view of dust particles suspended in a golden beam of light."
    }
)
```

### 6. Harvest Completed Canvas Assets (`gflow_harvest_assets`)
Streams all rendered videos and images directly from the Flow canvas into your local folder:
```python
call_mcp_tool(
    ServerName="google-flow",
    ToolName="gflow_harvest_assets",
    Arguments={
        "output_dir": "C:/assets/scenes/harvested"
    }
)
```

### 7. Generate Storyboard Batch (`gflow_generate_batch`)
Runs an entire multi-shot manifest with optional `chain_continuity=True` to feed previous scene cards into subsequent scene prompts:
```python
call_mcp_tool(
    ServerName="google-flow",
    ToolName="gflow_generate_batch",
    Arguments={
        "manifest_json_or_file": [
            {
                "id": "scene_01_bg",
                "type": "image",
                "prompt": "Vast sand dunes stretching to the horizon",
                "style": "documentary",
                "shot_scale": "wide_epic"
            },
            {
                "id": "scene_02_traveler",
                "type": "image",
                "prompt": "Desert traveler standing resolute in linen tunic",
                "style": "character_portrait",
                "chroma_backdrop": "chroma_royal_blue",
                "shot_scale": "intimate_close_up"
            },
            {
                "id": "scene_03_action",
                "type": "video",
                "prompt": "Traveler climbing steep limestone cliff in sandstorm",
                "duration_seconds": 10,
                "style": "cinematic_action",
                "shot_scale": "medium_action"
            }
        ],
        "output_dir": "C:/assets/scenes",
        "default_style": "documentary",
        "chain_continuity": True
    }
)
```

---

## 4. Visual Style Presets

- `documentary`: 35mm lens, atmospheric haze, volumetric dust, deep natural shadows, authentic film texture, 8k.
- `vsl_macro`: Commercial macro, razor-sharp focal plane, dark luxury backdrop, edge glow, pristine finish.
- `hypercar_commercial`: Automotive commercial grade, rain-slicked asphalt, sunset rim lighting, puddle reflections.
- `character_portrait`: Medium close-up, Rembrandt lighting, eye catchlight, skin micro-texture, 85mm lens.
- `cinematic_action`: Dynamic motion blur, dramatic rim light, wide-angle perspective, hyper-detailed.
- `raw`: Uses the exact prompt string without any enrichment.

---

## 5. One-Time Setup & Authentication

Run the setup wizard script from `google-flow-mcp/`:
- **Windows**: Double-click `google-flow-mcp\setup_auth.bat`
- **macOS/Linux**: Run `./google-flow-mcp/setup_auth.sh`

This opens Chrome in visible mode to let you log in to Google Flow once. Your session cookies and tokens are preserved in your local profile directory for zero-prompt, ongoing access.
