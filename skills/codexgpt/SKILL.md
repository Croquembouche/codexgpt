---
name: codexgpt
description: Use when the user wants to send Codex context, text, Markdown, JSON, code files, PDFs, images, or other local files into ChatGPT web in Safari, Chrome, or Chromium and bring the visible ChatGPT result back into Codex.
---

# CodexGPT Bridge

Use this skill when the user asks to hand work from Codex to ChatGPT web, WebGPT, web ChatGPT, Safari/Chrome/Chromium ChatGPT, or a logged-in ChatGPT Pro browser session.

## Behavior

- Prefer `send_to_chatgpt_web` for actual handoffs.
- Omit `browser` for Safari, or pass `browser: "chrome"` for Google Chrome on macOS or Chrome/Chromium on Ubuntu/Linux.
- Use one ChatGPT web chat per Codex conversation key.
- If the user says to start a new ChatGPT chat, pass `start_new_chat: true`.
- If the user is only checking setup, pass `dry_run: true` first.
- Use `get_chatgpt_bridge_status` before troubleshooting.
- Use `reset_chat_mapping` only when the user wants to forget the saved ChatGPT chat for the current Codex conversation.

## Inputs

The bridge accepts:

- `prompt`: text to send to ChatGPT web.
- `files`: local file paths to upload.
- `conversation_key`: a stable key for the current Codex conversation.
- `browser`: `safari` or `chrome`; defaults to `safari`. On Ubuntu/Linux, `chrome` uses Chrome/Chromium through a local Chrome DevTools connection.
- `start_new_chat`: true when the user explicitly wants a fresh ChatGPT chat.
- `dry_run`: true when checking the handoff without controlling a browser.

## Limits

This is browser automation, not a web API. It cannot bypass login, CAPTCHA, rate limits, file-size limits, model limits, or UI changes. If the selected browser is logged out or ChatGPT changes its selectors, return the recovery message and ask the user to fix the visible browser state.

On Ubuntu/Linux, the first Chrome/Chromium run opens a dedicated bridge browser profile at `~/.codex/state/codexgpt/chrome-linux-profile`. The user must log into ChatGPT in that profile once; subsequent runs reuse it.

## Suggested Use

When invoking the tool, include the user goal, relevant context, and exact file paths. Ask ChatGPT web for a concrete output format when the result needs to come back cleanly, such as Markdown, JSON, or a short review checklist.
