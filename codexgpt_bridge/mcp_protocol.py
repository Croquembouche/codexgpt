import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .bridge import ChatGPTBridge, result_to_text


PROTOCOL_VERSION = "2025-06-18"


class JsonRpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class MCPServer:
    def __init__(self, state_root: Optional[Path] = None):
        self.bridge = ChatGPTBridge(state_root=state_root)

    def handle(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if "id" not in message:
            return None
        request_id = message.get("id")
        try:
            result = self._dispatch(message.get("method"), message.get("params") or {})
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except JsonRpcError as exc:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": exc.code, "message": exc.message},
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32603, "message": str(exc)},
            }

    def _dispatch(self, method: Optional[str], params: Dict[str, Any]) -> Dict[str, Any]:
        if method == "initialize":
            return {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "codexgpt", "version": "0.0.0"},
                "instructions": (
                    "Use these tools to hand prompts and local files to ChatGPT web in Safari, "
                    "macOS Chrome, or Ubuntu/Linux Chrome/Chromium."
                ),
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": self._tools()}
        if method == "tools/call":
            return self._call_tool(params)
        raise JsonRpcError(-32601, f"Method not found: {method}")

    def _tools(self) -> Iterable[Dict[str, Any]]:
        return [
            {
                "name": "send_to_chatgpt_web",
                "description": (
                    "Send a prompt and optional local files to ChatGPT web in Safari, Chrome, or Chromium. "
                    "Reuses the mapped ChatGPT chat for the conversation unless start_new_chat is true."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "Prompt to submit to ChatGPT web."},
                        "files": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Absolute or user-relative local file paths to upload.",
                            "default": [],
                        },
                        "conversation_key": {
                            "type": "string",
                            "description": "Stable key for this Codex conversation.",
                            "default": "default",
                        },
                        "browser": {
                            "type": "string",
                            "description": "Browser to control for ChatGPT web. Use chrome for Chrome or Chromium on Ubuntu/Linux.",
                            "enum": ["safari", "chrome"],
                            "default": "safari",
                        },
                        "start_new_chat": {
                            "type": "boolean",
                            "description": "Create a fresh ChatGPT chat for this conversation.",
                            "default": False,
                        },
                        "wait_timeout_sec": {
                            "type": "integer",
                            "description": "Maximum time to wait for the visible ChatGPT response.",
                            "default": 180,
                        },
                        "dry_run": {
                            "type": "boolean",
                            "description": "Plan the handoff without opening or controlling a browser.",
                            "default": False,
                        },
                    },
                    "required": ["prompt"],
                },
            },
            {
                "name": "get_chatgpt_bridge_status",
                "description": "Report browser bridge state, run folder, macOS Apple Events status, Linux Chrome CDP status, and chat mappings.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "conversation_key": {
                            "type": "string",
                            "description": "Optional conversation key to inspect.",
                        }
                    },
                },
            },
            {
                "name": "reset_chat_mapping",
                "description": "Forget the saved ChatGPT chat URL for one Codex conversation.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "conversation_key": {
                            "type": "string",
                            "description": "Conversation key whose saved ChatGPT chat should be removed.",
                        }
                    },
                    "required": ["conversation_key"],
                },
            },
        ]

    def _call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name == "send_to_chatgpt_web":
            if not arguments.get("prompt"):
                raise JsonRpcError(-32602, "send_to_chatgpt_web requires a prompt")
            result = self.bridge.send_to_chatgpt_web(
                prompt=arguments["prompt"],
                files=arguments.get("files") or [],
                conversation_key=arguments.get("conversation_key") or "default",
                start_new_chat=bool(arguments.get("start_new_chat", False)),
                wait_timeout_sec=int(arguments.get("wait_timeout_sec", 180)),
                dry_run=bool(arguments.get("dry_run", False)),
                browser=arguments.get("browser") or "safari",
            )
            return self._text_result(result)
        if name == "get_chatgpt_bridge_status":
            return self._text_result(self.bridge.status(arguments.get("conversation_key")))
        if name == "reset_chat_mapping":
            conversation_key = arguments.get("conversation_key")
            if not conversation_key:
                raise JsonRpcError(-32602, "reset_chat_mapping requires conversation_key")
            return self._text_result(self.bridge.reset_chat_mapping(conversation_key))
        raise JsonRpcError(-32602, f"Unknown tool: {name}")

    def _text_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        return {"content": [{"type": "text", "text": result_to_text(result)}]}


def serve(server: Optional[MCPServer] = None, input_stream=None, output_stream=None) -> None:
    server = server or MCPServer()
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    for line in input_stream:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc}"},
            }
        else:
            response = server.handle(message)
        if response is not None:
            output_stream.write(json.dumps(response, separators=(",", ":")) + "\n")
            output_stream.flush()
