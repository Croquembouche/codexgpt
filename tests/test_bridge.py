import tempfile
import unittest
from pathlib import Path

from codexgpt_bridge.bridge import ChatGPTBridge
from codexgpt_bridge.safari import LinuxChromeChatGPTClient


class FakeSafariClient:
    def __init__(self, fail_at=None):
        self.fail_at = fail_at

    def open_chat(self, chat_url, start_new_chat):
        if self.fail_at == "open_chat":
            raise RuntimeError("open failed")
        return "https://chatgpt.com/"

    def upload_files(self, files):
        if self.fail_at == "upload_files":
            raise RuntimeError("upload failed")
        return list(files)

    def submit_prompt(self, prompt):
        if self.fail_at == "submit_prompt":
            raise RuntimeError("submit failed")

    def wait_for_response(self, timeout_sec=180):
        if self.fail_at == "wait_for_response":
            raise RuntimeError("wait failed")
        return {
            "url": "https://chatgpt.com/c/fake",
            "text": "Done",
            "html": "<p>Done</p>",
            "downloadable": [],
        }

    def collect_downloaded_files(self, before, destination):
        if self.fail_at == "collect_downloaded_files":
            raise RuntimeError("download failed")
        return []


class NamedFakeClient(FakeSafariClient):
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.opened = []

    def open_chat(self, chat_url, start_new_chat):
        self.opened.append((chat_url, start_new_chat))
        return f"https://chatgpt.com/c/{self.name}"


class FakeFocusManager:
    def __init__(self):
        self.captured = []
        self.restored = []

    def capture_frontmost_app(self):
        self.captured.append(True)
        return "Codex"

    def restore_app(self, app_name):
        self.restored.append(app_name)


class ChatGPTBridgeTests(unittest.TestCase):
    def test_dry_run_creates_plan_without_running_safari(self):
        with tempfile.TemporaryDirectory() as tmp:
            bridge = ChatGPTBridge(state_root=Path(tmp))

            result = bridge.send_to_chatgpt_web(
                prompt="Summarize this file.",
                files=[],
                conversation_key="codex-thread-1",
                dry_run=True,
            )

            self.assertEqual(result["status"], "dry_run")
            self.assertEqual(result["conversation_key"], "codex-thread-1")
            self.assertTrue(result["would_start_new_chat"])
            self.assertIn("run_dir", result)
            self.assertTrue((Path(result["run_dir"]) / "request.json").exists())

    def test_existing_mapping_is_reused_unless_start_new_chat_is_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            bridge = ChatGPTBridge(state_root=Path(tmp))
            bridge.state.set_chat_url("codex-thread-1", "https://chatgpt.com/c/existing")

            result = bridge.send_to_chatgpt_web(
                prompt="Continue the review.",
                files=[],
                conversation_key="codex-thread-1",
                dry_run=True,
            )

            self.assertFalse(result["would_start_new_chat"])
            self.assertEqual(result["target_chat_url"], "https://chatgpt.com/c/existing")

            fresh = bridge.send_to_chatgpt_web(
                prompt="Fresh review please.",
                files=[],
                conversation_key="codex-thread-1",
                start_new_chat=True,
                dry_run=True,
            )

            self.assertTrue(fresh["would_start_new_chat"])
            self.assertIsNone(fresh["target_chat_url"])

    def test_missing_file_is_reported_before_browser_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            bridge = ChatGPTBridge(state_root=Path(tmp))

            with self.assertRaises(FileNotFoundError):
                bridge.send_to_chatgpt_web(
                    prompt="Review",
                    files=[str(Path(tmp) / "missing.pdf")],
                    conversation_key="codex-thread-1",
                    dry_run=True,
                )

    def test_live_send_restores_previously_focused_app_on_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            focus = FakeFocusManager()
            bridge = ChatGPTBridge(
                state_root=Path(tmp),
                safari_client=FakeSafariClient(),
                focus_manager=focus,
            )

            result = bridge.send_to_chatgpt_web(
                prompt="Review",
                files=[],
                conversation_key="codex-thread-1",
                dry_run=False,
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(focus.captured, [True])
            self.assertEqual(focus.restored, ["Codex"])

    def test_live_send_restores_previously_focused_app_on_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            focus = FakeFocusManager()
            bridge = ChatGPTBridge(
                state_root=Path(tmp),
                safari_client=FakeSafariClient(fail_at="wait_for_response"),
                focus_manager=focus,
            )

            with self.assertRaises(RuntimeError):
                bridge.send_to_chatgpt_web(
                    prompt="Review",
                    files=[],
                    conversation_key="codex-thread-1",
                    dry_run=False,
                )

            self.assertEqual(focus.captured, [True])
            self.assertEqual(focus.restored, ["Codex"])

    def test_dry_run_records_requested_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            bridge = ChatGPTBridge(state_root=Path(tmp))

            result = bridge.send_to_chatgpt_web(
                prompt="Review",
                files=[],
                conversation_key="codex-thread-1",
                browser="chrome",
                dry_run=True,
            )

            self.assertEqual(result["browser"], "chrome")

    def test_live_send_uses_chrome_client_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            safari = NamedFakeClient("safari")
            chrome = NamedFakeClient("chrome")
            bridge = ChatGPTBridge(
                state_root=Path(tmp),
                safari_client=safari,
                chrome_client=chrome,
                focus_manager=FakeFocusManager(),
            )

            result = bridge.send_to_chatgpt_web(
                prompt="Review",
                files=[],
                conversation_key="codex-thread-1",
                browser="chrome",
                dry_run=False,
            )

            self.assertEqual(result["browser"], "chrome")
            self.assertEqual(chrome.opened, [(None, True)])
            self.assertEqual(safari.opened, [])

    def test_linux_platform_uses_cdp_chrome_client_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            bridge = ChatGPTBridge(state_root=Path(tmp), platform_name="linux")

            self.assertIsInstance(bridge.chrome_client, LinuxChromeChatGPTClient)


if __name__ == "__main__":
    unittest.main()
