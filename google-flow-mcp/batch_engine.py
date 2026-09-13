"""
Google Flow Batch Generation Engine
Processes entire storyboards or video script manifests in a single session.
Reuses the persistent CDP connection across all scenes without reconnect overhead.
"""

import os
import sys
import json
import time
import asyncio
from pathlib import Path
from typing import List, Dict, Union, Any

# Ensure tools dir is in sys.path
TOOLS_DIR = Path(__file__).parent.resolve()
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from presets import apply_cinematic_tokens, apply_style_preset
from flow_cdp_client import sync_generate_image, sync_generate_video


def parse_manifest(manifest_input: Union[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Parse manifest from file path, JSON string, or list of dicts."""
    if isinstance(manifest_input, list):
        return manifest_input
    
    if isinstance(manifest_input, str):
        p = Path(manifest_input)
        if p.exists() and p.is_file():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        try:
            return json.loads(manifest_input)
        except Exception as e:
            raise ValueError(f"Could not parse manifest string as JSON or file: {e}")

    raise TypeError(f"Invalid manifest input type: {type(manifest_input)}")


def generate_batch(
    manifest_input: Union[str, List[Dict[str, Any]]],
    output_dir: str,
    default_style: str = "raw",
    concurrent: bool = True,
    chain_continuity: bool = False,
    project_url: str = None
) -> Dict[str, Any]:
    """
    Generate an entire batch of scene assets (images and videos).
    When concurrent=True and not chain_continuity, pipelines all prompt injections onto Google Flow's canvas
    for 3x-4x speedup by rendering simultaneously in the cloud.
    When chain_continuity=True, executes sequentially, attaching each scene's completed asset
    as an ingredient reference for the next scene to preserve character and lighting continuity.
    """
    if concurrent and not chain_continuity:
        return generate_batch_concurrent(manifest_input, output_dir, default_style, project_url)

    scenes = parse_manifest(manifest_input)
    out_path = Path(output_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    t_start = time.time()
    completed = []
    failed = []
    previous_ref_keyword = None

    print(f"[BATCH] Starting batch generation for {len(scenes)} scenes in: {out_path} (chain_continuity={chain_continuity})")

    for idx, scene in enumerate(scenes):
        scene_id = scene.get("id", f"scene_{idx+1:02d}")
        asset_type = scene.get("type", "image").lower()
        base_prompt = scene.get("prompt", "")
        style = scene.get("style", default_style)
        shot_scale = scene.get("shot_scale")
        motility = scene.get("motility")
        chroma_backdrop = scene.get("chroma_backdrop")
        lighting_match = scene.get("lighting_match")
        aspect = scene.get("aspect_ratio", "16:9")
        duration = scene.get("duration_seconds", 10)

        # Reference asset / character continuity
        ref_asset = scene.get("reference_asset") or scene.get("reference_character")
        if not ref_asset and chain_continuity and previous_ref_keyword:
            ref_asset = previous_ref_keyword

        # Apply multi-dimensional cinematographic tokens
        final_prompt = apply_cinematic_tokens(
            base_prompt,
            style=style,
            shot_scale=shot_scale,
            motility=motility,
            chroma_backdrop=chroma_backdrop,
            lighting_match=lighting_match
        )
        ext = "mp4" if asset_type == "video" else "jpeg"
        target_file = out_path / f"{scene_id}.{ext}"

        print(f"\n[BATCH] [{idx+1}/{len(scenes)}] Generating {asset_type.upper()}: {scene_id}")
        if ref_asset:
            print(f"[BATCH] Reference Asset Attached: {ref_asset}")
        print(f"[BATCH] Prompt: {final_prompt[:80]}...")

        scene_t0 = time.time()
        try:
            if asset_type == "video":
                res = sync_generate_video(
                    prompt=final_prompt,
                    output_path=str(target_file),
                    duration_seconds=duration,
                    reference_asset=ref_asset,
                    project_url=project_url
                )
            else:
                res = sync_generate_image(
                    prompt=final_prompt,
                    output_path=str(target_file),
                    aspect_ratio=aspect,
                    reference_asset=ref_asset,
                    project_url=project_url
                )

            scene_elapsed = round(time.time() - scene_t0, 2)
            completed.append({
                "id": scene_id,
                "type": asset_type,
                "output_path": str(target_file),
                "reference_asset": ref_asset,
                "file_size": target_file.stat().st_size if target_file.exists() else 0,
                "elapsed_seconds": scene_elapsed,
                "prompt": final_prompt
            })
            first_words = [w for w in final_prompt.split(',')[0].split() if len(w) >= 4]
            previous_ref_keyword = " ".join(first_words[:2]) if first_words else scene_id
            print(f"[BATCH] SUCCESS: {scene_id} ({scene_elapsed}s)")
        except Exception as e:
            scene_elapsed = round(time.time() - scene_t0, 2)
            failed.append({
                "id": scene_id,
                "error": str(e),
                "elapsed_seconds": scene_elapsed,
                "prompt": final_prompt
            })
            print(f"[BATCH] FAILED: {scene_id} ({scene_elapsed}s): {e}")

    total_time = round(time.time() - t_start, 2)
    return {
        "status": "success" if not failed else ("partial" if completed else "failed"),
        "output_dir": str(out_path),
        "total_scenes": len(scenes),
        "completed_count": len(completed),
        "failed_count": len(failed),
        "total_elapsed_seconds": total_time,
        "completed": completed,
        "failed": failed
    }


async def _generate_batch_concurrent_async(
    scenes: List[Dict[str, Any]],
    out_path: Path,
    default_style: str = "raw",
    project_url: str = None,
    timeout_seconds: int = 150
) -> Dict[str, Any]:
    from flow_cdp_client import FlowSessionPool, _inject_prompt_fast, _trigger_submit_fast
    import base64
    import asyncio

    pool = FlowSessionPool.get_instance()
    page = await pool.get_page(project_url)

    existing_urls = set(await page.evaluate('''() => {
        const urls = [];
        document.querySelectorAll("img").forEach(img => {
            if (img.currentSrc) urls.push(img.currentSrc);
            if (img.src) urls.push(img.src);
        });
        return urls;
    }'''))

    dispatched_scenes = []
    t_start = time.time()

    for idx, scene in enumerate(scenes):
        scene_id = scene.get("id", f"scene_{idx+1:02d}")
        asset_type = scene.get("type", "image").lower()
        base_prompt = scene.get("prompt", "")
        style = scene.get("style", default_style)
        shot_scale = scene.get("shot_scale")
        motility = scene.get("motility")
        chroma_backdrop = scene.get("chroma_backdrop")
        lighting_match = scene.get("lighting_match")
        aspect = scene.get("aspect_ratio", "16:9")

        final_prompt = apply_cinematic_tokens(
            base_prompt,
            style=style,
            shot_scale=shot_scale,
            motility=motility,
            chroma_backdrop=chroma_backdrop,
            lighting_match=lighting_match
        )
        ext = "mp4" if asset_type == "video" else "jpeg"
        target_file = out_path / f"{scene_id}.{ext}"

        prompt_prefix = final_prompt.split(',')[0].strip()
        STOP_WORDS = {
            'the', 'and', 'with', 'for', 'from', 'parked', 'outside', 'inside', 'front', 'back', 
            'sunset', 'sunrise', 'dusk', 'dawn', 'day', 'night', 'road', 'highway', 'street', 
            'city', 'luxury', 'modern', 'cinematic', 'photo', 'photography', 'ultra', 'realistic', 
            'commercial', 'scenic', 'dramatic', '4k', '8k', 'hd', 'view', 'shot', 'high', 'detail'
        }
        prompt_tokens = [
            w for w in "".join(c if c.isalnum() else " " for c in prompt_prefix.lower()).split()
            if len(w) >= 3 and w not in STOP_WORDS
        ]
        subject_words = prompt_tokens[:3] if prompt_tokens else [prompt_prefix.lower()[:15]]

        dispatched_scenes.append({
            "id": scene_id,
            "type": asset_type,
            "prompt": final_prompt,
            "prompt_prefix": prompt_prefix,
            "subject_words": subject_words,
            "target_file": target_file,
            "completed": False,
            "output_path": None,
            "error": None,
            "elapsed": None
        })

    print(f"[CONCURRENT BATCH] Submitting {len(dispatched_scenes)} scenes concurrently onto canvas...")

    for s in dispatched_scenes:
        await _inject_prompt_fast(page, s["prompt"])
        await _trigger_submit_fast(page)
        print(f"[CONCURRENT BATCH] Dispatched: {s['id']} -> {s['prompt'][:60]}...")
        await asyncio.sleep(0.8)

    print(f"[CONCURRENT BATCH] All prompts dispatched. Now awaiting cloud renders concurrently...")

    start_poll = time.time()
    downloaded_urls = set()

    while time.time() - start_poll < timeout_seconds:
        all_done = all(s["completed"] for s in dispatched_scenes)
        if all_done:
            break

        tiles_data = await page.evaluate('''(existingList) => {
            const existing = new Set(existingList);
            const titles = Array.from(document.querySelectorAll('.footer-title'));
            const matches = [];

            for (const t of titles) {
                const titleText = (t.innerText || t.textContent || '').toLowerCase();
                let container = t;
                while (container && 
                       container.tagName !== 'FLOW-TILE-CONTAINER' && 
                       container.tagName !== 'FLOW-IMAGE-TILE' && 
                       !container.className.includes('container') && 
                       container !== document.body) {
                    container = container.parentElement;
                }
                if (container && container !== document.body) {
                    const img = container.querySelector('img.image, img[src*="/asb/"], img[src*="storage.googleapis.com"]');
                    if (img) {
                        const src = img.currentSrc || img.src;
                        if (src && !existing.has(src) && img.complete && img.naturalWidth > 0) {
                            matches.push({ title: titleText, src: src });
                        }
                    }
                }
            }
            return matches;
        }''', list(existing_urls))

        if time.time() - t_start < 14.0:
            await asyncio.sleep(0.5)
            continue

        for tile in tiles_data:
            tile_title = (tile.get("title") or "").lower()
            tile_src = tile.get("src")
            if not tile_src or tile_src in downloaded_urls:
                continue

            for s in dispatched_scenes:
                if s["completed"]:
                    continue
                matches_prefix = s["prompt_prefix"].lower()[:20] in tile_title if len(s["prompt_prefix"]) > 5 else False
                matches_subject = any(sw in tile_title for sw in s["subject_words"]) if s["subject_words"] else False

                if matches_prefix or matches_subject:
                    downloaded_urls.add(tile_src)
                    try:
                        img_bytes = await page.evaluate('''async (url) => {
                            const resp = await fetch(url);
                            const blob = await resp.blob();
                            return new Promise((resolve) => {
                                const reader = new FileReader();
                                reader.onloadend = () => resolve(reader.result.split(',')[1]);
                                reader.readAsDataURL(blob);
                            });
                        }''', tile_src)
                        s["target_file"].write_bytes(base64.b64decode(img_bytes))
                        s["completed"] = True
                        s["output_path"] = str(s["target_file"])
                        s["elapsed"] = round(time.time() - t_start, 2)
                        print(f"[CONCURRENT BATCH] SUCCESS: {s['id']} ready in {s['elapsed']}s")
                    except Exception as e:
                        s["error"] = str(e)
                    break

        await asyncio.sleep(0.5)

    total_time = round(time.time() - t_start, 2)
    completed = [
        {k: (str(v) if isinstance(v, Path) else v) for k, v in s.items()}
        for s in dispatched_scenes if s["completed"]
    ]
    failed = [
        {k: (str(v) if isinstance(v, Path) else v) for k, v in s.items()}
        for s in dispatched_scenes if not s["completed"]
    ]

    return {
        "status": "success" if not failed else ("partial" if completed else "failed"),
        "mode": "concurrent_pipelined",
        "output_dir": str(out_path),
        "total_scenes": len(dispatched_scenes),
        "completed_count": len(completed),
        "failed_count": len(failed),
        "total_elapsed_seconds": total_time,
        "completed": completed,
        "failed": failed
    }


def generate_batch_concurrent(
    manifest_input: Union[str, List[Dict[str, Any]]],
    output_dir: str,
    default_style: str = "raw",
    project_url: str = None
) -> Dict[str, Any]:
    """Synchronous entrypoint for concurrent batch generation."""
    scenes = parse_manifest(manifest_input)
    out_path = Path(output_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)
    return asyncio.run(_generate_batch_concurrent_async(scenes, out_path, default_style, project_url))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Google Flow Batch Scene Generator")
    parser.add_argument("--manifest", "-m", required=True, help="Path to manifest JSON or JSON string")
    parser.add_argument("--output-dir", "-o", required=True, help="Output directory")
    parser.add_argument("--style", "-s", default="raw", help="Default style preset")
    parser.add_argument("--chain-continuity", "-c", action="store_true", help="Chain each scene's output card as reference asset for subsequent scenes")
    args = parser.parse_args()

    result = generate_batch(args.manifest, args.output_dir, args.style, chain_continuity=args.chain_continuity)
    print(json.dumps(result, indent=2))
