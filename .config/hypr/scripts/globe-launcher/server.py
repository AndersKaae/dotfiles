#!/usr/bin/env python3
"""3D globe app launcher: enumerates .desktop files and serves a CSS3D UI."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from configparser import ConfigParser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent

APP_DIRS = [
    Path("/usr/share/applications"),
    Path.home() / ".local/share/applications",
    Path("/var/lib/flatpak/exports/share/applications"),
    Path.home() / ".local/share/flatpak/exports/share/applications",
]

ICON_DIRS = [
    Path.home() / ".local/share/icons",
    Path("/usr/share/icons"),
    Path("/usr/share/pixmaps"),
]

ICON_EXTS = (".svg", ".png", ".xpm")
SIZE_PREFERENCE = ["scalable", "256", "192", "128", "96", "64", "48", "32", "24", "16"]


def find_icon(name: str):
    if not name:
        return None
    if name.startswith("/"):
        return name if Path(name).exists() else None
    candidates = []
    for base in ICON_DIRS:
        if not base.exists():
            continue
        for ext in ICON_EXTS:
            p = base / f"{name}{ext}"
            if p.exists():
                return str(p)
        try:
            for p in base.rglob(f"{name}.*"):
                if p.suffix.lower() in ICON_EXTS:
                    candidates.append(p)
        except OSError:
            continue
    if not candidates:
        return None

    def rank(p):
        s = str(p)
        for i, key in enumerate(SIZE_PREFERENCE):
            if f"/{key}/" in s or f"/{key}x{key}/" in s:
                return i
        return len(SIZE_PREFERENCE)

    candidates.sort(key=rank)
    return str(candidates[0])


def parse_desktop_file(path: Path):
    cp = ConfigParser(interpolation=None, strict=False)
    try:
        cp.read(path, encoding="utf-8")
    except Exception:
        return None
    if "Desktop Entry" not in cp:
        return None
    e = cp["Desktop Entry"]
    if e.get("Type", "Application") != "Application":
        return None
    if e.get("NoDisplay", "false").lower() == "true":
        return None
    if e.get("Hidden", "false").lower() == "true":
        return None
    name = e.get("Name")
    exec_cmd = e.get("Exec")
    if not name or not exec_cmd:
        return None
    exec_cmd = " ".join(
        p for p in exec_cmd.split() if not (p.startswith("%") and len(p) == 2)
    )
    return {
        "name": name,
        "exec": exec_cmd,
        "icon_name": e.get("Icon", ""),
    }


def collect_apps():
    seen = set()
    apps = []
    for d in APP_DIRS:
        if not d.exists():
            continue
        for f in d.glob("*.desktop"):
            if f.name in seen:
                continue
            seen.add(f.name)
            app = parse_desktop_file(f)
            if app:
                apps.append(app)
    apps.sort(key=lambda a: a["name"].lower())
    return apps


APPS = collect_apps()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a, **kw):
        pass

    def _send(self, status, body, ctype="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/":
            self._send(200, (ROOT / "globe.html").read_bytes(), "text/html; charset=utf-8")
            return
        if p == "/apps":
            data = [{"id": i, "name": a["name"]} for i, a in enumerate(APPS)]
            self._send(200, json.dumps(data).encode())
            return
        if p.startswith("/icon/"):
            try:
                i = int(p.rsplit("/", 1)[-1])
                app = APPS[i]
            except (ValueError, IndexError):
                self._send(404, b"")
                return
            icon = find_icon(app["icon_name"])
            if not icon:
                self._send(404, b"")
                return
            try:
                data = Path(icon).read_bytes()
            except OSError:
                self._send(404, b"")
                return
            ext = Path(icon).suffix.lower().lstrip(".")
            ctype = {"png": "image/png", "svg": "image/svg+xml", "xpm": "image/x-xpixmap"}.get(
                ext, "application/octet-stream"
            )
            self._send(200, data, ctype)
            return
        self._send(404, b"")

    def do_POST(self):
        p = urlparse(self.path).path
        if p == "/launch":
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length))
                cmd = APPS[int(payload["id"])]["exec"]
            except Exception:
                self._send(400, b"")
                return
            subprocess.Popen(["hyprctl", "dispatch", "exec", "--", cmd])
            self._send(200, b'{"ok":true}')
            return
        if p == "/close":
            self._send(200, b'{"ok":true}')
            return
        self._send(404, b"")


def main():
    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    profile_dir = tempfile.mkdtemp(prefix="globe-launcher-")
    url = f"http://127.0.0.1:{port}/"
    proc = subprocess.Popen([
        "brave",
        "--kiosk",
        f"--app={url}",
        "--class=globe-launcher",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=TranslateUI",
        "--password-store=basic",
    ])
    try:
        proc.wait()
    finally:
        server.shutdown()
        try:
            import shutil
            shutil.rmtree(profile_dir, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
