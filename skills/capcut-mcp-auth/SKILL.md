---
name: capcut-mcp-auth
description: Guide for authenticating and troubleshooting the CapCut MCP servers. Explains how to configure the OAuth Bearer token for capcut_creation and manage the unauthenticated capcut_creation_resource endpoint.
---

# CapCut MCP Authentication

AI coding agents use the Model Context Protocol (MCP) to connect to CapCut's cloud editing and template services.

---

## Server Architecture

1. **`capcut_creation_resource`** (`https://www.capcut.com/api/external_mcp/resource`):
   - Identity-free and unauthenticated server.
   - Serves widget rendering, template cards preview, and public resource resolution.
   - Does not require login or OAuth tokens.

2. **`capcut_creation`** (`https://www.capcut.com/api/external_mcp`):
   - Authenticated server requiring an OAuth 2.0 Bearer token with scope `capcut:mcp`.
   - Serves AI Lab video editing (`capcut_ailab_*`), template search (`capcut_template_search`), and upload credentials (`capcut_asset_upload_credential`).

---

## How to Get Your CapCut Bearer Token in 30 Seconds

1. Open your browser and navigate to [capcut.com](https://www.capcut.com) (sign in to your account).
2. Open Developer Tools (`F12` or `Ctrl+Shift+I` on Windows, `Cmd+Option+I` on macOS) and click the **Network** tab.
3. Click into any project or workspace on CapCut.
4. Filter requests by `api` and click any request sent to `capcut.com/api/...`.
5. In the **Request Headers** section, find the `Authorization` header and copy the token value after `Bearer `.

---

## Configuring Authentication

### Method 1: In `mcp_config.json`
Update your client's MCP configuration with your Bearer token:

```json
{
  "mcpServers": {
    "capcut_creation": {
      "serverUrl": "https://www.capcut.com/api/external_mcp",
      "headers": {
        "Authorization": "Bearer <YOUR_CAPCUT_BEARER_TOKEN>"
      }
    },
    "capcut_creation_resource": {
      "serverUrl": "https://www.capcut.com/api/external_mcp/resource"
    }
  }
}
```

### Method 2: Via Antigravity CLI
Configure directly using the CLI:

```bash
agy mcp add --header "Authorization: Bearer <YOUR_CAPCUT_BEARER_TOKEN>" capcut_creation https://www.capcut.com/api/external_mcp
agy mcp add capcut_creation_resource https://www.capcut.com/api/external_mcp/resource
```

### Method 3: In Claude Desktop / Cursor / Windsurf
See ready-to-paste snippets in the `clients/` folder in this repository.

---

## Important Notices

- **Geographical Restrictions**: ByteDance / CapCut blocks requests originating from US IP addresses (`Currently unavailable to users with US IP addresses`). Route your connection through a non-US region (UK, Europe, Canada, or Asia) when connecting to CapCut APIs.
- **Token Security**: Keep your bearer token private. Never commit files containing raw tokens to GitHub or public repositories.
