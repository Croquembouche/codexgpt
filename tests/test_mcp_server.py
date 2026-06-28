import tempfile
import unittest
from pathlib import Path

from codexgpt_bridge.mcp_protocol import MCPServer


class MCPServerTests(unittest.TestCase):
    def test_initialize_returns_server_info_and_tools_capability(self):
        server = MCPServer(state_root=Path(tempfile.mkdtemp()))

        response = server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            }
        )

        self.assertEqual(response["id"], 1)
        self.assertIn("tools", response["result"]["capabilities"])
        self.assertEqual(response["result"]["serverInfo"]["name"], "codexgpt")

    def test_tools_list_includes_send_status_and_reset(self):
        server = MCPServer(state_root=Path(tempfile.mkdtemp()))

        response = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})

        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertIn("send_to_chatgpt_web", names)
        self.assertIn("get_chatgpt_bridge_status", names)
        self.assertIn("reset_chat_mapping", names)
        send_tool = next(tool for tool in response["result"]["tools"] if tool["name"] == "send_to_chatgpt_web")
        self.assertEqual(send_tool["inputSchema"]["properties"]["browser"]["enum"], ["safari", "chrome"])

    def test_tools_call_dry_run_send_returns_content_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = MCPServer(state_root=Path(tmp))

            response = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "send_to_chatgpt_web",
                        "arguments": {
                            "prompt": "Review this",
                            "conversation_key": "thread-1",
                            "dry_run": True,
                        },
                    },
                }
            )

            self.assertEqual(response["id"], 3)
            self.assertIn("dry_run", response["result"]["content"][0]["text"])

    def test_tools_call_dry_run_send_accepts_chrome_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = MCPServer(state_root=Path(tmp))

            response = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "send_to_chatgpt_web",
                        "arguments": {
                            "prompt": "Review this",
                            "conversation_key": "thread-1",
                            "browser": "chrome",
                            "dry_run": True,
                        },
                    },
                }
            )

            self.assertEqual(response["id"], 5)
            self.assertIn('"browser": "chrome"', response["result"]["content"][0]["text"])

    def test_unknown_tool_returns_json_rpc_error(self):
        server = MCPServer(state_root=Path(tempfile.mkdtemp()))

        response = server.handle(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "not_a_tool", "arguments": {}},
            }
        )

        self.assertEqual(response["error"]["code"], -32602)
        self.assertIn("Unknown tool", response["error"]["message"])


if __name__ == "__main__":
    unittest.main()
