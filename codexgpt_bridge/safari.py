import base64
import hashlib
import json
import mimetypes
import os
import shutil
import socket
import struct
import subprocess
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .downloads import DownloadSnapshot, collect_new_downloads


CHATGPT_HOME_URL = "https://chatgpt.com/"
DEFAULT_LINUX_CHROME_CDP_HOST = "127.0.0.1"
DEFAULT_LINUX_CHROME_CDP_PORT = 9222


class SafariAutomationError(RuntimeError):
    pass


class NoOpFocusManager:
    def capture_frontmost_app(self) -> Optional[str]:
        return None

    def restore_app(self, app_name: Optional[str]) -> None:
        return


class MacOSFocusManager:
    def capture_frontmost_app(self) -> Optional[str]:
        try:
            return _osascript(
                'tell application "System Events" to return name of first application process whose frontmost is true',
                timeout=10,
            )
        except (SafariAutomationError, OSError):
            return None

    def restore_app(self, app_name: Optional[str]) -> None:
        if not app_name:
            return
        try:
            _osascript(f'tell application {json.dumps(app_name)} to activate', timeout=10)
        except (SafariAutomationError, OSError):
            return


def classify_javascript_permission_error(message: str) -> str:
    if "Allow JavaScript from Apple Events" in message:
        return "disabled"
    if "Executing JavaScript through AppleScript is turned off" in message:
        return "disabled"
    return "unknown"


def normalize_browser_name(browser: Optional[str]) -> str:
    value = (browser or "safari").strip().lower().replace("_", "-")
    if value in {"safari"}:
        return "safari"
    if value in {"chrome", "google-chrome", "google chrome", "chromium", "chromium-browser"}:
        return "chrome"
    raise ValueError("Unsupported browser. Use 'safari' or 'chrome'.")


