# CodexGPT Bridge

CodexGPT Bridge lets Codex use your logged-in ChatGPT web session. It sends prompts and local files from Codex into ChatGPT in a real browser, then brings the visible response and downloaded artifacts back into Codex.

This is useful when you want ChatGPT web features such as your logged-in account, browser-side file upload, generated images, or rich document review without switching back and forth manually.

CodexGPT Bridge is community tooling and is not an official OpenAI product.

## Install

Add this repository as a Codex plugin marketplace, then install the plugin:

```bash
codex plugin marketplace add Croquembouche/codexgpt
codex plugin add codexgpt@codexgpt
```

Start a new Codex thread after installing so the plugin tools load.

## First-Time Browser Setup

You need to be logged into ChatGPT in the browser CodexGPT Bridge will control.

### macOS Safari

1. Log into ChatGPT in Safari.
2. Turn on `Develop > Allow JavaScript from Apple Events`.
3. Allow Codex or your terminal to control Safari if macOS asks.

Use Safari by default, or ask Codex to use:

```json
{"browser": "safari"}
```

### macOS Chrome

1. Log into ChatGPT in Chrome.
2. Turn on `View > Developer > Allow JavaScript from Apple Events`.
3. Allow Codex or your terminal to control Chrome if macOS asks.

Ask Codex to use:

```json
{"browser": "chrome"}
```

### Ubuntu/Linux Chrome or Chromium

Install Chrome or Chromium, then ask Codex to use:

```json
{"browser": "chrome"}
```

The first run opens a dedicated CodexGPT browser profile. Log into ChatGPT in that window once. Later runs reuse the same profile.

## How To Use It

After installation, ask Codex naturally:

```text
Use CodexGPT Bridge to ask ChatGPT web to summarize this PDF.
```

Or:

```text
Send this draft to ChatGPT web in Chrome and bring the full answer back here.
```

CodexGPT Bridge can send:

- text prompts
- Markdown
- JSON
- code files
- PDFs
- images

It can bring back:

- ChatGPT's visible text response
- response HTML
- generated/downloaded files copied into a local run folder
- the ChatGPT chat URL for continuity

By default, CodexGPT Bridge keeps using the same ChatGPT web chat for the same Codex conversation. Ask for a new chat when you want a fresh ChatGPT thread.

## More Documentation

- [Usage guide](docs/USAGE.md)
- [Detailed plugin reference](docs/PLUGIN_REFERENCE.md)

## Troubleshooting

If something does not work, ask Codex to run `get_chatgpt_bridge_status`.

Most issues are one of these:

- the browser is not logged into ChatGPT
- macOS browser automation permission has not been allowed
- Safari or Chrome has not enabled JavaScript from Apple Events
- Ubuntu/Linux does not have Chrome or Chromium installed
- ChatGPT changed its web UI

CodexGPT Bridge cannot bypass login, CAPTCHA, file-size limits, model limits, or account checks.

## Development

Run tests from the repo root:

```bash
PYTHONPATH=. python3 -m unittest discover tests -v
python3 -m compileall -q codexgpt_bridge mcp tests
```
