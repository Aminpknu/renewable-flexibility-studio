from __future__ import annotations

import json
import struct
from pathlib import Path

import app

ROOT = Path(app.__file__).resolve().parent


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def test_pwa_manifest_and_icons_are_valid() -> None:
    manifest = json.loads((ROOT / "assets" / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert manifest["display"] == "standalone"
    assert manifest["start_url"].startswith("/")
    assert manifest["scope"] == "/"
    assert _png_size(ROOT / "assets" / "icon-192.png") == (192, 192)
    assert _png_size(ROOT / "assets" / "icon-512.png") == (512, 512)
    assert _png_size(ROOT / "assets" / "icon-maskable-512.png") == (512, 512)

def test_pwa_routes_and_index_tags() -> None:
    client = app.server.test_client()
    manifest = client.get("/manifest.webmanifest")
    worker = client.get("/service-worker.js")
    offline = client.get("/offline.html")
    index = client.get("/")
    assert manifest.status_code == 200
    assert manifest.mimetype in {"application/manifest+json", "application/json"}
    assert worker.status_code == 200
    assert worker.headers["Service-Worker-Allowed"] == "/"
    assert "no-cache" in worker.headers["Cache-Control"]
    assert offline.status_code == 200
    text = index.get_data(as_text=True)
    assert '<link rel="manifest" href="/manifest.webmanifest">' in text
    assert 'apple-mobile-web-app-capable' in text
    assert '/assets/apple-touch-icon.png' in text


def test_pwa_install_ui_and_worker_logic_present() -> None:
    layout = str(app.app.layout)
    worker = (ROOT / "pwa" / "service-worker.js").read_text(encoding="utf-8")
    script = (ROOT / "assets" / "pwa.js").read_text(encoding="utf-8")
    assert 'pwa-install-button' in layout
    assert 'pwa-connectivity' in layout
    assert 'pwa-install-help' in layout
    assert "request.mode === 'navigate'" in worker
    assert "caches.match(OFFLINE_URL)" in worker
    assert "beforeinstallprompt" in script
    assert "Add to Home Screen" in script
    assert "navigator.serviceWorker.register('/service-worker.js'" in script
