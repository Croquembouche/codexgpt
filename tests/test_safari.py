import json
import os
import tempfile
import unittest
from pathlib import Path

from codexgpt_bridge.safari import (
    ChromeChatGPTClient,
    LinuxChromeChatGPTClient,
    SafariChatGPTClient,
    build_linux_chrome_profile_copy_dir,
    build_assert_chatgpt_page_javascript,
    build_choose_file_applescript,
    build_chrome_javascript_applescript,
    build_composer_plus_rect_javascript,
    build_extract_response_javascript,
    build_focus_composer_javascript,
    build_inject_file_javascript,
    build_open_file_picker_applescript,
    build_generation_state_javascript,
    build_linux_chrome_launch_args,
    build_open_chrome_chat_applescript,
    build_open_chat_applescript,
    build_paste_and_submit_applescript,
    build_prompt_javascript,
    classify_javascript_permission_error,
    prepare_linux_chrome_user_data_dir,
    normalize_browser_name,
    normalize_extracted_response,
)


class ImageOnlySafariClient(SafariChatGPTClient):
    def __init__(self):
        super().__init__(wait_interval_sec=0)
        self.calls = 0

    def extract_latest_response(self):
        self.calls += 1
        return {
            "url": "https://chatgpt.com/c/image",
            "title": "Image",
            "text": "",
            "html": "",
            "has_assistant": True,
            "downloadable": [],
            "images": [{"src": "blob:https://chatgpt.com/image", "alt": "cat"}],
            "has_visual_output": True,
        }

    def _is_generating(self):
        return False


class RecordingFileInjectionSafariClient(SafariChatGPTClient):
    file_upload_chunk_size = 8

    def __init__(self, expected_size):
        super().__init__(wait_interval_sec=0)
        self.expected_size = expected_size
        self.scripts = []
        self.upload_settle_sec = 0

    def _run_js(self, javascript, timeout=30):
        self.scripts.append(javascript)
        return json.dumps({"ok": True, "size": self.expected_size, "files": 1})


class RecordingLinuxChromeClient(LinuxChromeChatGPTClient):
    def __init__(self):
        super().__init__(wait_interval_sec=0)
        self.scripts = []

    def assert_chatgpt_page(self):
        return None

    def _run_js(self, javascript, timeout=30):
        self.scripts.append((javascript, timeout))
        return json.dumps({"ok": True, "url": "https://chatgpt.com/c/linux"})


class RecordingLinuxUploadClient(LinuxChromeChatGPTClient):
    def __init__(self):
        super().__init__(wait_interval_sec=0)
        self.upload_settle_sec = 0
        self.websocket = RecordingCdpWebSocket()

    def assert_chatgpt_page(self):
        return None

    def _open_cdp_websocket(self, timeout=30):
        self.websocket.timeout = timeout
        return self.websocket

    def _current_web_socket_url(self):
        return "ws://127.0.0.1/devtools/page/upload-test"


class RecordingCdpWebSocket:
    def __init__(self):
        self.timeout = None
        self.sessions = 0
        self.commands = []
        self._last_method = ""

    def __enter__(self):
        self.sessions += 1
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def send_json(self, payload):
        self.commands.append(payload)
        self._last_method = str(payload.get("method") or "")

    def recv_json(self, expected_id):
        if self._last_method == "DOM.getDocument":
            return {"id": expected_id, "result": {"root": {"nodeId": 1}}}
        if self._last_method == "DOM.querySelector":
            return {"id": expected_id, "result": {"nodeId": 42}}
        if self._last_method == "DOM.setFileInputFiles":
            return {"id": expected_id, "result": {}}
        return {"id": expected_id, "error": {"message": self._last_method}}


class FakeChromeHttpClient:
    def __init__(self, targets):
        self._targets = list(targets)
        self.new_pages = []

    def version(self):
        return {"Browser": "Chrome/test"}

    def targets(self):
        return list(self._targets)

    def new_page(self, url):
        target = {"url": url, "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/page/new"}
        self.new_pages.append(url)
        self._targets.append(target)
        return target


