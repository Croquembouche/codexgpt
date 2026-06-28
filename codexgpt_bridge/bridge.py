import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .downloads import snapshot_downloads
from .files import build_file_manifest
from .safari import (
    ChromeChatGPTClient,
    LinuxChromeChatGPTClient,
    MacOSFocusManager,
    SafariChatGPTClient,
    check_chrome_javascript_from_apple_events,
    check_javascript_from_apple_events,
    check_linux_chrome_cdp,
    normalize_browser_name,
)
from .state import BridgeState


def create_default_chrome_client(platform_name: Optional[str] = None):
    platform_value = platform_name or sys.platform
    if platform_value.startswith("linux"):
        return LinuxChromeChatGPTClient()
    return ChromeChatGPTClient()


class ChatGPTBridge:
    def __init__(
        self,
        state_root: Optional[Path] = None,
        safari_client: Optional[SafariChatGPTClient] = None,
        chrome_client: Optional[ChromeChatGPTClient] = None,
        focus_manager: Optional[MacOSFocusManager] = None,
        platform_name: Optional[str] = None,
    ):
        self.platform_name = platform_name or sys.platform
        self.state = BridgeState(state_root)
        self.safari_client = safari_client or SafariChatGPTClient()
        self.chrome_client = chrome_client or create_default_chrome_client(self.platform_name)
        self.focus_manager = focus_manager or MacOSFocusManager()

    def status(self, conversation_key: Optional[str] = None) -> Dict[str, Any]:
        status: Dict[str, Any] = {
            "state_root": str(self.state.root),
            "state_path": str(self.state.state_path),
            "runs_root": str(self.state.runs_root),
            "platform": self.platform_name,
            "osascript_available": shutil.which("osascript") is not None,
            "safari_javascript_from_apple_events": check_javascript_from_apple_events(),
            "chrome_javascript_from_apple_events": check_chrome_javascript_from_apple_events(),
            "linux_chrome_cdp": check_linux_chrome_cdp(),
            "mappings": self.state.list_mappings(),
        }
        if conversation_key:
            status["conversation_key"] = conversation_key
            status["chat_url"] = self.state.get_chat_url(conversation_key)
        return status

    def reset_chat_mapping(self, conversation_key: str) -> Dict[str, Any]:
        removed = self.state.reset_chat_url(conversation_key)
        return {"conversation_key": conversation_key, "removed": removed}

    def send_to_chatgpt_web(
        self,
        prompt: str,
        files: Optional[Iterable[str]] = None,
        conversation_key: str = "default",
        start_new_chat: bool = False,
        wait_timeout_sec: int = 180,
        dry_run: bool = False,
        browser: Optional[str] = None,
    ) -> Dict[str, Any]:
        browser_name = normalize_browser_name(browser)
        browser_client = self._client_for_browser(browser_name)
        file_list = [str(Path(path).expanduser()) for path in (files or [])]
        manifest = build_file_manifest(file_list)
        run = self.state.create_run(conversation_key, prompt, [item["path"] for item in manifest])
        existing_url = self.state.get_chat_url(conversation_key)
        would_start_new_chat = start_new_chat or existing_url is None

        if dry_run:
            result = {
                "status": "dry_run",
                "browser": browser_name,
                "conversation_key": conversation_key,
                "run_dir": str(run.run_dir),
                "target_chat_url": None if would_start_new_chat else existing_url,
                "would_start_new_chat": would_start_new_chat,
                "files": manifest,
                "prompt_preview": prompt[:500],
            }
            self.state.write_result(run, result)
            return result

        previous_app = self.focus_manager.capture_frontmost_app()
        try:
            before_downloads = snapshot_downloads()
            target_url = browser_client.open_chat(existing_url, would_start_new_chat)
            if manifest:
                browser_client.upload_files([str(item["path"]) for item in manifest])
            browser_client.submit_prompt(prompt)
            response = browser_client.wait_for_response(timeout_sec=wait_timeout_sec)
            downloaded_files = browser_client.collect_downloaded_files(before_downloads, run.downloads_dir)
            chat_url = str(response.get("url") or target_url)
            if chat_url.startswith("https://chatgpt.com/"):
                self.state.set_chat_url(conversation_key, chat_url)
            result = {
                "status": "completed",
                "browser": browser_name,
                "conversation_key": conversation_key,
                "run_dir": str(run.run_dir),
                "chat_url": chat_url,
                "response_text": response.get("text", ""),
                "response_html": response.get("html", ""),
                "downloadable": response.get("downloadable", []),
                "downloads_dir": str(run.downloads_dir),
                "downloaded_files": downloaded_files,
                "files": manifest,
            }
        except Exception as exc:
            result = {
                "status": "error",
                "browser": browser_name,
                "conversation_key": conversation_key,
                "run_dir": str(run.run_dir),
                "error": str(exc),
                "recovery": (
                    "Check that the selected browser is logged into ChatGPT and automation is enabled. "
                    "On macOS, allow Accessibility and JavaScript from Apple Events. On Ubuntu/Linux, "
                    "install Chrome or Chromium and keep the bridge-launched Chrome profile logged into ChatGPT."
                ),
            }
            self.state.write_result(run, result)
            raise
        finally:
            self.focus_manager.restore_app(previous_app)

        self.state.write_result(run, result)
        return result

    def _client_for_browser(self, browser_name: str):
        if browser_name == "chrome":
            return self.chrome_client
        return self.safari_client


def result_to_text(result: Dict[str, Any]) -> str:
    return json.dumps(result, indent=2, sort_keys=True)
