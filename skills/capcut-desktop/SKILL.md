---
name: capcut-desktop
description: Programmatic timeline assembly, multi-track orchestration, and directing automation for CapCut Desktop (Windows & macOS). Use when creating, modifying, aligning, or repairing CapCut Desktop draft projects, timelines, video tracks, SFX layering, and typographic cards.
---

# CapCut Desktop Programmatic Timeline Automation

This skill provides the comprehensive architecture, JSON specifications, directing directives, and multi-track orchestration protocols for programmatically generating and modifying **CapCut Desktop** draft projects directly on local machines (Windows and macOS).

---

## 1. Directory Structure and Path Discovery

CapCut Desktop stores all local projects in a root draft directory:
- **Windows**: `C:/Users/<USER>/AppData/Local/CapCut/User Data/Projects/com.lveditor.draft/draft_<TIMESTAMP>/`
- **macOS**: `/Users/<USER>/Movies/CapCut/User Data/Projects/com.lveditor.draft/draft_<TIMESTAMP>/`

> [!CRITICAL]
> **Mandatory Canonical Folder Naming (`draft_<timestamp>`)**:
> CapCut Desktop strictly validates folder names directly inside `com.lveditor.draft/`.
> The folder name MUST match `draft_<timestamp>` (e.g. `draft_1788710296`) or 4-digit date (`\d{4}`).
> Custom folder names trigger CapCut's rejection popup:
> *"Couldn't use project: Current project is from an unusual path and cannot be used currently."*
> 
> The human-readable project title belongs exclusively in `draft_content.json` -> `"name"`.
> In `draft_meta_info.json` and `root_meta_info.json`, `"draft_name"` must strictly match the folder name (`draft_<timestamp>`).

Inside each draft folder:
```
com.lveditor.draft/draft_<TIMESTAMP>/
├── Resources/                     # Material cache subfolder (required)
├── Timelines/                     # Sub-timeline folder (required)
│   └── <TIMELINE_UUID>/
│       ├── draft_content.json     # Internal timeline payload (MUST BE SYNCHRONIZED)
│       └── draft_content.json.bak
├── adjust_mask/                   # Mask cache (required)
├── ai_material/                   # AI material cache (required)
├── common_attachment/             # Attachment cache (required)
├── matting/                       # Matting/chroma cache (required)
├── qr_upload/                     # QR upload cache (required)
├── smart_crop/                    # Smart crop cache (required)
├── subdraft/                      # Subdraft cache (required)
├── draft_content.json             # Primary project timeline payload
├── draft_content.json.bak         # Backup copy (must match draft_content.json)
├── draft_meta_info.json           # Material catalog and draft metadata
├── draft_cover.jpg                # Project thumbnail
├── draft_settings                 # Edit metadata
├── timeline_layout.json           # UI layout config
└── template-2.tmp                 # Engine template copy
```

Root Registry:
- `com.lveditor.draft/root_meta_info.json` contains `all_draft_store` listing all projects.
  - `"draft_name"` MUST be `draft_<timestamp>`.
  - `"draft_cover"` and `"draft_json_file"` must use mixed backslashes: `<DIR>\\draft_cover.jpg`.

---

## 2. The Dual-Synchronization Protocol (Mandatory)

CapCut Desktop maintains two copies of the project timeline. Both must be updated simultaneously:
1. Root `draft_content.json`
2. Sub-timeline `Timelines/<TIMELINE_UUID>/draft_content.json`

If only the root file is modified, CapCut Desktop will load the stale sub-timeline, reverting your edits. Always write to both paths and update their corresponding `.bak` files.

---

## 3. The 10 Golden Directing Rules

Amateur AI video edits suffer from five fatal flaws: metronomic 2.5-second cuts, flat 2D static images, whoosh spam, karaoke subtitles over graphics, and abrupt hard cuts. Disciplined video editing follows clear rules:

1. **Audio-Driven Cutting (Cadence over Clock)**: Never cut visual clips on a fixed metronome (e.g. exactly every 2.5 seconds). Visual cuts must align to narrative breath, syntactic pauses, or punchline consonants in the voiceover track.
2. **The Split-Cut Imperative (J-Cuts and L-Cuts)**: Hard cuts where audio and video shift simultaneously feel robotic. Lead dialogue by 250ms to 400ms before cutting to the new scene (J-Cut), or let scene audio spill across the visual transition (L-Cut).
3. **Eye-Trace Vector Matching**: Guide the viewer's focus intentionally. If a subject exits screen-right in shot A, the focal anchor of shot B must sit on the right third of the frame. Never force the viewer's eyes to jump erratically across quadrants without motivation.
4. **2.5D Multi-Plane Parallax Layering**: Never show flat, isolated images with a generic Ken Burns push. Build visual depth by separating scenes into multiple planes:
   - **Track 0 (Background Plate)**: Slow, wide push (scale 1.0 to 1.025).
   - **Track 1 (Sandwiched Typography)**: Bold editorial headlines positioned physically behind the subject.
   - **Track 2 (Midground Cutout Subject)**: Isolated character or foreground object pushing faster (scale 1.0 to 1.07) with subtle drop shadow.
   - **Track 3 (Atmospheric Texture Overlay)**: 35mm film grain, dust motes, or anamorphic lens flares at 15% to 25% opacity.
