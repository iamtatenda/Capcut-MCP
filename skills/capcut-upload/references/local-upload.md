# Local Upload Workflow

Use this workflow only when the tool whose name ends with `capcut_asset_upload_credential` is available, every source has a readable local path, and Node.js is available.

`SKILL_ROOT` is the directory containing the parent `SKILL.md`. The bundled uploader is `<SKILL_ROOT>/scripts/capcut-upload.mjs` and uses Node.js built-ins only (zero external npm dependencies).

## Security Model

- Request one complete, short-lived upload session from `capcut_asset_upload_credential` for the current authenticated user.
- Never use permanent AK/SK credentials or assemble/override credential, region, host, space, service, account, or protocol fields.
- Pass the upload session response through `--upload-session-stdin` or `--upload-session`.
- Require the returned `video_finalize` capability for video batches. The uploader sends it only to the fixed HTTPS CapCut finalize endpoint.

## Upload Workflow

1. Resolve each absolute path and collect its base file name and byte size.
2. Call `capcut_asset_upload_credential` once with 1 to 16 entries:

```json
{
  "files": [
    {"file_name": "clip.mp4", "size_bytes": 123456},
    {"file_name": "cover.png", "size_bytes": 23456}
  ]
}
```

3. Run the uploader for the batch:

```bash
node "<SKILL_ROOT>/scripts/capcut-upload.mjs" \
  --files '[{"client_id":"video-1","file":"<ABSOLUTE_VIDEO_PATH>"},{"client_id":"image-1","file":"<ABSOLUTE_IMAGE_PATH>"}]' \
  --upload-session '<SESSION_JSON>' \
  --json
```

Or pass via stdin:

```bash
node "<SKILL_ROOT>/scripts/capcut-upload.mjs" \
  --files '[{"client_id":"video-1","file":"<ABSOLUTE_VIDEO_PATH>"}]' \
  --upload-session-stdin \
  --json
```

4. For a single file:

```bash
node "<SKILL_ROOT>/scripts/capcut-upload.mjs" \
  --file "<ABSOLUTE_PATH>" \
  --client-id "media-1" \
  --upload-session '<SESSION_JSON>' \
  --json
```

## Interpret Results

- Batch success: `{"success":true,"results":[...]}`, exit code `0`.
- Partial/total failure: `{"success":false,"results":[...]}`, exit code `1`; preserve successful identifiers.
- A successful video requires upload success plus `setPublic.success:true`.
