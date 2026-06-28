# CodexGPT Bridge Usage

## Normal Chat

Use one conversation key for each Codex thread. CodexGPT Bridge will reuse the same ChatGPT web chat unless `start_new_chat` is true.

```json
{
  "prompt": "What is today's date?",
  "conversation_key": "project-thread-1",
  "browser": "chrome"
}
```

## Start A New Chat

```json
{
  "prompt": "Start a fresh review of this design.",
  "conversation_key": "project-thread-1",
  "browser": "chrome",
  "start_new_chat": true
}
```

## Upload Files

Always pass absolute file paths or user-relative paths.

```json
{
  "prompt": "Summarize this paper and list the main contributions.",
  "files": ["/Users/example/Downloads/paper.pdf"],
  "conversation_key": "paper-review",
  "browser": "safari"
}
```

Supported inputs depend on what ChatGPT web accepts in your account, but the bridge is designed for text, Markdown, JSON, code files, PDFs, and images.

## Returned Data

Successful runs return:

- `response_text`
- `response_html`
- `chat_url`
- `downloadable`
- `downloaded_files`
- `downloads_dir`
- `run_dir`

Downloaded files are copied into the run folder so Codex can reference them locally.

## Troubleshooting

Use `get_chatgpt_bridge_status` first. It reports state paths, browser automation status, and saved chat mappings.

Common issues:

- Browser is not logged into ChatGPT.
- macOS has not granted Accessibility or browser-control permission.
- Safari or Chrome has not enabled JavaScript from Apple Events.
- Ubuntu/Linux does not have Chrome or Chromium installed.
- ChatGPT changed its page selectors.

For Ubuntu/Linux, delete the bridge profile only if you want to reset login state:

```bash
rm -rf ~/.codex/state/codexgpt/chrome-linux-profile
```
