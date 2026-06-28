import mimetypes
from pathlib import Path
from typing import Dict, Iterable, List


def build_file_manifest(files: Iterable[str]) -> List[Dict[str, object]]:
    manifest: List[Dict[str, object]] = []
    for raw_path in files:
        path = Path(raw_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(str(path))
        if not path.is_file():
            raise ValueError(f"Not a regular file: {path}")
        mime_type, _ = mimetypes.guess_type(str(path))
        manifest.append(
            {
                "path": str(path.resolve()),
                "name": path.name,
                "size_bytes": path.stat().st_size,
                "mime_type": mime_type or "application/octet-stream",
            }
        )
    return manifest
