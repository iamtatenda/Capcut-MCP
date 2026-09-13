# CapCut Creation Resource MCP Instructions

Render safe CapCut cards from prepared tool results or persisted template-search snapshots, restore their read-only interaction state, and accept app-only card telemetry.

This server (`capcut_creation_resource`) does not accept OAuth account credentials or mutate account data.

For write and mutation operations (`capcut_ailab_start_edit`, `capcut_template_search`, `capcut_asset_upload_credential`), connect to the authenticated endpoint: `capcut_creation` (`https://www.capcut.com/api/external_mcp`).