def _osascript(script: str, timeout: int = 60) -> str:
    proc = subprocess.run(
        ["osascript", "-e", script],
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        message = proc.stderr.strip() or proc.stdout.strip() or "osascript failed"
        raise SafariAutomationError(message)
    return proc.stdout.strip()


def check_javascript_from_apple_events() -> Dict[str, str]:
    try:
        _osascript(_do_javascript_script("'ok'"), timeout=15)
    except Exception as exc:
        message = str(exc)
        return {
            "status": classify_javascript_permission_error(message),
            "message": message,
        }
    return {"status": "enabled", "message": "Safari accepted do JavaScript from Apple Events."}


def _do_javascript_script(javascript: str) -> str:
    return f"""
tell application "Safari"
  if not (exists front document) then make new document
  do JavaScript {json.dumps(javascript)} in front document
end tell
""".strip()


def build_chrome_javascript_applescript(javascript: str) -> str:
    return f"""
tell application "Google Chrome"
  if not (exists window 1) then make new window
  execute active tab of front window javascript {json.dumps(javascript)}
end tell
""".strip()


def check_chrome_javascript_from_apple_events() -> Dict[str, str]:
    try:
        _osascript(build_chrome_javascript_applescript("'ok'"), timeout=15)
    except Exception as exc:
        message = str(exc)
        return {
            "status": classify_javascript_permission_error(message),
            "message": message,
        }
    return {"status": "enabled", "message": "Chrome accepted JavaScript through Apple Events."}


def _linux_chrome_host() -> str:
    return (
        os.environ.get("CODEXGPT_CHROME_CDP_HOST")
        or os.environ.get("SAFARI_CHATGPT_BRIDGE_CHROME_CDP_HOST")
        or os.environ.get(
            "CHATGPT_BRIDGE_CHROME_CDP_HOST", DEFAULT_LINUX_CHROME_CDP_HOST
        )
    )


def _linux_chrome_port() -> int:
    value = (
        os.environ.get("CODEXGPT_CHROME_CDP_PORT")
        or os.environ.get("SAFARI_CHATGPT_BRIDGE_CHROME_CDP_PORT")
        or os.environ.get(
            "CHATGPT_BRIDGE_CHROME_CDP_PORT"
        )
    )
    if not value:
        return DEFAULT_LINUX_CHROME_CDP_PORT
    try:
        return int(value)
    except ValueError as exc:
        raise SafariAutomationError(f"Invalid Chrome CDP port: {value}") from exc


def _linux_chrome_user_data_dir() -> Path:
    value = (
        os.environ.get("CODEXGPT_CHROME_USER_DATA_DIR")
        or os.environ.get("SAFARI_CHATGPT_BRIDGE_CHROME_USER_DATA_DIR")
        or os.environ.get(
            "CHATGPT_BRIDGE_CHROME_USER_DATA_DIR"
        )
    )
    if value:
        return Path(value).expanduser()
    return Path.home() / ".codex" / "state" / "codexgpt" / "chrome-linux-profile"


def _linux_chrome_profile_directory() -> Optional[str]:
    value = (
        os.environ.get("CODEXGPT_CHROME_PROFILE_DIRECTORY")
        or os.environ.get("SAFARI_CHATGPT_BRIDGE_CHROME_PROFILE_DIRECTORY")
        or os.environ.get("CHATGPT_BRIDGE_CHROME_PROFILE_DIRECTORY")
    )
    return value.strip() if value and value.strip() else None


def find_linux_chrome_executable() -> str:
    explicit = (
        os.environ.get("CODEXGPT_CHROME_BINARY")
        or os.environ.get("SAFARI_CHATGPT_BRIDGE_CHROME_BINARY")
        or os.environ.get(
            "CHATGPT_BRIDGE_CHROME_BINARY"
        )
    )
    if explicit:
        resolved = shutil.which(explicit) if not Path(explicit).is_absolute() else explicit
        if resolved and Path(resolved).exists():
            return resolved
        raise SafariAutomationError(f"Chrome/Chromium binary not found: {explicit}")
    for candidate in ("google-chrome", "google-chrome-stable", "chromium-browser", "chromium", "chrome"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise SafariAutomationError(
        "Could not find Chrome or Chromium. Install google-chrome/chromium, or set "
        "CODEXGPT_CHROME_BINARY."
    )


def build_linux_chrome_launch_args(
    executable: str,
    port: int,
    user_data_dir: Path,
    initial_url: Optional[str] = None,
    profile_directory: Optional[str] = None,
) -> List[str]:
    args = [
        executable,
        f"--remote-debugging-port={int(port)}",
        f"--user-data-dir={Path(user_data_dir).expanduser()}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-mode",
        "--new-window",
    ]
    if profile_directory:
        args.append(f"--profile-directory={profile_directory}")
    if initial_url:
        args.append(initial_url)
    return args


def check_linux_chrome_cdp(host: Optional[str] = None, port: Optional[int] = None) -> Dict[str, str]:
    client = ChromeDevToolsHttpClient(host or _linux_chrome_host(), int(port or _linux_chrome_port()), timeout=2)
    try:
        version = client.version()
    except Exception as exc:
        return {"status": "unavailable", "message": str(exc)}
    return {
        "status": "available",
        "message": str(version.get("Browser") or "Chrome DevTools endpoint is available."),
    }


class ChromeDevToolsHttpClient:
    def __init__(self, host: str, port: int, timeout: float = 10.0):
        self.host = host
        self.port = int(port)
        self.timeout = timeout

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def request_json(self, path: str, method: str = "GET") -> object:
        request = urllib.request.Request(f"{self.base_url}{path}", method=method)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = response.read().decode("utf-8")
        return json.loads(body)

    def version(self) -> Dict[str, object]:
        payload = self.request_json("/json/version")
        if not isinstance(payload, dict):
            raise SafariAutomationError("Chrome DevTools version endpoint returned unexpected data.")
        return payload

    def targets(self) -> List[Dict[str, object]]:
        payload = self.request_json("/json/list")
        if not isinstance(payload, list):
            raise SafariAutomationError("Chrome DevTools target list returned unexpected data.")
        return [target for target in payload if isinstance(target, dict)]

    def new_page(self, url: str) -> Dict[str, object]:
        encoded = urllib.parse.quote(url, safe="")
        last_error = ""
        for method in ("PUT", "POST", "GET"):
            try:
                payload = self.request_json(f"/json/new?{encoded}", method=method)
            except Exception as exc:
                last_error = str(exc)
                continue
            if isinstance(payload, dict):
                return payload
            last_error = f"Unexpected /json/new payload: {payload!r}"
        raise SafariAutomationError(f"Could not open Chrome DevTools page: {last_error}")


class ChromeDevToolsWebSocket:
    def __init__(self, web_socket_url: str, timeout: float = 30.0):
        self.web_socket_url = web_socket_url
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def connect(self) -> None:
        parsed = urllib.parse.urlparse(self.web_socket_url)
        if parsed.scheme != "ws":
            raise SafariAutomationError(f"Unsupported Chrome DevTools WebSocket URL: {self.web_socket_url}")
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        sock = socket.create_connection((host, port), timeout=self.timeout)
        sock.settimeout(self.timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = "\r\n".join(
            [
                f"GET {path} HTTP/1.1",
                f"Host: {host}:{port}",
                "Upgrade: websocket",
                "Connection: Upgrade",
                f"Sec-WebSocket-Key: {key}",
                "Sec-WebSocket-Version: 13",
                "\r\n",
            ]
        )
        sock.sendall(request.encode("ascii"))
        response = self._read_http_headers(sock)
        if " 101 " not in response.splitlines()[0]:
            sock.close()
            raise SafariAutomationError(f"Chrome DevTools WebSocket handshake failed: {response.splitlines()[0]}")
        expected_accept = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        ).decode("ascii")
        if expected_accept not in response:
            sock.close()
            raise SafariAutomationError("Chrome DevTools WebSocket handshake returned an invalid accept key.")
        self.sock = sock

    def send_json(self, payload: Dict[str, object]) -> None:
        self._send_frame(json.dumps(payload, separators=(",", ":")).encode("utf-8"))

    def recv_json(self, expected_id: int) -> Dict[str, object]:
        while True:
            message = self._recv_text_message()
            payload = json.loads(message)
            if payload.get("id") == expected_id:
                return payload

    def close(self) -> None:
        if not self.sock:
            return
        try:
            self.sock.close()
        finally:
            self.sock = None

    def _read_http_headers(self, sock: socket.socket) -> str:
        chunks = []
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
            data = b"".join(chunks)
        return data.decode("iso-8859-1", errors="replace")

    def _send_frame(self, payload: bytes, opcode: int = 0x1) -> None:
        if not self.sock:
            raise SafariAutomationError("Chrome DevTools WebSocket is not connected.")
        header = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _recv_text_message(self) -> str:
        parts: List[bytes] = []
        while True:
            fin, opcode, payload = self._recv_frame()
            if opcode == 0x8:
                raise SafariAutomationError("Chrome DevTools WebSocket closed.")
            if opcode == 0x9:
                self._send_frame(payload, opcode=0xA)
                continue
            if opcode in {0x1, 0x0}:
                parts.append(payload)
                if fin:
                    return b"".join(parts).decode("utf-8")

    def _recv_frame(self) -> Tuple[bool, int, bytes]:
        if not self.sock:
            raise SafariAutomationError("Chrome DevTools WebSocket is not connected.")
        head = self._recv_exact(2)
        first, second = head
        fin = bool(first & 0x80)
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8))[0]
        mask = self._recv_exact(4) if masked else b""
        payload = self._recv_exact(length) if length else b""
        if masked:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        return fin, opcode, payload

    def _recv_exact(self, size: int) -> bytes:
        if not self.sock:
            raise SafariAutomationError("Chrome DevTools WebSocket is not connected.")
        chunks = []
        remaining = size
        while remaining:
            chunk = self.sock.recv(remaining)
            if not chunk:
                raise SafariAutomationError("Chrome DevTools WebSocket closed unexpectedly.")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)


