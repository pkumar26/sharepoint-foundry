# Web Chat Interface Implementation Plan

## Overview
Add a full-featured web chat interface to the SharePoint Foundry Agent with Entra ID (Azure AD) authentication and per-request search approach selection. The frontend will be vanilla HTML/CSS/JS served from the same FastAPI container (no separate frontend build step).

## Step 1: Add `search_approach` field to ChatRequest
- In `src/main.py`, add an optional `search_approach` field to `ChatRequest`:
  ```python
  search_approach: Optional[Literal["indexer", "foundryiq", "indexed_sharepoint"]] = None
  ```
- Update the `send_message` handler to use `request.search_approach or settings.search_approach` when selecting the search backend via the factory.

## Step 2: Add `GET /approaches` endpoint
- Return available search approaches and the server default:
  ```json
  {
    "approaches": ["indexer", "foundryiq", "indexed_sharepoint"],
    "default": "indexed_sharepoint"
  }
  ```

## Step 3: Create `static/` directory with full frontend SPA
### `static/index.html`
- Layout: sidebar (conversation history list), main chat area, top bar (approach selector dropdown, user info, logout button)
- Load MSAL.js 2.x from CDN (`https://alcdn.msauth.net/browser/2.38.0/js/msal-browser.min.js`)
- Load marked.js from CDN for Markdown rendering
- Link local CSS and JS files

### `static/css/styles.css`
- Responsive chat UI with flexbox layout
- Message bubbles (user vs assistant styling)
- Source citation cards (expandable, showing title, snippet, relevance score)
- Typing/thinking indicator animation
- Conversation sidebar with active state
- Dark/light theme support (CSS custom properties)
- Mobile-responsive breakpoints

### `static/js/auth.js`
- MSAL.js `PublicClientApplication` configuration:
  - `clientId`: fetched from `/auth/config`
  - `authority`: `https://login.microsoftonline.com/{tenant_id}`
  - `redirectUri`: `window.location.origin`
- `loginPopup()` with scope `api://806458c7-d269-46d6-90a5-3db2d1df16b4/access_as_user`
- `acquireTokenSilent()` with fallback to `acquireTokenPopup()`
- Export: `getAccessToken()`, `login()`, `logout()`, `getAccount()`

### `static/js/chat.js`
- `sendMessage(text, conversationId, searchApproach)` — POST to `/chat` with Bearer token
- Render assistant responses with Markdown (via marked.js)
- Display source references as expandable citation cards below the answer
- Show typing indicator while waiting for response
- Auto-scroll to latest message

### `static/js/conversations.js`
- Fetch conversation list from `GET /conversations` (with auth header)
- Render sidebar list with conversation titles/timestamps
- Load conversation history from `GET /conversations/{id}`
- "New Chat" button to start fresh conversation
- Highlight active conversation

### `static/js/app.js`
- Main entry point: initialize MSAL, check auth state
- If not authenticated → show login screen
- If authenticated → load UI, fetch approaches, fetch conversations
- Wire up event listeners (send button, Enter key, sidebar clicks, approach selector, logout)

## Step 4: Mount StaticFiles in FastAPI
- Add `StaticFiles` mount in `src/main.py`:
  ```python
  from fastapi.staticfiles import StaticFiles
  from fastapi.responses import FileResponse

  app.mount("/static", StaticFiles(directory="static"), name="static")
  ```
- Update root `GET /` to serve `index.html`:
  ```python
  @app.get("/")
  async def root():
      return FileResponse("static/index.html")
  ```

## Step 5: Add `aiofiles` dependency
- Add `aiofiles` to `pyproject.toml` dependencies (required by FastAPI's `StaticFiles`)
- Run `uv pip install -e ".[dev]"` to install

## Step 6: Add `GET /auth/config` endpoint
- Return public (non-secret) auth configuration for the frontend:
  ```json
  {
    "client_id": "806458c7-d269-46d6-90a5-3db2d1df16b4",
    "tenant_id": "cc4fb710-2bb6-4c47-ace3-a3c85b8fdf4c",
    "scopes": ["api://806458c7-d269-46d6-90a5-3db2d1df16b4/access_as_user"]
  }
  ```
- No secrets exposed — only what the SPA needs for MSAL configuration

## Step 7: Register SPA redirect URIs in Entra ID
- Add SPA platform redirect URIs to the app registration:
  - `http://localhost:8000` (local development)
  - `https://ca-spagent.wonderfulpebble-3a3db259.eastus2.azurecontainerapps.io` (production)
- Use Azure CLI:
  ```bash
  az ad app update --id 806458c7-d269-46d6-90a5-3db2d1df16b4 \
    --spa-redirect-uris "http://localhost:8000" "https://ca-spagent.wonderfulpebble-3a3db259.eastus2.azurecontainerapps.io"
  ```

## Step 8: Update Dockerfile
- Add `COPY static/ ./static/` after the source copy:
  ```dockerfile
  COPY src/ ./src/
  COPY static/ ./static/
  ```

## Step 9: Rebuild and redeploy
- Same Docker image — static files bundled in
- Rebuild ACR image and update Container App:
  ```bash
  az acr build --registry crspagentuor4ileqr5554 --image spagent:latest .
  az containerapp update -n ca-spagent -g rg-sharepoint-agent \
    --image crspagentuor4ileqr5554.azurecr.io/spagent:latest
  ```

## Step 10: Update README-AGENT.md
- Add "Web Interface" section documenting:
  - How to access the chat UI
  - Entra ID login flow
  - Approach selector usage
  - Local development instructions

## Verification Checkpoints
- After Steps 1-2: Run locally, test `POST /chat` with `search_approach` field and `GET /approaches`
- After Steps 3-6: Run locally, open `http://localhost:8000`, verify login popup, chat flow, citations, conversation sidebar
- After Step 7: Verify Entra login works from both localhost and Azure FQDN
- After Step 9: Verify production deployment at `https://ca-spagent.wonderfulpebble-3a3db259.eastus2.azurecontainerapps.io`