class ReusingLinuxChromeClient(LinuxChromeChatGPTClient):
    def __init__(self, targets):
        super().__init__(wait_interval_sec=0)
        self._http = FakeChromeHttpClient(targets)

    def _ensure_browser(self):
        return None

    def _wait_for_chatgpt_page(self):
        return None


class SafariScriptTests(unittest.TestCase):
    def test_prompt_javascript_json_encodes_prompt_content(self):
        prompt = 'Line 1\n"quoted" and backslash \\ content'

        script = build_prompt_javascript(prompt)

        self.assertIn(json.dumps(prompt), script)
        self.assertIn("prompt-textarea", script)
        self.assertIn("send-button", script)
        self.assertIn("async ()", script)
        self.assertIn("send-button_not_ready", script)
        self.assertIn("pointerdown", script)
        self.assertIn("button.click()", script)

    def test_open_chat_applescript_activates_safari_for_focused_mode(self):
        script = build_open_chat_applescript("https://chatgpt.com/")

        self.assertIn('tell application "Safari"', script)
        self.assertIn("activate", script)
        self.assertIn("make new document", script)

    def test_open_chrome_chat_applescript_activates_chrome_and_new_tab(self):
        script = build_open_chrome_chat_applescript("https://chatgpt.com/")

        self.assertIn('tell application "Google Chrome"', script)
        self.assertIn("activate", script)
        self.assertIn("make new tab", script)
        self.assertIn("active tab index", script)

    def test_chrome_javascript_applescript_executes_active_tab(self):
        script = build_chrome_javascript_applescript("'ok'")

        self.assertIn('tell application "Google Chrome"', script)
        self.assertIn("execute active tab of front window javascript", script)
        self.assertIn("'ok'", script)

    def test_chrome_client_uses_chrome_javascript_wrapper(self):
        client = ChromeChatGPTClient()

        script = client.build_javascript_applescript("'ok'")

        self.assertIn('tell application "Google Chrome"', script)
        self.assertIn("execute active tab", script)

    def test_browser_name_normalization_accepts_safari_and_chrome(self):
        self.assertEqual(normalize_browser_name(None), "safari")
        self.assertEqual(normalize_browser_name("Safari"), "safari")
        self.assertEqual(normalize_browser_name("google-chrome"), "chrome")
        self.assertEqual(normalize_browser_name("Chrome"), "chrome")
        self.assertEqual(normalize_browser_name("chromium"), "chrome")
        self.assertEqual(normalize_browser_name("chromium-browser"), "chrome")
        with self.assertRaises(ValueError):
            normalize_browser_name("firefox")

    def test_linux_chrome_launch_args_enable_remote_debugging_and_profile(self):
        args = build_linux_chrome_launch_args(
            executable="/usr/bin/chromium",
            port=9222,
            user_data_dir=Path("/tmp/chatgpt-bridge-profile"),
            profile_directory="Profile 1",
            initial_url="https://chatgpt.com/",
        )

        self.assertEqual(args[0], "/usr/bin/chromium")
        self.assertIn("--remote-debugging-port=9222", args)
        self.assertIn("--user-data-dir=/tmp/chatgpt-bridge-profile", args)
        self.assertIn("--profile-directory=Profile 1", args)
        self.assertIn("--no-first-run", args)
        self.assertNotIn("--new-window", args)
        self.assertEqual(args[-1], "https://chatgpt.com/")

    def test_linux_profile_copy_dir_is_stable_and_port_specific(self):
        source = Path("/home/test/.config/google-chrome")
        copy_root = Path("/tmp/codexgpt-profile-copies")

        first = build_linux_chrome_profile_copy_dir(source, "Profile 1", 9223, copy_root=copy_root)
        second = build_linux_chrome_profile_copy_dir(source, "Profile 1", 9223, copy_root=copy_root)
        different_port = build_linux_chrome_profile_copy_dir(source, "Profile 1", 9224, copy_root=copy_root)

        self.assertEqual(first, second)
        self.assertNotEqual(first, different_port)
        self.assertEqual(first.parent, copy_root)
        self.assertIn("Profile-1", first.name)

    def test_prepare_linux_chrome_user_data_dir_copies_explicit_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            target = root / "target"
            profile = source / "Profile 1"
            profile.mkdir(parents=True)
            (source / "Local State").write_text("{}", encoding="utf-8")
            (source / "SingletonLock").write_text("lock", encoding="utf-8")
            (source / "DevToolsActivePort").write_text("9223", encoding="utf-8")
            (profile / "Preferences").write_text("prefs", encoding="utf-8")

            old_value = os.environ.get("CODEXGPT_CHROME_SOURCE_USER_DATA_DIR")
            os.environ["CODEXGPT_CHROME_SOURCE_USER_DATA_DIR"] = str(source)
            try:
                resolved = prepare_linux_chrome_user_data_dir(target, "Profile 1", 9223)
            finally:
                if old_value is None:
                    os.environ.pop("CODEXGPT_CHROME_SOURCE_USER_DATA_DIR", None)
                else:
                    os.environ["CODEXGPT_CHROME_SOURCE_USER_DATA_DIR"] = old_value

            self.assertEqual(resolved, target)
            self.assertEqual((target / "Local State").read_text(encoding="utf-8"), "{}")
            self.assertEqual((target / "Profile 1" / "Preferences").read_text(encoding="utf-8"), "prefs")
            self.assertFalse((target / "SingletonLock").exists())
            self.assertFalse((target / "DevToolsActivePort").exists())

    def test_linux_chrome_client_submits_prompt_with_javascript(self):
        client = RecordingLinuxChromeClient()

        client.submit_prompt("Hello from Ubuntu")

        self.assertEqual(len(client.scripts), 1)
        self.assertIn("Hello from Ubuntu", client.scripts[0][0])
        self.assertIn("send-button", client.scripts[0][0])
        self.assertEqual(client.scripts[0][1], 75)

    def test_linux_chrome_upload_uses_devtools_file_input_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.txt"
            second = Path(tmp) / "second.json"
            first.write_text("one", encoding="utf-8")
            second.write_text("{}", encoding="utf-8")
            client = RecordingLinuxUploadClient()

            uploaded = client.upload_files([str(first), str(second)])

        self.assertEqual(uploaded, [str(first.resolve()), str(second.resolve())])
        self.assertEqual(client.websocket.sessions, 1)
        self.assertEqual([command["method"] for command in client.websocket.commands], [
            "DOM.getDocument",
            "DOM.querySelector",
            "DOM.setFileInputFiles",
        ])
        self.assertEqual(client.websocket.commands[-1]["params"]["files"], uploaded)

    def test_linux_open_chat_reuses_existing_chatgpt_target(self):
        existing = {
            "url": "https://chatgpt.com/c/existing",
            "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/page/existing",
        }
        client = ReusingLinuxChromeClient([existing])

        target_url = client.open_chat("https://chatgpt.com/c/existing", start_new_chat=False)

        self.assertEqual(target_url, "https://chatgpt.com/c/existing")
        self.assertEqual(client._target, existing)
        self.assertEqual(client._http.new_pages, [])

    def test_linux_open_chat_starts_new_chat_when_requested(self):
        existing = {
            "url": "https://chatgpt.com/c/existing",
            "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/page/existing",
        }
        client = ReusingLinuxChromeClient([existing])

        target_url = client.open_chat(None, start_new_chat=True)

        self.assertEqual(target_url, "https://chatgpt.com/")
        self.assertEqual(client._http.new_pages, ["https://chatgpt.com/"])

    def test_focus_composer_javascript_targets_prompt_editor(self):
        script = build_focus_composer_javascript()

        self.assertIn("prompt-textarea", script)
        self.assertIn("composer.focus", script)

    def test_paste_and_submit_applescript_uses_clipboard_and_return(self):
        script = build_paste_and_submit_applescript()

        self.assertIn('keystroke "v" using {command down}', script)
        self.assertIn("key code 36", script)

    def test_composer_plus_rect_javascript_returns_screen_coordinates(self):
        script = build_composer_plus_rect_javascript()

        self.assertIn("composer-plus-btn", script)
        self.assertIn("window.screenX", script)
        self.assertIn("outerHeight", script)
        self.assertIn("innerHeight", script)

    def test_open_file_picker_applescript_clicks_plus_and_accepts_menu_item(self):
        script = build_open_file_picker_applescript(722, 907)

        self.assertIn("click at {722, 907}", script)
        self.assertIn("click at {760, 461}", script)

    def test_choose_file_applescript_uses_go_to_path_and_clipboard_paste(self):
        script = build_choose_file_applescript()

        self.assertIn('keystroke "g" using {command down, shift down}', script)
        self.assertIn('keystroke "a" using {command down}', script)
        self.assertIn('keystroke "v" using {command down}', script)

    def test_inject_file_javascript_assigns_file_to_upload_input(self):
        script = build_inject_file_javascript("brief.md", "text/markdown", "SGVsbG8=")

        self.assertIn("upload-files", script)
        self.assertIn("DataTransfer", script)
        self.assertIn("new File", script)
        self.assertIn(json.dumps("brief.md"), script)
        self.assertIn(json.dumps("text/markdown"), script)
        self.assertIn("dispatchEvent(new Event('change'", script)

    def test_inject_file_sends_large_content_in_small_chunks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paper.pdf"
            path.write_bytes(b"%PDF-" + (b"large-pdf-content" * 5))
            client = RecordingFileInjectionSafariClient(path.stat().st_size)

            client._inject_file(path)

        append_scripts = [script for script in client.scripts if ".chunks.push" in script]
        self.assertGreater(len(append_scripts), 1)
        self.assertTrue(all(len(script) < 2000 for script in append_scripts))
        self.assertIn(json.dumps("paper.pdf"), client.scripts[-1])
        self.assertIn(json.dumps("application/pdf"), client.scripts[-1])

    def test_extract_response_javascript_targets_assistant_messages(self):
        script = build_extract_response_javascript()

        self.assertIn('data-message-author-role="assistant"', script)
        self.assertIn("innerText", script)
        self.assertIn("hasVisualOutput", script)
        self.assertIn("querySelectorAll('img')", script)
        self.assertIn("hasAssistant: !!last", script)
        self.assertIn("scope.querySelectorAll('a[download]", script)
        self.assertIn("scope.querySelectorAll('button')", script)
        self.assertIn("/download/i.test(label)", script)
        self.assertNotIn("hasAssistant: !!last || hasVisualOutput", script)
        self.assertNotIn("document.body;", script)

    def test_assert_chatgpt_page_javascript_requires_chatgpt_host(self):
        script = build_assert_chatgpt_page_javascript()

        self.assertIn("chatgpt.com", script)
        self.assertIn("location.hostname", script)

    def test_generation_state_javascript_detects_finalizing_and_stop(self):
        script = build_generation_state_javascript()

        self.assertIn("Finalizing answer", script)
        self.assertIn("stop-button", script)

    def test_normalize_extracted_response_parses_json_payload(self):
        raw = json.dumps(
            {
                "url": "https://chatgpt.com/c/abc",
                "title": "ChatGPT",
                "text": "Finished response",
                "html": "<p>Finished response</p>",
            }
        )

        normalized = normalize_extracted_response(raw)

        self.assertEqual(normalized["url"], "https://chatgpt.com/c/abc")
        self.assertEqual(normalized["text"], "Finished response")

    def test_normalize_extracted_response_preserves_visual_outputs(self):
        raw = json.dumps(
            {
                "url": "https://chatgpt.com/c/image",
                "title": "Image",
                "text": "",
                "html": "",
                "hasAssistant": True,
                "hasVisualOutput": True,
                "images": [{"src": "blob:https://chatgpt.com/image", "alt": "cat"}],
            }
        )

        normalized = normalize_extracted_response(raw)

        self.assertTrue(normalized["has_visual_output"])
        self.assertEqual(normalized["images"][0]["alt"], "cat")

    def test_wait_for_response_accepts_image_only_assistant_output(self):
        client = ImageOnlySafariClient()

        response = client.wait_for_response(timeout_sec=1)

        self.assertTrue(response["has_visual_output"])
        self.assertGreaterEqual(client.calls, 2)

    def test_classifies_disabled_javascript_from_apple_events(self):
        message = "You must enable 'Allow JavaScript from Apple Events' in the Developer section"

        self.assertEqual(classify_javascript_permission_error(message), "disabled")
        self.assertEqual(classify_javascript_permission_error("other error"), "unknown")


if __name__ == "__main__":
    unittest.main()
