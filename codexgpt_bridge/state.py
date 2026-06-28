import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


STATE_DIR_ENV = "CODEXGPT_STATE_DIR"
LEGACY_STATE_DIR_ENV = "SAFARI_CHATGPT_BRIDGE_STATE_DIR"


@dataclass(frozen=True)
class BridgeRun:
    run_dir: Path
    downloads_dir: Path
    request_path: Path
    result_path: Path


def default_state_root() -> Path:
    override = os.environ.get(STATE_DIR_ENV) or os.environ.get(LEGACY_STATE_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".codex" / "state" / "codexgpt"


def _safe_slug(value: str, max_length: int = 48) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    if not slug:
        slug = "conversation"
    return slug[:max_length]


class BridgeState:
    def __init__(self, root: Optional[Path] = None):
        self.root = (root or default_state_root()).expanduser()
        self.state_path = self.root / "state.json"
        self.runs_root = self.root / "runs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.runs_root.mkdir(parents=True, exist_ok=True)

    def _load(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return {"chat_mappings": {}}
        with self.state_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        payload.setdefault("chat_mappings", {})
        return payload

    def _save(self, payload: Dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp_path = self.state_path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        tmp_path.replace(self.state_path)

    def get_chat_url(self, conversation_key: str) -> Optional[str]:
        payload = self._load()
        entry = payload["chat_mappings"].get(conversation_key)
        if isinstance(entry, dict):
            return entry.get("chat_url")
        if isinstance(entry, str):
            return entry
        return None

    def set_chat_url(self, conversation_key: str, chat_url: str) -> None:
        payload = self._load()
        payload["chat_mappings"][conversation_key] = {
            "chat_url": chat_url,
            "updated_at": int(time.time()),
        }
        self._save(payload)

    def reset_chat_url(self, conversation_key: str) -> bool:
        payload = self._load()
        existed = conversation_key in payload["chat_mappings"]
        payload["chat_mappings"].pop(conversation_key, None)
        self._save(payload)
        return existed

    def list_mappings(self) -> Dict[str, str]:
        payload = self._load()
        result: Dict[str, str] = {}
        for key, entry in payload["chat_mappings"].items():
            if isinstance(entry, dict) and isinstance(entry.get("chat_url"), str):
                result[key] = entry["chat_url"]
            elif isinstance(entry, str):
                result[key] = entry
        return result

    def create_run(self, conversation_key: str, prompt: str, files: List[str]) -> BridgeRun:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        slug = _safe_slug(conversation_key)
        suffix = 0
        while True:
            name = f"{timestamp}-{slug}" if suffix == 0 else f"{timestamp}-{slug}-{suffix}"
            run_dir = self.runs_root / name
            try:
                run_dir.mkdir(parents=True)
                break
            except FileExistsError:
                suffix += 1

        downloads_dir = run_dir / "downloads"
        downloads_dir.mkdir()
        request_path = run_dir / "request.json"
        result_path = run_dir / "result.json"
        request_payload = {
            "conversation_key": conversation_key,
            "prompt": prompt,
            "files": files,
            "created_at": int(time.time()),
        }
        with request_path.open("w", encoding="utf-8") as handle:
            json.dump(request_payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        return BridgeRun(
            run_dir=run_dir,
            downloads_dir=downloads_dir,
            request_path=request_path,
            result_path=result_path,
        )

    def write_result(self, run: BridgeRun, result: Dict[str, Any]) -> None:
        with run.result_path.open("w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, sort_keys=True)
            handle.write("\n")
