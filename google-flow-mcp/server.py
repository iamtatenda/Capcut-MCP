# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "mcp>=1.0.0",
#     "playwright>=1.40.0",
#     "python-dotenv>=1.0.0",
# ]
# ///
"""
Google Flow MCP Server (Persistent CDP & Batch Edition)
Exposes high-speed, direct video and image generation tools backed by a
persistent Chrome DevTools Protocol daemon.
Zero ephemeral browser launches, zero screenshots, unmetered Flow Pro quota.
"""

import os
import sys
import json
from pathlib import Path

CURRENT_DIR = Path(__file__).parent.resolve()
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:
    from mcp.server.fastmcp import FastMCP

from flow_daemon import is_cdp_ready, ensure_flow_daemon, CDP_PORT, DEFAULT_PROJECT_URL
from flow_cdp_client import (
    sync_generate_video,
    sync_generate_image,
    sync_list_ingredients,
    sync_prompt_agent,
    sync_harvest_assets
)
from presets import apply_cinematic_tokens, list_available_styles, generate_character_sheet_prompt
from batch_engine import generate_batch

mcp = FastMCP("google-flow")


@mcp.tool()
def gflow_generate_video(
    prompt: str,
    output_path: str,
    reference_asset: str = None,
    style: str = "raw",
    shot_scale: str = None,
    motility: str = None,
    chroma_backdrop: str = None,
    lighting_match: str = None,
    duration_seconds: int = 10,
    project_url: str = DEFAULT_PROJECT_URL
) -> str:
    """
    Generate a 16:9 cinematic motion video clip (.mp4) via Google Flow using persistent CDP.
    Instant in-page JS prompt injection (<10ms) and direct network payload interception.
    Supports Image-to-Video generation conditioned on reference_asset.
    
    Args:
        prompt: Detailed cinematic prompt (action, environment, subject).
        output_path: Local absolute path where the .mp4 should be saved.
        reference_asset: Optional existing canvas asset or character keyword to condition video motion on.
        style: Style preset ('documentary', 'vsl_macro', 'hypercar_commercial', 'character_portrait', 'cinematic_action', or 'raw').
        shot_scale: Optional shot scale ('macro_detail', 'intimate_close_up', 'medium_action', 'wide_epic', 'low_angle_hero').
        motility: Optional camera movement ('slow_push_in', 'tracking_lateral', 'locked_off', 'orbital_arc', 'subtle_handheld').
        chroma_backdrop: Optional studio keying backdrop ('chroma_royal_blue', 'chroma_magenta', 'chroma_emerald', 'chroma_high_key_white').
        lighting_match: Optional matching lighting direction/temperature (e.g. 'harsh top-right sunlight 3200K').
        duration_seconds: Video duration in seconds (default: 10).
        project_url: URL to the Google Flow project canvas.
    """
    try:
        final_prompt = apply_cinematic_tokens(
            prompt,
            style=style,
            shot_scale=shot_scale,
            motility=motility,
            chroma_backdrop=chroma_backdrop,
            lighting_match=lighting_match
        )
        res = sync_generate_video(final_prompt, output_path, duration_seconds, reference_asset, project_url)
        res["style_applied"] = style
        res["shot_scale"] = shot_scale
        res["motility"] = motility
        res["chroma_backdrop"] = chroma_backdrop
        res["reference_asset"] = reference_asset
        return json.dumps(res, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e), "prompt": prompt})


@mcp.tool()
def gflow_generate_image(
    prompt: str,
    output_path: str,
    reference_asset: str = None,
    style: str = "raw",
    shot_scale: str = None,
    motility: str = None,
    chroma_backdrop: str = None,
    lighting_match: str = None,
    aspect_ratio: str = "16:9",
    project_url: str = DEFAULT_PROJECT_URL
) -> str:
    """
    Generate a 16:9 cinematic still image (.jpeg/.png) via Google Flow using persistent CDP.
    Instant in-page JS prompt injection (<10ms) with zero screenshot overhead.
    Supports character consistency and style reference conditioned on reference_asset.
    
    Args:
        prompt: Image prompt describing scene, character, and lighting.
        output_path: Local absolute path where the image should be saved.
        reference_asset: Optional existing canvas asset or character keyword to inject as @ ingredient chip.
        style: Style preset ('documentary', 'vsl_macro', 'hypercar_commercial', 'character_portrait', 'cinematic_action', or 'raw').
        shot_scale: Optional shot scale ('macro_detail', 'intimate_close_up', 'medium_action', 'wide_epic', 'low_angle_hero').
        motility: Optional camera angle/framing token.
        chroma_backdrop: Optional studio keying backdrop ('chroma_royal_blue', 'chroma_magenta', 'chroma_emerald', 'chroma_high_key_white').
        lighting_match: Optional matching lighting direction/temperature.
        aspect_ratio: Aspect ratio (default: '16:9').
        project_url: URL to the Google Flow project canvas.
    """
    try:
        final_prompt = apply_cinematic_tokens(
            prompt,
            style=style,
            shot_scale=shot_scale,
            motility=motility,
            chroma_backdrop=chroma_backdrop,
            lighting_match=lighting_match
        )
        res = sync_generate_image(final_prompt, output_path, aspect_ratio, reference_asset, project_url)
        res["style_applied"] = style
        res["shot_scale"] = shot_scale
        res["chroma_backdrop"] = chroma_backdrop
        res["reference_asset"] = reference_asset
        return json.dumps(res, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e), "prompt": prompt})


