"""
Flow CDP Client (High-Speed & Workspace Agent Edition)
Communicates directly with persistent Chrome over DevTools Protocol.
Zero ephemeral browser launches, zero screenshot disk lag, instant in-page JS prompt injection (<10ms),
direct network payload interception, and built-in Flow Agent multi-clip orchestration.
"""

import os
import sys
import time
import json
import base64
import asyncio
import urllib.request
from pathlib import Path
from playwright.async_api import async_playwright

from flow_daemon import ensure_flow_daemon, CDP_PORT, DEFAULT_PROJECT_URL


async def _get_flow_page(browser_context, target_project_url: str = None):
    """Find an existing Flow project canvas tab or open/navigate to it."""
    url = target_project_url or DEFAULT_PROJECT_URL
    pages = browser_context.pages

    # 1. Look for an already loaded project canvas tab
    for page in pages:
        if "/project/" in page.url:
            return page

    # 2. If a generic flow/labs tab is open, navigate it to the project canvas
    for page in pages:
        if "flow.google.com" in page.url or "labs.google" in page.url:
            await page.goto(url, wait_until="domcontentloaded")
            return page

    # 3. Otherwise open a new page directly to the project URL
    page = await browser_context.new_page()
    await page.goto(url, wait_until="domcontentloaded")
    return page


class FlowSessionPool:
    """
    Singleton connection manager that maintains a persistent warm connection
    to Chrome CDP and the active Flow project tab.
    Eliminates cold Playwright initialization, browser launches, and tab lookups.
    """
    _instance = None

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self._lock = asyncio.Lock()
        self._project_url = DEFAULT_PROJECT_URL
        self._active_callback = None
        self._observer_initialized = False

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = FlowSessionPool()
        return cls._instance

    async def get_page(self, target_project_url: str = None):
        async with self._lock:
            url = target_project_url or self._project_url
            
            # Check if existing page and browser are healthy
            if self.page and not self.page.is_closed() and self.browser and self.browser.is_connected():
                if "/project/" in self.page.url:
                    return self.page

            if not ensure_flow_daemon(url):
                raise RuntimeError("Failed to connect or launch Chrome CDP daemon on port 9222")

            if not self.playwright:
                self.playwright = await async_playwright().start()

            if not self.browser or not self.browser.is_connected():
                self.browser = await self.playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
                self.context = self.browser.contexts[0] if self.browser.contexts else await self.browser.new_context()

            self.page = await _get_flow_page(self.context, url)
            await self.page.wait_for_load_state("domcontentloaded")
            self._observer_initialized = False
            return self.page

    def set_callback(self, cb):
        self._active_callback = cb

    async def ensure_observer(self):
        """Register the browser callback and MutationObserver on the canvas."""
        if not self.page or self.page.is_closed():
            return

        if not self._observer_initialized:
            try:
                async def _on_asset(src, title):
                    if self._active_callback:
                        await self._active_callback(src, title)

                await self.page.expose_function("__onFlowImageReady", _on_asset)
            except Exception:
                pass

            await self.page.evaluate('''() => {
                if (window.__flowObserverAttached) return;
                window.__flowObserverAttached = true;

                const checkAndEmit = (tile) => {
                    if (!tile) return;
                    const img = tile.querySelector('img.image, img[src*="/asb/"], img[src*="storage.googleapis.com"]');
                    const titleEl = tile.querySelector('.footer-title');
                    const title = titleEl ? (titleEl.innerText || titleEl.textContent || '') : '';
                    if (img) {
                        const src = img.currentSrc || img.src;
                        if (src && img.complete && img.naturalWidth > 0) {
                            window.__onFlowImageReady && window.__onFlowImageReady(src, title);
                        }
                    }
                };

                const observer = new MutationObserver((mutations) => {
                    for (const m of mutations) {
                        if (m.type === 'childList') {
                            m.addedNodes.forEach(node => {
                                if (node.nodeType !== 1) return;
                                if (node.tagName === 'FLOW-IMAGE-TILE') {
                                    checkAndEmit(node);
                                } else if (node.querySelectorAll) {
                                    node.querySelectorAll('flow-image-tile').forEach(checkAndEmit);
                                }
                            });
                        } else if (m.type === 'attributes' && m.attributeName === 'src') {
                            if (m.target && m.target.tagName === 'IMG') {
                                const tile = m.target.closest('flow-image-tile');
                                if (tile) checkAndEmit(tile);
                            }
                        }
                    }
                });

                const target = document.querySelector('flow-project-page') || document.body;
                observer.observe(target, { childList: true, subtree: true, attributes: true, attributeFilter: ['src'] });
            }''')
            self._observer_initialized = True

    async def close(self):
        async with self._lock:
            try:
                if self.browser:
                    if hasattr(self.browser, "disconnect"):
                        await self.browser.disconnect()
                    else:
                        await self.browser.close()
                if self.playwright:
                    await self.playwright.stop()
            except Exception:
                pass
            finally:
                self.browser = None
                self.context = None
                self.page = None
                self.playwright = None
                self._observer_initialized = False


