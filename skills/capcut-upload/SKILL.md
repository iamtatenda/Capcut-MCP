---
name: capcut-upload
description: Upload one or more local videos and images to CapCut and return reusable resource IDs. Use the bundled local uploader with capcut_asset_upload_credential when the sources have readable local paths. Mixed video/image batches are supported; videos must be made public before success. Audio and private video uploads are not supported.
---

# Upload Media to CapCut

Upload 1 to 16 local videos or images in one mixed batch. Return a public-ready video `vid` or image `uri` for each successful item.

## Upload Workflow

Load and follow [references/local-upload.md](references/local-upload.md) for the complete batch. Every source must have a readable local path, and the tool whose name ends with `capcut_asset_upload_credential` must be available.

If the credential tool is unavailable, consult the sibling `capcut-mcp-auth` skill. If a source has no readable local path, report that local file access is required.

## Invariants

- Reject audio before requesting credentials or invoking an upload tool.
- Preserve input order and upload mixed video/image inputs in one batch.
- Treat a video as successful only when it has a non-empty `vid` and `setPublic.success:true`.
- Treat an image as successful only when it has a non-empty `uri`.
- Preserve successful identifiers from partial failures and never re-upload an item that already has a `vid`, `uri`, or `uploadSuccess:true`.
- Never request or expose cookies, bearer tokens, permanent credentials, raw headers, signing material, or complete short-lived upload sessions.

## Result Contract

Return reusable identifiers together with concise per-file status. For video finalize failures, preserve the Vid and report the `set_public` stage; do not upload the raw bytes again.