def build_open_chat_applescript(target_url: str) -> str:
    return f"""
tell application "Safari"
  activate
  make new document with properties {{URL:{json.dumps(target_url)}}}
end tell
""".strip()


def build_open_chrome_chat_applescript(target_url: str) -> str:
    return f"""
tell application "Google Chrome"
  activate
  if not (exists window 1) then
    make new window
    set URL of active tab of front window to {json.dumps(target_url)}
  else
    make new tab at end of tabs of front window with properties {{URL:{json.dumps(target_url)}}}
    set active tab index of front window to (count of tabs of front window)
  end if
end tell
""".strip()


def build_prompt_javascript(prompt: str) -> str:
    prompt_json = json.dumps(prompt)
    return textwrap.dedent(
        f"""
        (() => {{
          const prompt = {prompt_json};
          const selectors = [
            'textarea[data-testid="prompt-textarea"]',
            '[contenteditable="true"][data-testid="prompt-textarea"]',
            '#prompt-textarea',
            'textarea',
            '[contenteditable="true"]'
          ];
          const composer = selectors.map((selector) => document.querySelector(selector)).find(Boolean);
          if (!composer) {{
            return JSON.stringify({{ ok: false, reason: 'composer_not_found' }});
          }}
          composer.focus();
          if ('value' in composer) {{
            composer.value = prompt;
            composer.dispatchEvent(new InputEvent('input', {{ bubbles: true, inputType: 'insertText', data: prompt }}));
          }} else {{
            composer.textContent = prompt;
            composer.dispatchEvent(new InputEvent('input', {{ bubbles: true, inputType: 'insertText', data: prompt }}));
          }}
          const sendSelectors = [
            'button[data-testid="send-button"]',
            'button[aria-label="Send prompt"]',
            'button[aria-label="Send message"]',
            'button[aria-label*="Send"]'
          ];
          const button = sendSelectors.map((selector) => document.querySelector(selector)).find(Boolean);
          if (!button) {{
            return JSON.stringify({{ ok: false, reason: 'send-button_not_found' }});
          }}
          button.click();
          return JSON.stringify({{ ok: true, url: location.href }});
        }})();
        """
    ).strip()