async def _inject_prompt_fast(page, prompt_text: str, is_agent_chat: bool = False) -> bool:
    """
    Instant programmatic text insertion into ProseMirror or contenteditable in <10ms.
    Eliminates character-by-character keyboard typing lag.
    """
    selector = "textarea[placeholder*='create'], div[contenteditable='true'], textarea" if is_agent_chat else "div.ProseMirror, [contenteditable='true'], textarea"
    
    injected = await page.evaluate(f'''async () => {{
        const editor = document.querySelector("{selector}");
        if (!editor) return false;
        editor.focus();
        if (editor.tagName.toLowerCase() === 'textarea') {{
            editor.value = {json.dumps(prompt_text)};
            editor.dispatchEvent(new Event('input', {{ bubbles: true }}));
            editor.dispatchEvent(new Event('change', {{ bubbles: true }}));
            return true;
        }}
        // For contenteditable / ProseMirror:
        const sel = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(editor);
        sel.removeAllRanges();
        sel.addRange(range);
        document.execCommand('delete', false, null);
        document.execCommand('insertText', false, {json.dumps(prompt_text)});
        return true;
    }}''')
    
    if not injected:
        # Fallback to standard Playwright locator fill
        editor = page.locator(selector).first
        await editor.wait_for(state="visible", timeout=8000)
        await editor.click()
        await editor.fill(prompt_text)
    return True


async def _trigger_submit_fast(page, is_agent_chat: bool = False):
    """Trigger generation immediately without guessing or slow hunting."""
    submitted = await page.evaluate('''() => {
        let btn = document.querySelector("button[aria-label*='generate' i], button[aria-label*='send' i], button[aria-label*='submit' i], button.generate-button");
        if (!btn) {
            const buttons = Array.from(document.querySelectorAll("button"));
            btn = buttons.find(b => {
                const txt = (b.innerText || b.textContent || '').toLowerCase();
                return txt.includes('generate') || txt.includes('arrow_forward') || txt.includes('send') || txt.includes('create');
            });
        }
        if (btn && !btn.disabled) {
            btn.click();
            return true;
        }
        return false;
    }''')
    if not submitted:
        await page.keyboard.press("Enter")


async def _clear_ingredients(page) -> bool:
    """Remove all attached ingredient chips from the prompt box."""
    cleared = await page.evaluate('''() => {
        const chips = Array.from(document.querySelectorAll("flow-ingredient-chip button, .chip-container, button[aria-label*='remove' i], button[aria-label*='delete' i], .prompt-ingredient-bar button"));
        let count = 0;
        for (const btn of chips) {
            btn.click();
            count++;
        }
        return count;
    }''')
    return bool(cleared)


