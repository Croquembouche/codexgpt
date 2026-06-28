# CodexGPT Bridge

CodexGPT Bridge is a local Codex plugin that sends prompts and local files to the logged-in ChatGPT web UI in Safari, Chrome, or Chromium, then returns visible response text and local artifact paths back to Codex.

## What It Does

- Keeps one ChatGPT web chat per Codex conversation key.
- Starts a new ChatGPT chat when `start_new_chat` is true.
- Uses Safari by default; pass `browser: "chrome"` to use Google Chrome on macOS or Chrome/Chromium on Ubuntu/Linux.
- Accepts text prompts plus local file paths for PDFs, images, Markdown, JSON, and code files.
- Stores each run under `~/.codex/state/codexgpt/runs/`.
- Provides a dry-run mode for safe plumbing checks without controlling a browser.

## Tools

- `send_to_chatgpt_web`
- `get_chatgpt_bridge_status`
- `reset_chat_mapping`

## Browser Setup

The live browser path needs:

- The selected browser logged into ChatGPT.
- On macOS: Accessibility permission for the process running the MCP server.
- On macOS Safari/Chrome: the selected browser's `Allow JavaScript from Apple Events` setting enabled.
- On Ubuntu/Linux: Chrome or Chromium installed. The bridge uses a dedicated Chrome/Chromium profile at `~/.codex/state/codexgpt/chrome-linux-profile` and controls it through a local Chrome DevTools connection.

For Ubuntu/Linux, pass `browser: "chrome"`. The first live run opens the bridge profile; log into ChatGPT in that window once, and later runs reuse that profile.

Optional Ubuntu/Linux environment variables:

- `CODEXGPT_CHROME_BINARY`: path or command for Chrome/Chromium.
- `CODEXGPT_CHROME_USER_DATA_DIR`: custom bridge browser profile directory.
- `CODEXGPT_CHROME_CDP_HOST`: Chrome DevTools host, default `127.0.0.1`.
- `CODEXGPT_CHROME_CDP_PORT`: Chrome DevTools port, default `9222`.

If ChatGPT changes its web UI, the bridge will return a recovery message instead of silently guessing.

## Install From A Local Clone

The repository includes a local marketplace at `.agents/plugins/marketplace.json`, so a clone can be used as a Codex plugin marketplace.

```bash
git clone https://github.com/Croquembouche/codexgpt.git
cd codexgpt
codex plugin marketplace add "$PWD"
codex plugin add codexgpt@codexgpt
```

After installing or updating, start a new Codex thread so the new MCP tools are loaded.

## Development

Run tests from the repo root:

```bash
PYTHONPATH=. python3 -m unittest discover tests -v
python3 -m compileall -q codexgpt_bridge mcp tests
```