def build_focus_composer_javascript() -> str:
    return textwrap.dedent(
        """
        (() => {
          const selectors = [
            '#prompt-textarea',
            '[contenteditable="true"][role="textbox"]',
            '[contenteditable="true"]',
            'textarea[name="prompt-textarea"]',
            'textarea[aria-label="Chat with ChatGPT"]',
            'textarea'
          ];
          const composer = selectors.map((selector) => document.querySelector(selector)).find(Boolean);
          if (!composer) {
            return JSON.stringify({ ok: false, reason: 'composer_not_found' });
          }
          composer.focus();
          return JSON.stringify({ ok: true });
        })();
        """
    ).strip()


def build_assert_chatgpt_page_javascript() -> str:
    return textwrap.dedent(
        """
        (() => {
          const ok = location.hostname === 'chatgpt.com' || location.hostname.endsWith('.chatgpt.com');
          return JSON.stringify({ ok, url: location.href, hostname: location.hostname });
        })();
        """
    ).strip()


def build_paste_and_submit_applescript() -> str:
    return textwrap.dedent(
        """
        tell application "System Events"
          keystroke "v" using {command down}
          delay 0.6
          key code 36
        end tell
        """
    ).strip()


def build_composer_plus_rect_javascript() -> str:
    return textwrap.dedent(
        """
        (() => {
          const selectors = [
            'button[data-testid="composer-plus-btn"]',
            'button[aria-label="Add files and more"]',
            'button[aria-label*="Add files"]',
            'button[aria-label*="Attach"]',
            'button[aria-label*="Upload"]'
          ];
          const target = selectors.map((selector) => document.querySelector(selector)).find(Boolean);
          if (!target) {
            return JSON.stringify({ ok: false, reason: 'composer_plus_not_found' });
          }
          const rect = target.getBoundingClientRect();
          const chromeHeight = Math.max(0, window.outerHeight - window.innerHeight);
          return JSON.stringify({
            ok: true,
            x: Math.round(window.screenX + rect.left + rect.width / 2),
            y: Math.round(window.screenY + chromeHeight + rect.top + rect.height / 2),
            rect: {
              left: rect.left,
              top: rect.top,
              width: rect.width,
              height: rect.height
            }
          });
        })();
        """
    ).strip()


def build_open_file_picker_applescript(x: int, y: int) -> str:
    upload_row_x = int(x) + 38
    upload_row_y = max(40, int(y) - 446)
    return textwrap.dedent(
        f"""
        tell application "System Events"
          click at {{{int(x)}, {int(y)}}}
          delay 0.45
          click at {{{upload_row_x}, {upload_row_y}}}
        end tell
        """
    ).strip()


def build_choose_file_applescript() -> str:
    return textwrap.dedent(
        """
        tell application "System Events"
          keystroke "g" using {command down, shift down}
          delay 0.5
          keystroke "a" using {command down}
          delay 0.15
          keystroke "v" using {command down}
          delay 0.35
          key code 36
          delay 0.9
          key code 36
        end tell
        """
    ).strip()


def build_inject_file_javascript(file_name: str, mime_type: str, base64_content: str) -> str:
    file_name_json = json.dumps(file_name)
    mime_type_json = json.dumps(mime_type)
    base64_json = json.dumps(base64_content)
    return textwrap.dedent(
        f"""
        (() => {{
          const input = document.querySelector('#upload-files, input[type="file"]:not([accept]), input[type="file"]');
          if (!input) {{
            return JSON.stringify({{ ok: false, reason: 'file_input_not_found' }});
          }}
          const binary = atob({base64_json});
          const bytes = new Uint8Array(binary.length);
          for (let i = 0; i < binary.length; i += 1) {{
            bytes[i] = binary.charCodeAt(i);
          }}
          const file = new File([bytes], {file_name_json}, {{ type: {mime_type_json} }});
          const transfer = new DataTransfer();
          transfer.items.add(file);
          input.files = transfer.files;
          input.dispatchEvent(new Event('input', {{ bubbles: true }}));
          input.dispatchEvent(new Event('change', {{ bubbles: true }}));
          return JSON.stringify({{
            ok: true,
            name: file.name,
            size: file.size,
            type: file.type,
            files: input.files.length
          }});
        }})();
        """
    ).strip()


def build_start_file_injection_javascript(upload_id: str) -> str:
    upload_id_json = json.dumps(upload_id)
    return textwrap.dedent(
        f"""
        (() => {{
          window.__safariChatGPTBridgeUploads = window.__safariChatGPTBridgeUploads || {{}};
          window.__safariChatGPTBridgeUploads[{upload_id_json}] = {{ chunks: [] }};
          return JSON.stringify({{ ok: true, uploadId: {upload_id_json} }});
        }})();
        """
    ).strip()