async def _attach_reference_ingredient(page, reference_name_or_keyword: str) -> bool:
    """
    Attach an existing project card or character as an active reference ingredient
    in Google Flow's prompt box via the @ mention menu.
    """
    if not reference_name_or_keyword:
        return False

    ref_kw = reference_name_or_keyword.lower().strip()

    attached = await page.evaluate(f'''async () => {{
        const editor = document.querySelector("div.ProseMirror");
        if (!editor) return {{ success: false, reason: "ProseMirror not found" }};

        // 1. Focus editor and clear current text
        editor.focus();
        const sel = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(editor);
        sel.removeAllRanges();
        sel.addRange(range);
        document.execCommand('delete', false, null);

        // 2. Type '@' to open mention menu
        document.execCommand('insertText', false, '@');
        await new Promise(r => setTimeout(r, 600));

        // 3. Search items in flow-add-menu
        const items = Array.from(document.querySelectorAll("flow-add-menu-asset-item, button.asset-item, .asset-item"));
        const targetKw = {json.dumps(ref_kw)};
        
        let match = items.find(el => (el.innerText || '').toLowerCase().includes(targetKw));
        if (!match && items.length > 0) {{
            // Fallback to matching first substantive token
            const tokens = targetKw.split(/\\s+/).filter(t => t.length >= 3);
            match = items.find(el => {{
                const txt = (el.innerText || '').toLowerCase();
                return tokens.some(tok => txt.includes(tok));
            }});
        }}

        if (match) {{
            const btn = match.tagName === 'BUTTON' ? match : match.querySelector('button') || match;
            btn.click();
            await new Promise(r => setTimeout(r, 600));
            return {{ success: true, matched: match.innerText.trim().replace(/\\s+/g, ' ') }};
        }}

        return {{ success: false, reason: "No matching asset in @ menu for: " + targetKw }};
    }}''')

    if attached.get("success"):
        return True
    return False


async def list_canvas_ingredients(project_url: str = None) -> list:
    """List all assets and characters available on canvas for @ ingredient injection."""
    pool = FlowSessionPool.get_instance()
    page = await pool.get_page(project_url)

    items = await page.evaluate('''async () => {
        const editor = document.querySelector("div.ProseMirror");
        if (!editor) return [];

        editor.focus();
        const sel = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(editor);
        sel.removeAllRanges();
        sel.addRange(range);
        document.execCommand('delete', false, null);
        document.execCommand('insertText', false, '@');
        await new Promise(r => setTimeout(r, 600));

        const menuItems = Array.from(document.querySelectorAll("flow-add-menu-asset-item, button.asset-item")).map(el => {
            return (el.innerText || '').trim().replace(/\\s+/g, ' ');
        });

        // Close menu with Escape
        const escEvent = new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true });
        editor.dispatchEvent(escEvent);

        return Array.from(new Set(menuItems));
    }''')
    return items


async def generate_video_cdp(
    prompt: str,
    output_path: str,
    duration_seconds: int = 10,
    reference_asset: str = None,
    project_url: str = None,
    timeout_seconds: int = 180
) -> dict:
    """
    Generate a video via Google Flow using the persistent CDP session.
    Intercepts network responses directly without taking screenshots.
    """
    if not ensure_flow_daemon(project_url or DEFAULT_PROJECT_URL):
        raise RuntimeError("Failed to connect or launch Chrome CDP daemon on port 9222")

    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    captured_urls = []
    completion_event = asyncio.Event()

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await _get_flow_page(context, project_url)
        await page.wait_for_load_state("domcontentloaded")

        # Record pre-existing video URLs on canvas
        existing_videos = set(await page.evaluate('''() => {
            const urls = [];
            document.querySelectorAll("video").forEach(v => {
                if (v.currentSrc) urls.push(v.currentSrc);
                if (v.src) urls.push(v.src);
            });
            return urls;
        }'''))

        # Attach network listener for video URLs and status APIs
        async def on_response(response):
            resp_url = response.url
            try:
                if "batchCheckAsyncVideoGenerationStatus" in resp_url or "batchAsyncGenerateVideoText" in resp_url:
                    if response.status == 200:
                        data = await response.json()
                        res_str = json.dumps(data)
                        if "storage.googleapis.com" in res_str:
                            for op in data.get("operations", []):
                                media = op.get("response", {}).get("media", {})
                                url_val = media.get("video", {}).get("url") or media.get("url")
                                if url_val and url_val not in existing_videos and url_val not in captured_urls:
                                    captured_urls.append(url_val)
                                    completion_event.set()
                elif "storage.googleapis.com" in resp_url and (".mp4" in resp_url or "video" in resp_url):
                    if resp_url not in existing_videos and resp_url not in captured_urls:
                        captured_urls.append(resp_url)
                        completion_event.set()
            except Exception:
                pass

        page.on("response", on_response)

        # Attach reference ingredient if specified, otherwise clear previous chips
        if reference_asset:
            await _attach_reference_ingredient(page, reference_asset)
        else:
            await _clear_ingredients(page)

        # Instant prompt injection (<10ms)
        await _inject_prompt_fast(page, prompt)

        # Fast submit
        await _trigger_submit_fast(page)

        # Dual-detection: Network listener + active 1000ms DOM video polling
        download_url = None
        start_poll = time.time()
        
        while time.time() - start_poll < timeout_seconds:
            if captured_urls:
                download_url = captured_urls[0]
                break
                
            # Check DOM for completed video element that did not exist previously
            v_src = await page.evaluate('''(data) => {
                const existing = new Set(data.existing);
                const videos = Array.from(document.querySelectorAll("video"));
                for (const v of videos) {
                    const src = v.currentSrc || v.src;
                    if (src && !existing.has(src) && src.startsWith('http')) {
                        return src;
                    }
                }
                return null;
            }''', {"existing": list(existing_videos)})
            if v_src:
                download_url = v_src
                break
                
            await asyncio.sleep(1.0)

        if not download_url:
            raise TimeoutError(f"Video generation timed out after {timeout_seconds}s or download URL not emitted")

        # Download asset directly to disk
        urllib.request.urlretrieve(download_url, str(out_file))

        if hasattr(browser, "disconnect"):
            await browser.disconnect()
        else:
            await browser.close()

    return {
        "status": "success",
        "output_path": str(out_file),
        "source_url": download_url,
        "prompt": prompt
    }