5. **Split-Screen Comparative Layouts**: For before/after comparisons, historical contrasts, or technical teardowns, place two synchronized clips side-by-side (left: -0.25 offset, right: +0.25 offset) rather than cutting back and forth.
6. **Strict Audio Politeness (The SFX Budget)**: Ban whoosh spam. Never attach risers, whooshes, or swooshes to routine b-roll cuts. Cap project audio to:
   - Subtle tactile clicks (`ui_tap.wav`, ~0.07s) only on major structural chapter shifts.
   - Cinematic sub-bass sine drops (30Hz to 60Hz) budgeted to a maximum of 3 per project, reserved exclusively for breakthrough epiphany moments.
7. **Subtitles vs. Graphic Cards Rule**: Never layer lower-third subtitle text over full-screen typographic graphic cards. When graphic cards carry the copy, suppress subtitles completely. Reserve subtitles for raw B-roll footage.
8. **Color-Safe Chroma Keying & Non-Colliding Backdrops**: When isolating subjects against solid backgrounds for compositing, never default blindly to green screen:
   - If the subject wears khaki, olive, yellow, or desert tactical gear, green screen causes keyer spill and erases clothing edges. Use **Royal Blue (`#0047AB`)** or **Neutral Studio Grey (`#808080`)**.
   - If the subject wears navy or denim, use **Magenta (`#FF00FF`)**.
   - For high-contrast modern editorial cutouts, use **High-Key White (`#FFFFFF`)**.
9. **Lighting Angle and Color Temperature Continuity**: An isolated subject cut out and placed over an environment plate looks fake if light sources clash. Enforce matching key light angles (e.g. 45-degree camera-right) and color temperatures (e.g. 3200K tungsten vs 5600K daylight) across all generated assets for that scene.
10. **Zero Repetitive B-Roll Stalling**: Never loop or hold a static image when speech runs long. If voiceover exceeds clip duration, hold the final frame with smooth keyframing, apply an optical speed ramp, or cut to a complementary reverse angle.

---

## 4. Multi-Track Timeline Architecture

CapCut Desktop projects follow an 8-track visual and acoustic stack:

### Visual Tracks
- **Track 0 (Main Video / Background Plates / Graphic Cards)**: Base narrative sequence. Video clips set to `volume: 0.0`.
- **Track 1 (Sandwiched Typography)**: Editorial headlines rendered behind cutout midgrounds.
- **Track 2 (Midground Isolated Subjects / Split Right Clips)**: Foreground subjects with alpha channels and differential parallax scaling.
- **Track 3 (Atmospheric Overlays)**: Texture passes, dust, grain, and lighting overlays at lowered alpha.

### Audio Tracks
- **Audio Track 1 (Master Voiceover)**: Continuous narration audio (`voiceover.mp3` or `.wav`), `volume: 1.0`. Continuous, primary anchor.
- **Audio Track 2 (Ambient Room Tone Bed)**: Continuous low-level room tone, analog tape hiss, or environmental atmosphere (`volume: 0.08 - 0.12`). Glues disparate scene cuts together acoustically.
- **Audio Track 3 (Tactile Haptics & Sub-Bass)**: High-priority tactile UI clicks (`volume: 0.70`) and sub-bass epiphany drops (`volume: 0.85`). Strictly validated for non-collision.
- **Audio Track 4 (Ducked Music Bed)**: Cinematic music score ducked to `-18dB` (`volume: 0.15 - 0.22`) beneath voiceover.

---

## 5. Pre-Production Scene Blueprint

Before calling generation tools or writing timeline JSON, construct a structured Scene Blueprint. This eliminates trial-and-error edits:

```markdown
### Scene Blueprint: [Scene ID & Name]
- **Target Duration**: [e.g. 5.2s, mapped to voiceover breath]
- **Narrative Subtext**: [What emotional tension or concept does this convey?]
- **Shot Composition**: [Scale: Wide / Medium / Close-Up | Motility: Static / Push / Lateral Drift]
- **Lighting Direction & Temp**: [e.g. 45-degree top-right direct sun, 3200K warm desert light]
- **Eye-Trace Entry & Exit**: [Entry focal point: Center-left | Exit focal point: Center-right]
- **Layering Structure**:
  - Track 0 (BG Plate): Wide desert dunes, horizon on upper third
  - Track 1 (Typography): "THE CROSSING" in Inter-Bold, tracked out
  - Track 2 (Subject Cutout): Hooded traveler, generated against Royal Blue `#0047AB`
  - Track 3 (Overlay): Fine dust motes at 20% alpha
- **Audio Layers**:
  - Voiceover: "No map marked what lay beyond the ridge."
  - Room Tone: Continuous low desert wind hiss (-20dB)
  - Haptics: Tactile click at 0.0s transition
```