def build_append_file_injection_chunk_javascript(upload_id: str, chunk: str) -> str:
    upload_id_json = json.dumps(upload_id)
    chunk_json = json.dumps(chunk)
    return textwrap.dedent(
        f"""
        (() => {{
          const store = window.__safariChatGPTBridgeUploads || {{}};
          const entry = store[{upload_id_json}];
          if (!entry) {{
            return JSON.stringify({{ ok: false, reason: 'upload_session_not_found' }});
          }}
          entry.chunks.push({chunk_json});
          return JSON.stringify({{ ok: true, chunks: entry.chunks.length }});
        }})();
        """
    ).strip()


def build_finish_file_injection_javascript(
    upload_id: str,
    file_name: str,
    mime_type: str,
    expected_size: int,
) -> str:
    upload_id_json = json.dumps(upload_id)
    file_name_json = json.dumps(file_name)
    mime_type_json = json.dumps(mime_type)
    return textwrap.dedent(
        f"""
        (() => {{
          const store = window.__safariChatGPTBridgeUploads || {{}};
          const entry = store[{upload_id_json}];
          if (!entry) {{
            return JSON.stringify({{ ok: false, reason: 'upload_session_not_found' }});
          }}
          const input = document.querySelector('#upload-files, input[type="file"]:not([accept]), input[type="file"]');
          if (!input) {{
            return JSON.stringify({{ ok: false, reason: 'file_input_not_found' }});
          }}
          const binary = atob(entry.chunks.join(''));
          if (binary.length !== {int(expected_size)}) {{
            return JSON.stringify({{ ok: false, reason: 'decoded_size_mismatch', size: binary.length }});
          }}
          const bytes = new Uint8Array(binary.length);
          for (let i = 0; i < binary.length; i += 1) {{
            bytes[i] = binary.charCodeAt(i);
          }}
          const file = new File([bytes], {file_name_json}, {{ type: {mime_type_json} }});
          const transfer = new DataTransfer();
          transfer.items.add(file);
          input.files = transfer.files;
          input.dispatchEvent(new Event('input', {{ bubbles: true }}));
          input.dispatchEvent(new Event('change', {{ bubbles: true }}));
          delete store[{upload_id_json}];
          return JSON.stringify({{
            ok: true,
            name: file.name,
            size: file.size,
            type: file.type,
            files: input.files.length
          }});
        }})();
        """
    ).strip()


def build_extract_response_javascript() -> str:
    return textwrap.dedent(
        """
        (() => {
          let nodes = Array.from(document.querySelectorAll('[data-message-author-role="assistant"]'));
          if (!nodes.length) {
            const fallbackSelectors = [
              'article[data-testid*="conversation-turn"]',
              '.markdown'
            ];
            for (const selector of fallbackSelectors) {
              nodes = Array.from(document.querySelectorAll(selector)).filter((node) => {
                return (node.innerText && node.innerText.trim()) || node.querySelector('img');
              });
              if (nodes.length) break;
            }
          }
          const last = nodes[nodes.length - 1] || null;
          const scope = last || document;
          const downloadable = Array.from(document.querySelectorAll('a[download], a[href^="blob:"], a[href*="/backend-api/files/"], a[href*="/file-"]'))
            .map((a) => ({ text: a.innerText || a.getAttribute('aria-label') || '', href: a.href || '', download: a.getAttribute('download') || '' }));
          const downloadButtons = Array.from(document.querySelectorAll('button[aria-label*="Download"], button[title*="Download"]'))
            .map((button) => ({ text: button.innerText || '', aria: button.getAttribute('aria-label') || '', title: button.getAttribute('title') || '' }));
          const images = Array.from(scope.querySelectorAll('img'))
            .filter((img) => img.src)
            .map((img) => ({ src: img.src || '', alt: img.alt || '', width: img.naturalWidth || img.width || 0, height: img.naturalHeight || img.height || 0 }));
          const hasVisualOutput = images.length > 0 || downloadable.length > 0 || downloadButtons.length > 0;
          return JSON.stringify({
            url: location.href,
            title: document.title,
            hasAssistant: !!last || hasVisualOutput,
            text: last ? (last.innerText || '').trim() : '',
            html: last ? (last.innerHTML || '').trim() : '',
            downloadable: downloadable,
            downloadButtons: downloadButtons,
            images: images,
            hasVisualOutput: hasVisualOutput
          });
        })();
        """
    ).strip()