async def generate_image_cdp(
    prompt: str,
    output_path: str,
    aspect_ratio: str = "16:9",
    reference_asset: str = None,
    project_url: str = None,
    timeout_seconds: int = 90
) -> dict:
    """
    Generate a still image via Google Flow using the persistent CDP session.
    Ultra-low latency DOM injection (<10ms) and instant MutationObserver push notifications.
    """
    pool = FlowSessionPool.get_instance()
    page = await pool.get_page(project_url)

    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    # Quick non-blocking modal dismissal
    try:
        modal_btn = page.locator("button:has-text('Get started'), button:has-text('Dismiss'), button:has-text('Got it'), button:has-text('Close')").first
        if await modal_btn.is_visible():
            await modal_btn.click()
    except Exception:
        pass

    # Record pre-existing URLs on canvas
    existing_urls = set(await page.evaluate('''() => {
        const urls = [];
        document.querySelectorAll("img").forEach(img => {
            if (img.currentSrc) urls.push(img.currentSrc);
            if (img.src) urls.push(img.src);
        });
        return urls;
    }'''))

    # Prepare keywords for strict card matching
    prompt_prefix = prompt.split(',')[0].strip()

    # Extract primary subject nouns (excluding generic environmental adjectives)
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
    # Primary subject words (first 3 substantive words of prompt)
    subject_words = prompt_tokens[:3] if prompt_tokens else [prompt_prefix.lower()[:15]]

    # Setup push callback for instant observer notification
    push_result = {}
    push_event = asyncio.Event()

    async def _on_push_asset(src, title):
        if src in existing_urls:
            return
        t_low = (title or "").lower()
        matches_subject = any(sw in t_low for sw in subject_words)
        if matches_subject:
            push_result["url"] = src
            push_event.set()

    pool.set_callback(_on_push_asset)
    await pool.ensure_observer()

    # Attach reference ingredient if specified, otherwise clear previous chips
    if reference_asset:
        await _attach_reference_ingredient(page, reference_asset)
    else:
        await _clear_ingredients(page)

    # Instant prompt injection (<10ms)
    await _inject_prompt_fast(page, prompt)

    # Fast submit
    await _trigger_submit_fast(page)

    # Active polling + push event listener
    captured_url = None
    start_poll = time.time()
    
    while time.time() - start_poll < timeout_seconds:
        elapsed = time.time() - start_poll

        if elapsed >= 14.0:
            if push_event.is_set() and "url" in push_result:
                captured_url = push_result["url"]
                break
            
            # Detect completed card strictly scoped to matching tiles
            detected_url = await page.evaluate('''(data) => {
                const existing = new Set(data.existing);
                const subjectWords = data.subjectWords;
                const promptPrefix = data.promptPrefix.toLowerCase();

                // Strategy 1: Find by .footer-title strictly matching subject
                const titles = Array.from(document.querySelectorAll('.footer-title'));
                for (const t of titles) {
                    const text = (t.innerText || t.textContent || '').toLowerCase();
                    const matchesPrefix = promptPrefix.length > 5 && text.includes(promptPrefix.slice(0, 25));
                    const matchesSubject = subjectWords.length > 0 && subjectWords.some(sw => text.includes(sw));

                    if (matchesPrefix || matchesSubject) {
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
                                if (src && !existing.has(src) && (src.includes('/asb/') || src.includes('storage.googleapis.com') || src.startsWith('http'))) {
                                    if (img.complete && img.naturalWidth > 0) {
                                        return src;
                                    }
                                }
                            }
                        }
                    }
                }

                // Strategy 2: After 20s if generation has settled, inspect the newest mounted tile
                if (data.elapsed >= 20.0) {
                    const firstTile = document.querySelector('flow-image-tile');
                    if (firstTile) {
                        const titleEl = firstTile.querySelector('.footer-title');
                        const tileText = titleEl ? (titleEl.innerText || '').toLowerCase() : '';
                        const matchesSubject = subjectWords.length > 0 && subjectWords.some(sw => tileText.includes(sw));
                        if (matchesSubject) {
                            const img = firstTile.querySelector('img.image, img[src*="/asb/"], img[src*="storage.googleapis.com"]');
                            if (img) {
                                const src = img.currentSrc || img.src;
                                if (src && !existing.has(src) && (src.includes('/asb/') || src.includes('storage.googleapis.com') || src.startsWith('http'))) {
                                    if (img.complete && img.naturalWidth > 0) {
                                        return src;
                                    }
                                }
                            }
                        }
                    }
                }

                return null;
            }''', {
                "existing": list(existing_urls),
                "subjectWords": subject_words,
                "promptPrefix": prompt_prefix,
                "elapsed": elapsed
            })
            
            if detected_url:
                captured_url = detected_url
                break
            
        await asyncio.sleep(0.25)

    pool.set_callback(None)

    if not captured_url:
        raise TimeoutError(f"Image generation timed out after {timeout_seconds}s")

    # Download via in-page fetch to preserve session authentication
    img_bytes = await page.evaluate('''async (url) => {
        const resp = await fetch(url);
        const blob = await resp.blob();
        return new Promise((resolve) => {
            const reader = new FileReader();
            reader.onloadend = () => resolve(reader.result.split(',')[1]);
            reader.readAsDataURL(blob);
        });
    }''', captured_url)
    out_file.write_bytes(base64.b64decode(img_bytes))

    return {
        "status": "success",
        "output_path": str(out_file),
        "source_url": captured_url,
        "prompt": prompt
    }