@mcp.tool()
def gflow_list_canvas_ingredients(
    project_url: str = DEFAULT_PROJECT_URL
) -> str:
    """
    List all assets, characters, and cards currently available on the Google Flow canvas for @ ingredient injection.
    """
    try:
        items = sync_list_ingredients(project_url)
        return json.dumps({
            "status": "success",
            "count": len(items),
            "available_ingredients": items
        }, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@mcp.tool()
def gflow_generate_character_sheet(
    character_description: str,
    output_path: str,
    wardrobe: str = None,
    style: str = "character_portrait",
    lighting: str = "3-point studio Rembrandt lighting",
    chroma_backdrop: str = "chroma_royal_blue",
    project_url: str = DEFAULT_PROJECT_URL
) -> str:
    """
    Generate an intentional 3-angle character reference sheet (front view, 45-degree three-quarter view, profile)
    with studio lighting and chroma backdrop, optimized for registering as a persistent character in Google Flow.
    """
    try:
        sheet_prompt = generate_character_sheet_prompt(
            character_description=character_description,
            wardrobe=wardrobe,
            style=style,
            lighting=lighting,
            chroma_backdrop=chroma_backdrop
        )
        res = sync_generate_image(
            prompt=sheet_prompt,
            output_path=output_path,
            aspect_ratio="16:9",
            project_url=project_url
        )
        res["sheet_type"] = "3-angle-character-reference"
        return json.dumps(res, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@mcp.tool()
def gflow_prompt_agent(
    prompt: str,
    project_url: str = DEFAULT_PROJECT_URL,
    wait_seconds: int = 10
) -> str:
    """
    Prompt Google Flow's built-in conversational workspace agent directly.
    Allows submitting compound multi-shot batch directives (e.g. 4-5 scene storyboard shots).
    The Flow Agent orchestrates multiple tiles concurrently in the project canvas.
    
    Args:
        prompt: Multi-shot or compound prompt (e.g. 'Create 4 cinematic 16:9 video clips: 1) ... 2) ... 3) ...').
        project_url: URL to the Google Flow project canvas.
        wait_seconds: Seconds to wait after submission before returning control.
    """
    try:
        res = sync_prompt_agent(prompt, project_url)
        return json.dumps(res, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@mcp.tool()
def gflow_harvest_assets(
    output_dir: str,
    project_url: str = DEFAULT_PROJECT_URL
) -> str:
    """
    Harvest and download all newly completed image and video assets directly from the Google Flow canvas.
    Bypasses DOM scraping and downloads directly via session-authenticated streaming.
    
    Args:
        output_dir: Local folder path to save all harvested assets.
        project_url: URL to the Google Flow project canvas.
    """
    try:
        res = sync_harvest_assets(output_dir, project_url)
        return json.dumps(res, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@mcp.tool()
def gflow_generate_batch(
    manifest_json_or_file: str,
    output_dir: str,
    default_style: str = "raw",
    concurrent: bool = True,
    chain_continuity: bool = False,
    project_url: str = DEFAULT_PROJECT_URL
) -> str:
    """
    Generate an entire batch of scene assets from a JSON manifest.
    Default concurrent=True pipelines prompt injections onto the canvas for 3x-4x speedup.
    When chain_continuity=True, executes sequentially, attaching each scene's output card
    as an ingredient reference for the next scene to preserve character and wardrobe consistency.
    """
    try:
        res = generate_batch(
            manifest_json_or_file,
            output_dir,
            default_style,
            concurrent=concurrent,
            chain_continuity=chain_continuity,
            project_url=project_url
        )
        return json.dumps(res, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@mcp.tool()
def gflow_list_styles() -> str:
    """
    List all available pre-compiled visual style presets, shot scales, camera motility tokens, and chroma key backdrops.
    """
    styles = list_available_styles()
    return json.dumps(styles, indent=2)


@mcp.tool()
def gflow_auth_status() -> str:
    """
    Check the connection status of the persistent Google Flow CDP daemon.
    """
    ready = is_cdp_ready()
    return json.dumps({
        "cdp_port": CDP_PORT,
        "cdp_ready": ready,
        "project_url": DEFAULT_PROJECT_URL,
        "mode": "persistent_cdp_daemon"
    }, indent=2)


@mcp.tool()
def gflow_list_projects() -> str:
    """
    List configured Google Flow project details.
    """
    project_id = DEFAULT_PROJECT_URL.split("/project/")[-1] if "/project/" in DEFAULT_PROJECT_URL else "default"
    return json.dumps({
        "current_project": {
            "id": project_id,
            "url": DEFAULT_PROJECT_URL
        }
    }, indent=2)


if __name__ == "__main__":
    mcp.run()