def build_click_downloads_javascript() -> str:
    return textwrap.dedent(
        """
        (() => {
          const selectors = [
            'a[download]',
            'a[href^="blob:"]',
            'a[href*="/backend-api/files/"]',
            'a[href*="/file-"]',
            'button[aria-label*="Download"]',
            'button[title*="Download"]'
          ];
          const targets = [];
          for (const selector of selectors) {
            for (const node of document.querySelectorAll(selector)) {
              if (!targets.includes(node)) targets.push(node);
            }
          }
          const seenImageUrls = new Set();
          for (const img of Array.from(document.querySelectorAll('img[src*="backend-api/estuary"], img[src*="/backend-api/estuary"], img[src*="/backend-api/files/"]')).slice(-8)) {
            if (!img.src || seenImageUrls.has(img.src)) continue;
            seenImageUrls.add(img.src);
            const link = document.createElement('a');
            link.href = img.src;
            link.download = `chatgpt-image-${seenImageUrls.size}.png`;
            link.dataset.syntheticDownload = 'true';
            document.body.appendChild(link);
            targets.push(link);
          }
          const clicked = [];
          for (const target of targets.slice(-8)) {
            const label = target.innerText || target.getAttribute('aria-label') || target.getAttribute('title') || target.href || '';
            target.click();
            clicked.push(label);
            if (target.dataset && target.dataset.syntheticDownload === 'true') {
              setTimeout(() => target.remove(), 1000);
            }
          }
          return JSON.stringify({ ok: true, clicked });
        })();
        """
    ).strip()


def build_generation_state_javascript() -> str:
    return textwrap.dedent(
        """
        (() => {
          const text = document.body ? document.body.innerText || '' : '';
          const hasStop = !!document.querySelector(
            'button[data-testid="stop-button"], button[aria-label*="Stop"], button[aria-label*="Cancel"]'
          );
          return JSON.stringify({
            isGenerating: hasStop || text.includes('Finalizing answer'),
            hasStop,
            hasFinalizing: text.includes('Finalizing answer')
          });
        })();
        """
    ).strip()


def normalize_extracted_response(raw: str) -> Dict[str, object]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SafariAutomationError(f"Could not parse ChatGPT extraction payload: {exc}") from exc
    return {
        "url": payload.get("url", ""),
        "title": payload.get("title", ""),
        "text": payload.get("text", ""),
        "html": payload.get("html", ""),
        "has_assistant": bool(payload.get("hasAssistant", False)),
        "downloadable": payload.get("downloadable", []),
        "download_buttons": payload.get("downloadButtons", []),
        "images": payload.get("images", []),
        "has_visual_output": bool(payload.get("hasVisualOutput", False)),
    }


