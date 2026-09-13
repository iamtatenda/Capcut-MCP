"""
Google Flow Style & Cinematographic Presets Engine
Pre-compiled visual styles that enrich base prompts with:
- Cinematic lens optics, lighting, contrast, and atmospheric tokens.
- Intentional shot scales (Macro ECU, Close-Up, Medium Action, Wide Epic, Low-Angle Hero).
- Camera motility tokens (Slow Creeping Push, Lateral Dolly, Orbital Arc, Locked-off).
- Color-safe chroma backdrops for multi-plane subject isolation (Royal Blue for warm/desert subjects, Magenta for cool subjects, High-Key White).
- Universal anti-CGI texture guardrails (Kodak Vision3, 35mm grain, zero plastic gloss).
"""

from typing import Dict, Optional

ANTI_CGI_TOKENS = (
    "authentic 35mm film grain, organic skin micro-texture, realistic cloth weave, "
    "natural optical lens flares, Kodak Vision3 5219 color science, photorealistic 8k, "
    "no artificial 3D CGI gloss, no smooth plastic rendering, no oversaturated digital sheen"
)

STYLE_PRESETS: Dict[str, str] = {
    "documentary": (
        "Cinematic historical documentary style, 35mm lens, atmospheric haze, "
        "volumetric dust particles, natural deep shadows, dramatic rim lighting, "
        f"authentic film texture, {ANTI_CGI_TOKENS}."
    ),
    "vsl_macro": (
        "High-contrast commercial macro shot, shallow depth of field, razor-sharp "
        f"focal plane, dark luxury backdrop, dramatic edge glow, pristine commercial grade, {ANTI_CGI_TOKENS}."
    ),
    "hypercar_commercial": (
        "High-octane luxury automotive commercial photography, rain-slicked asphalt, "
        f"sunset golden hour rim lighting, water puddle reflections, atmospheric haze, {ANTI_CGI_TOKENS}."
    ),
    "character_portrait": (
        "Cinematic medium close-up character portrait, Rembrandt lighting, subtle catchlight "
        f"in the eyes, natural skin micro-texture, 85mm portrait lens, shallow depth of field, {ANTI_CGI_TOKENS}."
    ),
    "cinematic_action": (
        "High-energy dynamic action sequence, subtle motion blur on movement, "
        f"dramatic cinematic rim light, wide angle perspective, hyper-detailed, {ANTI_CGI_TOKENS}."
    ),
    "raw": ""
}

# 1. Shot Scales
SHOT_SCALES: Dict[str, str] = {
    "macro_detail": (
        "Extreme close-up macro shot, razor-thin depth of field, tactile surface texture, "
        "100mm macro lens, dramatic edge lighting, hyper-detailed tactile focus"
    ),
    "intimate_close_up": (
        "Cinematic tight close-up portrait, 85mm portrait lens, shallow depth of field, "
        "authentic eye catchlights, subtle facial micro-expressions, emotional intensity"
    ),
    "medium_action": (
        "Medium cowboy shot, 50mm natural human focal length, dynamic physical posture, "
        "balanced environmental framing, clear character action"
    ),
    "wide_epic": (
        "Cinematic extreme wide establishing shot, 24mm anamorphic lens, grand environmental scale, "
        "deep horizon, volumetric atmospheric haze, deep spatial grandeur"
    ),
    "low_angle_hero": (
        "Dramatic low-angle hero perspective looking upward, commanding powerful presence, "
        "strong vertical lines, authoritative silhouette against sky or ceiling"
    ),
    "dutch_angle_tension": (
        "Off-kilter Dutch angle composition, 15-degree tilt, psychological disorientation, "
        "harsh shadows, high cognitive tension"
    )
}

# 2. Camera Motility
CAMERA_MOTILITY: Dict[str, str] = {
    "slow_push_in": "Slow creeping dolly forward, steady subtle push-in toward subject, rising tension and intimacy",
    "tracking_lateral": "Smooth lateral dolly tracking sideways, fluid motion blur, rich parallax background separation",
    "locked_off": "Locked-off tripod shot, completely stable camera, natural subject movement within frame",
    "orbital_arc": "Slow circular arc around subject, parallax depth separation, cinematic lighting shift",
    "subtle_handheld": "Subtle organic handheld camera drift, visceral documentary realism, realistic micro-shake"
}

