import shutil
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


DownloadSnapshot = Dict[str, Tuple[int, int]]


def default_downloads_dir() -> Path:
    return Path.home() / "Downloads"


def snapshot_downloads(downloads_dir: Optional[Path] = None) -> DownloadSnapshot:
    root = downloads_dir or default_downloads_dir()
    if not root.exists():
        return {}
    snapshot: DownloadSnapshot = {}
    for path in root.iterdir():
        if path.is_file() and not _is_transient_download(path):
            stat = path.stat()
            snapshot[str(path.resolve())] = (int(stat.st_mtime_ns), stat.st_size)
    return snapshot


def collect_new_downloads(
    before: DownloadSnapshot,
    destination: Path,
    downloads_dir: Optional[Path] = None,
    wait_sec: float = 5.0,
) -> List[str]:
    destination.mkdir(parents=True, exist_ok=True)
    root = downloads_dir or default_downloads_dir()
    deadline = time.time() + wait_sec
    copied: List[str] = []
    seen = set()
    while True:
        for path in _new_download_candidates(before, root):
            resolved = str(path.resolve())
            if resolved in seen:
                continue
            copied_path = _copy_unique(path, destination)
            copied.append(str(copied_path))
            seen.add(resolved)
        if time.time() >= deadline:
            return copied
        if copied and not any(_is_transient_download(path) for path in root.iterdir() if path.is_file()):
            return copied
        time.sleep(0.5)


def _new_download_candidates(before: DownloadSnapshot, root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    candidates: List[Path] = []
    for path in root.iterdir():
        if not path.is_file() or _is_transient_download(path):
            continue
        stat = path.stat()
        fingerprint = (int(stat.st_mtime_ns), stat.st_size)
        if before.get(str(path.resolve())) != fingerprint:
            candidates.append(path)
    return candidates


def _copy_unique(source: Path, destination: Path) -> Path:
    target = destination / source.name
    if not target.exists():
        shutil.copy2(source, target)
        return target
    stem = source.stem
    suffix = source.suffix
    index = 1
    while True:
        candidate = destination / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            shutil.copy2(source, candidate)
            return candidate
        index += 1


def _is_transient_download(path: Path) -> bool:
    return path.name.startswith(".") or path.suffix in {".download", ".crdownload", ".part", ".tmp"}