class SafariChatGPTClient:
    browser_name = "safari"
    file_upload_chunk_size = 60000
    upload_settle_sec = 3

    def __init__(self, wait_interval_sec: float = 2.0):
        self.wait_interval_sec = wait_interval_sec

    def build_javascript_applescript(self, javascript: str) -> str:
        return _do_javascript_script(javascript)

    def build_open_chat_applescript(self, target_url: str) -> str:
        return build_open_chat_applescript(target_url)

    def _run_js(self, javascript: str, timeout: int = 30) -> str:
        return _osascript(self.build_javascript_applescript(javascript), timeout=timeout)

    def open_chat(self, chat_url: Optional[str], start_new_chat: bool) -> str:
        target = CHATGPT_HOME_URL if start_new_chat or not chat_url else chat_url
        _osascript(self.build_open_chat_applescript(target), timeout=35)
        self._wait_for_chatgpt_page()
        return target

    def upload_files(self, files: Iterable[str]) -> List[str]:
        uploaded: List[str] = []
        for file_path in files:
            path = str(Path(file_path).expanduser().resolve())
            self._inject_file(Path(path))
            uploaded.append(path)
        return uploaded

    def _inject_file(self, path: Path) -> None:
        mime_type, _ = mimetypes.guess_type(str(path))
        content = base64.b64encode(path.read_bytes()).decode("ascii")
        upload_id = f"{int(time.time() * 1000)}-{path.name}"
        self._expect_js_ok(
            self._run_js(build_start_file_injection_javascript(upload_id), timeout=30),
            "File injection start script",
        )
        chunk_size = max(1, int(getattr(self, "file_upload_chunk_size", 60000)))
        for offset in range(0, len(content), chunk_size):
            chunk = content[offset : offset + chunk_size]
            self._expect_js_ok(
                self._run_js(build_append_file_injection_chunk_javascript(upload_id, chunk), timeout=30),
                "File injection chunk script",
            )
        raw = self._run_js(
            build_finish_file_injection_javascript(
                upload_id,
                path.name,
                mime_type or "application/octet-stream",
                path.stat().st_size,
            ),
            timeout=60,
        )
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SafariAutomationError(f"File injection script returned invalid JSON: {raw}") from exc
        if not payload.get("ok"):
            raise SafariAutomationError(str(payload.get("reason", "file injection failed")))
        if int(payload.get("size") or -1) != path.stat().st_size:
            raise SafariAutomationError(f"Injected file size mismatch for {path.name}")
        time.sleep(float(getattr(self, "upload_settle_sec", 3)))

    def _expect_js_ok(self, raw: str, label: str) -> Dict[str, object]:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SafariAutomationError(f"{label} returned invalid JSON: {raw}") from exc
        if not payload.get("ok"):
            raise SafariAutomationError(str(payload.get("reason", f"{label} failed")))
        return payload

    def _click_attach_button(self) -> None:
        raw = self._run_js(build_composer_plus_rect_javascript(), timeout=30)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SafariAutomationError(f"Composer plus script returned invalid JSON: {raw}") from exc
        if not payload.get("ok"):
            raise SafariAutomationError(str(payload.get("reason", "composer plus not found")))
        try:
            x = int(payload["x"])
            y = int(payload["y"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SafariAutomationError(f"Composer plus script returned invalid coordinates: {raw}") from exc
        _osascript(build_open_file_picker_applescript(x, y), timeout=30)
        time.sleep(1)

    def _choose_file(self, path: str) -> None:
        subprocess.run(["pbcopy"], input=path, text=True, check=True)
        _osascript(build_choose_file_applescript(), timeout=30)
        time.sleep(3)

    def submit_prompt(self, prompt: str) -> None:
        self.assert_chatgpt_page()
        raw = self._run_js(build_focus_composer_javascript(), timeout=30)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SafariAutomationError(f"Composer focus script returned invalid JSON: {raw}") from exc
        if not payload.get("ok"):
            raise SafariAutomationError(str(payload.get("reason", "composer focus failed")))
        subprocess.run(["pbcopy"], input=prompt, text=True, check=True)
        _osascript(build_paste_and_submit_applescript(), timeout=30)

    def wait_for_response(self, timeout_sec: int = 180) -> Dict[str, object]:
        deadline = time.time() + timeout_sec
        last_signature = ""
        stable_count = 0
        last_payload: Optional[Dict[str, object]] = None
        while time.time() < deadline:
            payload = self.extract_latest_response()
            text = str(payload.get("text") or "")
            has_assistant = bool(payload.get("has_assistant", False))
            has_visual_output = bool(
                payload.get("has_visual_output") or payload.get("images") or payload.get("downloadable")
            )
            signature = text
            if not signature and has_visual_output:
                signature = json.dumps(
                    {
                        "downloadable": payload.get("downloadable", []),
                        "images": payload.get("images", []),
                    },
                    sort_keys=True,
                )
            has_output = has_assistant and bool(signature) and (bool(text) or has_visual_output)
            if has_output and signature == last_signature:
                stable_count += 1
            else:
                stable_count = 0
                last_signature = signature
            last_payload = payload
            if has_output and stable_count >= 2 and not self._is_generating():
                return payload
            time.sleep(self.wait_interval_sec)
        if (
            last_payload
            and last_payload.get("has_assistant")
            and (last_payload.get("text") or last_payload.get("has_visual_output"))
            and not self._is_generating()
        ):
            return last_payload
        raise SafariAutomationError("Timed out waiting for ChatGPT response")

    def _is_generating(self) -> bool:
        try:
            raw = self._run_js(build_generation_state_javascript(), timeout=10)
            return bool(json.loads(raw).get("isGenerating"))
        except SafariAutomationError:
            return False
        except json.JSONDecodeError:
            return False

    def extract_latest_response(self) -> Dict[str, object]:
        self.assert_chatgpt_page()
        raw = self._run_js(build_extract_response_javascript(), timeout=30)
        return normalize_extracted_response(raw)

    def assert_chatgpt_page(self) -> None:
        raw = self._run_js(build_assert_chatgpt_page_javascript(), timeout=15)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SafariAutomationError(f"ChatGPT page assertion returned invalid JSON: {raw}") from exc
        if not payload.get("ok"):
            raise SafariAutomationError(f"Refusing to automate non-ChatGPT page: {payload.get('url', '')}")

    def _wait_for_chatgpt_page(self, timeout_sec: int = 30) -> None:
        deadline = time.time() + timeout_sec
        last_error = ""
        while time.time() < deadline:
            try:
                self.assert_chatgpt_page()
                return
            except Exception as exc:
                last_error = str(exc)
                time.sleep(0.5)
        raise SafariAutomationError(f"Timed out waiting for ChatGPT page: {last_error}")

    def click_download_links(self) -> List[str]:
        raw = self._run_js(build_click_downloads_javascript(), timeout=30)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SafariAutomationError(f"Download click script returned invalid JSON: {raw}") from exc
        if not payload.get("ok"):
            raise SafariAutomationError(str(payload.get("reason", "download click failed")))
        return [str(item) for item in payload.get("clicked", [])]

    def collect_downloaded_files(
        self,
        before: DownloadSnapshot,
        destination: Path,
        wait_sec: float = 8.0,
    ) -> List[str]:
        clicked = self.click_download_links()
        if clicked:
            time.sleep(1)
        return collect_new_downloads(before, destination, wait_sec=wait_sec)


class ChromeChatGPTClient(SafariChatGPTClient):
    browser_name = "chrome"

    def build_javascript_applescript(self, javascript: str) -> str:
        return build_chrome_javascript_applescript(javascript)

    def build_open_chat_applescript(self, target_url: str) -> str:
        return build_open_chrome_chat_applescript(target_url)


class LinuxChromeChatGPTClient(SafariChatGPTClient):
    browser_name = "chrome"

    def __init__(
        self,
        wait_interval_sec: float = 2.0,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user_data_dir: Optional[Path] = None,
        profile_directory: Optional[str] = None,
        executable: Optional[str] = None,
    ):
        super().__init__(wait_interval_sec=wait_interval_sec)
        self.host = host or _linux_chrome_host()
        self.port = int(port or _linux_chrome_port())
        self.user_data_dir = Path(user_data_dir).expanduser() if user_data_dir else _linux_chrome_user_data_dir()
        self.profile_directory = profile_directory or _linux_chrome_profile_directory()
        self.executable = executable
        self._http = ChromeDevToolsHttpClient(self.host, self.port)
        self._process: Optional[subprocess.Popen] = None
        self._target: Optional[Dict[str, object]] = None

    def open_chat(self, chat_url: Optional[str], start_new_chat: bool) -> str:
        target = CHATGPT_HOME_URL if start_new_chat or not chat_url else chat_url
        self._ensure_browser()
        self._target = self._http.new_page(target)
        self._wait_for_chatgpt_page()
        return target

    def submit_prompt(self, prompt: str) -> None:
        self.assert_chatgpt_page()
        raw = self._run_js(build_prompt_javascript(prompt), timeout=30)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SafariAutomationError(f"Prompt submit script returned invalid JSON: {raw}") from exc
        if not payload.get("ok"):
            raise SafariAutomationError(str(payload.get("reason", "prompt submit failed")))

    def _run_js(self, javascript: str, timeout: int = 30) -> str:
        target = self._current_target()
        web_socket_url = str(target.get("webSocketDebuggerUrl") or "")
        if not web_socket_url:
            raise SafariAutomationError("Chrome DevTools target did not include a WebSocket URL.")
        command_id = 1
        with ChromeDevToolsWebSocket(web_socket_url, timeout=timeout) as ws:
            ws.send_json(
                {
                    "id": command_id,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": javascript,
                        "awaitPromise": True,
                        "returnByValue": True,
                        "userGesture": True,
                    },
                }
            )
            payload = ws.recv_json(command_id)
        if payload.get("exceptionDetails"):
            raise SafariAutomationError(f"Chrome JavaScript evaluation failed: {payload['exceptionDetails']}")
        result = payload.get("result", {})
        if not isinstance(result, dict):
            raise SafariAutomationError(f"Chrome DevTools returned unexpected payload: {payload!r}")
        value_payload = result.get("result", {})
        if not isinstance(value_payload, dict):
            raise SafariAutomationError(f"Chrome DevTools returned unexpected result: {payload!r}")
        if "value" in value_payload:
            return str(value_payload.get("value", ""))
        if value_payload.get("type") == "undefined":
            return ""
        return str(value_payload.get("description", ""))

    def _current_target(self) -> Dict[str, object]:
        self._ensure_browser()
        if self._target:
            return self._target
        for target in self._http.targets():
            url = str(target.get("url") or "")
            if "chatgpt.com" in url and target.get("webSocketDebuggerUrl"):
                self._target = target
                return target
        self._target = self._http.new_page(CHATGPT_HOME_URL)
        return self._target

    def _ensure_browser(self) -> None:
        try:
            self._http.version()
            return
        except Exception:
            pass
        executable = self.executable or find_linux_chrome_executable()
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        args = build_linux_chrome_launch_args(
            executable=executable,
            port=self.port,
            user_data_dir=self.user_data_dir,
            profile_directory=self.profile_directory,
            initial_url=CHATGPT_HOME_URL,
        )
        self._process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        deadline = time.time() + 15
        last_error = ""
        while time.time() < deadline:
            try:
                self._http.version()
                return
            except Exception as exc:
                last_error = str(exc)
                time.sleep(0.25)
        raise SafariAutomationError(f"Timed out waiting for Chrome DevTools endpoint: {last_error}")
