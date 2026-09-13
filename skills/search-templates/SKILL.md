---
name: search-templates
description: Submit and poll CapCut video-template searches and present interactive result cards. For multimodal search, upload local or attached videos/images through capcut-upload; pass uploaded videos by Vid and resolve uploaded image Uris through capcut_batch_media_url. Use when a user asks to find templates or similar edits, explore video ideas, discover hooks or story structures, compare pacing or transition styles, find a soundtrack mood, or use image/video context.
---

# Search CapCut Templates

Use CapCut template search as the authoritative source for templates and template-based creative inspiration.

## Understand the Goal

Extract constraints already present in the request:

- Story or communication goal
- Target platform, duration, and aspect ratio
- Audience, mood, pacing, and visual style
- Soundtrack mood, genre, energy, vocals, beat-sync, and original-audio preferences
- Available image or video context, distinguishing local/attached files from reusable video Vids and public image URLs

Proceed when the request is actionable. Ask only for a missing source file or a choice that would materially change the result.

## Multimodal Preparation (Mandatory)

Complete this preparation before calling `capcut_template_search` whenever image or video context is part of the request.

1. Classify every context asset:
   - A local path or user-attached video/image must be uploaded first.
   - An existing CapCut video `vid` may be reused without uploading.
   - An existing public downloadable image URL using `http` or `https` may be reused without uploading or URL resolution.
   - Do not pass audio as template-search context.
2. For any local or attached media with readable local paths, load and follow `capcut-upload` once for the complete video/image batch.
3. Require every uploaded video result to have `success:true`, a non-empty `vid`, and `setPublic.success:true`. Use that `vid` in the template-search video asset. Do not resolve or pass a URL or Uri for an uploaded video.
4. Collect every successful uploaded image `uri`. Call the MCP tool whose name ends with `capcut_batch_media_url` once with `uris` containing the complete image-Uri batch. Match each returned `images[].url` to its input `images[].uri`.
5. Require a non-empty public `http` or `https` URL for every uploaded image. Use only that URL in the template-search image asset; never pass the ImageX Uri to `capcut_template_search`, even as supplemental identity.
6. Do not call `capcut_template_search` until every requested context asset has completed its required preparation. If upload, video finalize, or image URL resolution fails, report the failed stage and preserve successful resource IDs. Proceed with a subset only when the user explicitly asks.

For a mixed uploaded batch, the required order is:

```text
capcut-upload -> capcut_batch_media_url (images only) -> capcut_template_search -> capcut_template_search_poll -> templates_preview (non-empty success only)
```

For example, after the uploader returns one video Vid and one image Uri, resolve the image before searching:

```json
{
  "uris": ["tos-bucket/path/reference.png"]
}
```

Use the matching URL from the media-URL result:

```json
{
  "images": [
    {
      "uri": "tos-bucket/path/reference.png",
      "url": "https://example.image.host/reference.png?..."
    }
  ]
}
```

The final search assets then contain the image URL and video Vid, never the local paths or image Uri.

## Search Workflow

Use the tool whose name ends with `capcut_template_search` for requests about video creation ideas, templates, references, formats, hooks, structures, pacing, transitions, visual styles, soundtrack moods, trends, or "how should I cut this."

1. Verify availability of `capcut_batch_media_url`, `capcut_template_search`, `capcut_template_search_poll`, and `templates_preview`.
2. Complete the mandatory multimodal preparation above when assets are present.
3. Search with the user's creative goal rather than only a literal title. Preserve the user's language and include supplied platform, ratio, mood, pacing, industry, event, or music atmosphere. Do not invent missing constraints. When the user explicitly requests an assets-only search, omit `query`; at least one prepared asset is then required.
4. Set `count` to the requested amount or `10`. Template search returns at most 10 results and uses the streaming search interface in its background worker.
5. Include at most 16 `assets`, only for successfully prepared image or video context. Build each asset with the MCP schema fields below; do not pass audio assets.
   - `asset_type`: required, either `image` or `video`.
   - Images must include a public downloadable `url` using `http` or `https`. Never include `uri`.
   - Videos must include an uploaded or previously supplied VOD `vid`. Do not include video `url` or `uri`.
   - Include `asset_id` only when the caller already has a stable ID. Otherwise let the server derive one from `vid` or `url`.
   - Include known `width`, `height`, `duration_ms`, and `aspect_ratio`; omit unknown values.
6. Call `capcut_template_search` only after constructing the complete prepared asset list. Preserve the returned `search_id`; this call only submits the search and does not contain template results.
7. Poll `capcut_template_search_poll` with that exact `search_id`. When `status` is `running`, wait the returned `next_poll_after_ms` before polling again. Stop polling when `status` is `succeeded` or `failed`; never submit a duplicate search merely because the first task is still running.
8. When the terminal result has `status: succeeded` and `total > 0`, present the template cards or call `templates_preview` if available. Copy the result verbatim: never abbreviate, truncate, summarize, omit, or rewrite any field. Preserve every URL and its full query string, especially `x-expires` and `x-signature`. When `total` is 0 or the status is `failed`, do not mount an empty template frame.
9. Present the templates clearly with their preview URLs, duration, ratio, and template links.

Example asset payloads:

```json
{
  "query": "Find fast-paced product launch templates matching these references",
  "count": 10,
  "assets": [
    {
      "asset_type": "image",
      "url": "https://example.com/reference.jpg",
      "width": 1080,
      "height": 1920,
      "aspect_ratio": "9:16"
    },
    {
      "asset_type": "video",
      "vid": "v0287example",
      "duration_ms": 12000,
      "aspect_ratio": "9:16"
    }
  ]
}
```

## Failure Handling

- If CapCut MCP is unavailable or unauthenticated, consult the sibling `capcut-mcp-auth` skill to ensure the MCP server is configured and authenticated.
- If async template search returns `status=running`, continue polling the same `search_id` after `next_poll_after_ms`.
- If async template search returns `status=failed`, stop polling and report the error.
- If submission returns `template_search_busy`, wait briefly before submitting once more.