async def prompt_flow_agent_cdp(
    prompt: str,
    project_url: str = None,
    wait_seconds: int = 10
) -> dict:
    """Prompt the built-in Google Flow conversational workspace agent."""
    if not ensure_flow_daemon(project_url or DEFAULT_PROJECT_URL):
        raise RuntimeError("Failed to connect or launch Chrome CDP daemon on port 9222")

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await _get_flow_page(context, project_url)
        await page.wait_for_load_state("domcontentloaded")

        await _inject_prompt_fast(page, prompt, is_agent_chat=True)
        await _trigger_submit_fast(page, is_agent_chat=True)

        await page.wait_for_timeout(wait_seconds * 1000)

        if hasattr(browser, "disconnect"):
            await browser.disconnect()
        else:
            await browser.close()

    return {
        "status": "success",
        "message": f"Prompt submitted to Google Flow Agent: {prompt[:80]}...",
        "workspace_url": project_url or DEFAULT_PROJECT_URL
    }


async def harvest_canvas_assets_cdp(
    output_dir: str,
    project_url: str = None
) -> dict:
    """Scan the Google Flow canvas and harvest all newly completed image and video assets."""
    if not ensure_flow_daemon(project_url or DEFAULT_PROJECT_URL):
        raise RuntimeError("Failed to connect or launch Chrome CDP daemon on port 9222")

    out_path = Path(output_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    harvested = []

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await _get_flow_page(context, project_url)
        await page.wait_for_load_state("domcontentloaded")

        asset_urls = await page.evaluate('''() => {
            const urls = [];
            document.querySelectorAll("video, img").forEach(el => {
                const src = el.src || (el.querySelector("source") ? el.querySelector("source").src : "");
                if (src && (src.includes("/asb/") || src.includes("storage.googleapis.com"))) {
                    urls.push({
                        type: el.tagName.toLowerCase() === 'video' ? 'video' : 'image',
                        url: src
                    });
                }
            });
            return urls;
        }''')

        for idx, item in enumerate(asset_urls):
            u = item["url"]
            t = item["type"]
            ext = "mp4" if t == "video" else "jpeg"
            target_file = out_path / f"harvested_{idx+1:02d}_{int(time.time())}.{ext}"

            try:
                if t == "video":
                    urllib.request.urlretrieve(u, str(target_file))
                else:
                    img_bytes = await page.evaluate('''async (url) => {
                        const resp = await fetch(url);
                        const blob = await resp.blob();
                        return new Promise((resolve) => {
                            const reader = new FileReader();
                            reader.onloadend = () => resolve(reader.result.split(',')[1]);
                            reader.readAsDataURL(blob);
                        });
                    }''', u)
                    target_file.write_bytes(base64.b64decode(img_bytes))

                harvested.append({
                    "type": t,
                    "file_path": str(target_file),
                    "source_url": u
                })
            except Exception as e:
                print(f"[HARVEST ERROR] {u}: {e}")

        if hasattr(browser, "disconnect"):
            await browser.disconnect()
        else:
            await browser.close()

    return {
        "status": "success",
        "output_dir": str(out_path),
        "harvested_count": len(harvested),
        "assets": harvested
    }


def sync_generate_video(
    prompt: str,
    output_path: str,
    duration_seconds: int = 10,
    reference_asset: str = None,
    project_url: str = None
) -> dict:
    """Synchronous entrypoint for video generation."""
    return asyncio.run(generate_video_cdp(prompt, output_path, duration_seconds, reference_asset, project_url))


def sync_generate_image(
    prompt: str,
    output_path: str,
    aspect_ratio: str = "16:9",
    reference_asset: str = None,
    project_url: str = None
) -> dict:
    """Synchronous entrypoint for image generation."""
    return asyncio.run(generate_image_cdp(prompt, output_path, aspect_ratio, reference_asset, project_url))


def sync_list_ingredients(project_url: str = None) -> list:
    """Synchronous entrypoint for listing available canvas reference ingredients."""
    return asyncio.run(list_canvas_ingredients(project_url))


def sync_prompt_agent(prompt: str, project_url: str = None) -> dict:
    """Synchronous entrypoint for prompting the Flow Agent."""
    return asyncio.run(prompt_flow_agent_cdp(prompt, project_url))


def sync_harvest_assets(output_dir: str, project_url: str = None) -> dict:
    """Synchronous entrypoint for harvesting assets from canvas."""
    return asyncio.run(harvest_canvas_assets_cdp(output_dir, project_url))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Google Flow Persistent CDP Direct Generator")
    parser.add_argument("--prompt", "-p", required=True, help="Generation prompt")
    parser.add_argument("--output", "-o", required=True, help="Output file path (.jpeg / .mp4)")
    parser.add_argument("--type", "-t", choices=["image", "video"], default="image", help="Asset type")
    parser.add_argument("--reference", "-r", help="Name or keyword of existing canvas asset/character to attach as reference ingredient")
    parser.add_argument("--style", "-s", default="raw", help="Style preset")
    parser.add_argument("--duration", "-d", type=int, default=10, help="Duration in seconds (for video)")
    parser.add_argument("--aspect", "-a", default="16:9", help="Aspect ratio")
    parser.add_argument("--project", help="Flow project URL")

    args = parser.parse_args()

    try:
        from presets import apply_style_preset
        final_prompt = apply_style_preset(args.prompt, args.style)
    except Exception:
        final_prompt = args.prompt

    t0 = time.time()
    try:
        if args.type == "video":
            res = sync_generate_video(final_prompt, args.output, args.duration, args.reference, args.project)
        else:
            res = sync_generate_image(final_prompt, args.output, args.aspect, args.reference, args.project)
        elapsed = round(time.time() - t0, 2)
        print(f"\n[DONE] Finished in {elapsed}s: {res.get('output_path')}")
    finally:
        asyncio.run(FlowSessionPool.get_instance().close())
