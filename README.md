# CodexGPT Bridge

CodexGPT Bridge is a Codex plugin that sends prompts and local files from Codex to your logged-in ChatGPT web session, then brings the visible response and downloaded artifacts back into Codex.

It is browser automation, not an API wrapper. It uses the ChatGPT web UI you are already logged into.

CodexGPT Bridge is community tooling and is not an official OpenAI product.

## What It Does

- Keeps one ChatGPT web chat per Codex conversation key.
- Starts a new ChatGPT chat when `start_new_chat` is true.
- Supports Safari and Chrome on macOS.
- Supports Chrome and Chromium on Ubuntu/Linux.
- Uploads local files such as PDFs, images, Markdown, JSON, and code files.
- Returns visible response text, response HTML, download links, and copied local artifact paths.
- Stores run history under `~/.codex/state/codexgpt/runs/`.

## Install

Add this GitHub repo as a Codex plugin marketplace:

```bash
codex plugin marketplace add Croquembouche/codexgpt
codex plugin add codexgpt@codexgpt
```

After installing or updating, start a new Codex thread so the plugin tools are loaded.

For local development from a clone:

```bash
git clone https://github.com/Croquembouche/codexgpt.git
cd codexgpt
codex plugin marketplace add "$PWD"
codex plugin add codexgpt@codexgpt
```

## Browser Setup

### macOS Safari

1. Log into ChatGPT in Safari.
2. Enable Safari's `Develop` menu if needed.
3. Turn on `Develop > Allow JavaScript from Apple Events`.
4. Allow Codex or your terminal to control Safari when macOS asks.

Use the default browser option or pass:

```json
{"browser": "safari"}
```

### macOS Chrome

1. Log into ChatGPT in Chrome.
2. Turn on `View > Developer > Allow JavaScript from Apple Events`.
3. Allow Codex or your terminal to control Chrome when macOS asks.

Pass:

```json
{"browser": "chrome"}
```

If Chrome's menu toggle does not stick, close Chrome and set its internal preference before reopening:

```bash
defaults write com.google.Chrome browser.allow_javascript_apple_events -bool true
```

### Ubuntu/Linux Chrome or Chromium

Install Chrome or Chromium, then pass:

```json
{"browser": "chrome"}
```

The first live run opens a dedicated bridge profile at:

```text
~/.codex/state/codexgpt/chrome-linux-profile
```

Log into ChatGPT in that browser window once. Later runs reuse the same profile.

Optional Linux environment variables:

```bash
export CODEXGPT_CHROME_BINARY=/usr/bin/chromium
export CODEXGPT_CHROME_USER_DATA_DIR="$HOME/.codex/state/codexgpt/chrome-linux-profile"
export CODEXGPT_CHROME_CDP_HOST=127.0.0.1
export CODEXGPT_CHROME_CDP_PORT=9222
```

## Tools

CodexGPT Bridge exposes three MCP tools:

- `send_to_chatgpt_web`
- `get_chatgpt_bridge_status`
- `reset_chat_mapping`

## Example

Ask Codex:

```text
Use CodexGPT Bridge to ask ChatGPT web: summarize this PDF.
```

With a direct tool call, the core arguments look like this:

```json
{
  "prompt": "Summarize this PDF in five bullets.",
  "files": ["/absolute/path/to/paper.pdf"],
  "conversation_key": "my-codex-thread",
  "browser": "chrome",
  "start_new_chat": false,
  "wait_timeout_sec": 180
}
```

## Limits

CodexGPT Bridge cannot bypass:

- ChatGPT login
- CAPTCHA or account checks
- browser permission prompts
- file-size limits
- model limits
- ChatGPT UI changes

If the selected browser is logged out or ChatGPT changes its page structure, the bridge returns a recovery message instead of silently guessing.

## Development

Run tests from the repo root:

```bash
PYTHONPATH=. python3 -m unittest discover tests -v
python3 -m compileall -q codexgpt_bridge mcp tests
```
