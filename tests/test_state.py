import json
import tempfile
import unittest
from pathlib import Path

from codexgpt_bridge.state import BridgeState


class BridgeStateTests(unittest.TestCase):
    def test_chat_mapping_round_trips_by_conversation_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = BridgeState(Path(tmp))

            state.set_chat_url("codex-thread-1", "https://chatgpt.com/c/abc123")

            self.assertEqual(
                state.get_chat_url("codex-thread-1"),
                "https://chatgpt.com/c/abc123",
            )
            payload = json.loads((Path(tmp) / "state.json").read_text())
            self.assertIn("codex-thread-1", payload["chat_mappings"])

    def test_reset_chat_mapping_removes_only_requested_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = BridgeState(Path(tmp))
            state.set_chat_url("thread-a", "https://chatgpt.com/c/a")
            state.set_chat_url("thread-b", "https://chatgpt.com/c/b")

            removed = state.reset_chat_url("thread-a")

            self.assertTrue(removed)
            self.assertIsNone(state.get_chat_url("thread-a"))
            self.assertEqual(state.get_chat_url("thread-b"), "https://chatgpt.com/c/b")

    def test_create_run_folder_is_unique_and_writes_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = BridgeState(Path(tmp))

            first = state.create_run("thread-a", "Please review", ["a.pdf"])
            second = state.create_run("thread-a", "Please review", ["a.pdf"])

            self.assertNotEqual(first.run_dir, second.run_dir)
            self.assertTrue((first.run_dir / "request.json").exists())
            self.assertEqual(first.downloads_dir.name, "downloads")


if __name__ == "__main__":
    unittest.main()