# 3. Color-Safe Keying Backdrops (For Intentional Layer Compositing)
CHROMA_BACKDROPS: Dict[str, str] = {
    "chroma_royal_blue": (
        "isolated against a solid uniform studio pure royal blue backdrop (#0047AB), "
        "clean studio cyc wall, zero shadows on blue background, color-safe for warm/desert/khaki subjects, "
        "perfect for post-production chroma key extraction"
    ),
    "chroma_magenta": (
        "isolated against a solid uniform studio pure magenta backdrop (#FF00FF), "
        "clean studio cyc wall, zero shadows on magenta background, color-safe for cool/navy/blue subjects, "
        "perfect for post-production chroma key extraction"
    ),
    "chroma_emerald": (
        "isolated against a solid uniform studio emerald green backdrop (#00FF00), "
        "clean studio cyc wall, zero green spill on subject, color-safe for non-green subjects"
    ),
    "chroma_high_key_white": (
        "isolated against a stark pure seamless white studio backdrop (#FFFFFF), "
        "even high-key commercial illumination, perfect for luma matte extraction and graphic sandwiching"
    ),
    "chroma_neutral_grey": (
        "isolated against a clean neutral 50% studio grey backdrop (#808080), "
        "clean seamless studio floor, soft falloff, perfect for dark-mode VSL compositing"
    )
}


def apply_cinematic_tokens(
    prompt: str,
    style: str = "raw",
    shot_scale: Optional[str] = None,
    motility: Optional[str] = None,
    chroma_backdrop: Optional[str] = None,
    lighting_match: Optional[str] = None
) -> str:
    """
    Enrich a base prompt with multi-dimensional cinematographic tokens:
    style, shot scale, camera motility, chroma backdrop for keying, and lighting match.
    """
    parts = [prompt.strip().rstrip(".")]

    # 1. Shot scale
    if shot_scale and shot_scale.lower().strip() in SHOT_SCALES:
        parts.append(SHOT_SCALES[shot_scale.lower().strip()])

    # 2. Camera motility
    if motility and motility.lower().strip() in CAMERA_MOTILITY:
        parts.append(CAMERA_MOTILITY[motility.lower().strip()])

    # 3. Chroma backdrop (for cutout intention)
    if chroma_backdrop and chroma_backdrop.lower().strip() in CHROMA_BACKDROPS:
        parts.append(CHROMA_BACKDROPS[chroma_backdrop.lower().strip()])

    # 4. Explicit lighting match
    if lighting_match:
        clean_light = lighting_match.strip().rstrip(".")
        parts.append(f"lighting direction: {clean_light}")

    # 5. Base visual style preset
    style_key = (style or "raw").lower().strip()
    preset = STYLE_PRESETS.get(style_key, "")
    if preset:
        parts.append(preset)

    return ", ".join(parts)


def apply_style_preset(prompt: str, style: str = "raw") -> str:
    """Compatibility function for applying a single style string."""
    return apply_cinematic_tokens(prompt, style=style)


def list_available_styles() -> Dict[str, Dict[str, str]]:
    """Return dictionary of all available style presets, shot scales, motility, and chroma options."""
    return {
        "styles": {k: v for k, v in STYLE_PRESETS.items() if v},
        "shot_scales": SHOT_SCALES,
        "camera_motility": CAMERA_MOTILITY,
        "chroma_backdrops": CHROMA_BACKDROPS
    }


def generate_character_sheet_prompt(
    character_description: str,
    wardrobe: Optional[str] = None,
    style: str = "character_portrait",
    lighting: str = "3-point studio Rembrandt lighting",
    chroma_backdrop: str = "chroma_royal_blue"
) -> str:
    """
    Generate a 3-angle character reference sheet prompt
    (front view, 45-degree three-quarter view, profile) for Google Flow character registration.
    """
    wardrobe_text = f", wearing {wardrobe}" if wardrobe else ""
    base = (
        f"Multi-angle character reference sheet of {character_description}{wardrobe_text}. "
        "Showing front view, 45-degree three-quarter view, and side profile view side-by-side. "
        "Consistent facial geometry, neutral expression, eye-level camera framing"
    )
    return apply_cinematic_tokens(
        base,
        style=style,
        shot_scale="medium_action",
        chroma_backdrop=chroma_backdrop,
        lighting_match=lighting
    )
