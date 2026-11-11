"""Kayıtlar, kalıcı saklama ve tek bir kaydın kontrolü."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .extract import Candidate, anchor_from, extract_candidates, is_newer, pick_tracked, same_version
from .fetch import BlockedError, Browser, FetchError, Page, fetch_http

KINDS = ["BIOS", "Sürücü", "Firmware", "Yazılım", "Diğer"]


def data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    p = Path(base) / "DriverWatch"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------- kayıt

@dataclass
class Item:
    url: str
    name: str = ""
    kind: str = "Sürücü"
    installed: str = ""
    installed_auto: bool = False  # BIOS: yüklü sürümü bilgisayardan oku
    latest: str = ""
    latest_date: str = ""
    link: str = ""
    anchor: dict = field(default_factory=dict)
    state: str = "new"  # new | ok | update | noinstalled | blocked | error | lost
    message: str = ""
    last_checked: str = ""
    added: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])

    def recompute_state(self):
        if self.state in ("blocked", "error", "lost") and not self.latest:
            return
        if not self.latest:
            self.state = "new"
        elif not self.installed:
            self.state = "noinstalled"
        elif is_newer(self.latest, self.installed):
            self.state = "update"
        elif same_version(self.latest, self.installed) or not is_newer(self.latest, self.installed):
            self.state = "ok"


class Store:
    def __init__(self, path: Path | None = None):
        self.path = path or (data_dir() / "items.json")
        self.items: list[Item] = []
        self.settings: dict = {"check_on_start": True}
        self.load()

    def load(self):
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # bozuk dosyayı kaybetmeyelim
            self.path.replace(self.path.with_suffix(".bozuk.json"))
            return
        known = set(Item.__dataclass_fields__)
        self.items = [Item(**{k: v for k, v in d.items() if k in known}) for d in raw.get("items", [])]
        self.settings.update(raw.get("settings", {}))

    def save(self):
        data = {"version": 1, "settings": self.settings, "items": [asdict(i) for i in self.items]}
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def get(self, item_id: str) -> Item | None:
        return next((i for i in self.items if i.id == item_id), None)

    def has_url(self, url: str) -> bool:
        return any(i.url.strip() == url.strip() for i in self.items)

    def import_legacy(self, path: Path) -> int:
        """Eski Gemini uygulamasının tracker_data.json dosyasındaki linkleri al."""
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        n = 0
        for url in raw:
            if not self.has_url(url):
                kind = guess_kind(url)
                auto = kind == "BIOS" and bool(system_bios().get("version"))
                self.items.append(Item(url=url, kind=kind, installed_auto=auto))
                n += 1
        self.save()
        return n


_LABELS = ("revision", "version", "sürüm", "ver.", "release", "file size", "download", "applicable", "driver details")


def title_for(c: Candidate, page_title: str = "") -> str:
    """Sürümün hemen üstündeki başlık satırı: 'AMD Chipset Drivers' gibi."""
    for line in reversed(c.prev.split(" | ")):
        low = line.lower()
        if len(line) > 3 and not any(low.startswith(k) for k in _LABELS):
            return line[:80] if len(line) < 60 else page_title
    return page_title


def name_from_url(url: str) -> str:
    """'https://www.msi.com/Motherboard/X670E-GAMING-PLUS-WIFI/support#bios' → 'msi.com · X670E GAMING PLUS WIFI · bios'"""
    from urllib.parse import unquote, urlparse

    u = urlparse(url)
    host = u.netloc.removeprefix("www.")
    skip = {"support", "downloads", "download", "drivers", "driver", "app", "answers", "detail", "en", "us", "tr", "~"}
    segs = [unquote(s) for s in u.path.split("/") if s and s.lower() not in skip and not s.isdigit()]
    seg = max(segs, key=len) if segs else ""
    seg = seg.replace(".html", "").replace("-", " ").replace("_", " ").strip()
    parts = [host] + ([seg[:50]] if seg else []) + ([u.fragment] if u.fragment else [])
    return " · ".join(parts)


def guess_kind(url: str, title: str = "") -> str:
    s = (url + " " + title).lower()
    if "bios" in s:
        return "BIOS"
    if "firmware" in s:
        return "Firmware"
    if "driver" in s or "chipset" in s or "sürücü" in s:
        return "Sürücü"
    return "Diğer"


# ---------------------------------------------------------------- sistem

_bios_cache: dict | None = None


def system_bios() -> dict:
    """Bilgisayardaki BIOS sürümü ve anakart modeli (Windows)."""
    global _bios_cache
    if _bios_cache is not None:
        return _bios_cache
    info = {"version": "", "board": "", "date": ""}
    if os.name == "nt":
        ps = (
            "$b=Get-CimInstance Win32_BIOS; $m=Get-CimInstance Win32_BaseBoard;"
            "[pscustomobject]@{v=$b.SMBIOSBIOSVersion; d=$b.ReleaseDate.ToString('yyyy-MM-dd');"
            " p=($m.Manufacturer + ' ' + $m.Product)} | ConvertTo-Json -Compress"
        )
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                capture_output=True, text=True, timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout
            d = json.loads(out)
            info = {"version": (d.get("v") or "").strip(), "board": (d.get("p") or "").strip(), "date": d.get("d") or ""}
        except Exception:  # noqa: BLE001
            pass
    _bios_cache = info
    return info


# ---------------------------------------------------------------- kontrol

@dataclass
class Probe:
    page: Page | None = None
    candidates: list[Candidate] = field(default_factory=list)
    blocked: bool = False
    error: str = ""


def probe(url: str, browser: Browser, need_chrome_if_empty: bool = True) -> Probe:
    """Sayfayı indir ve sürüm adaylarını çıkar (önce düz istek, sonra Chrome)."""
    p = Probe()
    http_err = ""
    try:
        p.page = fetch_http(url)
        p.candidates = extract_candidates(p.page.text, p.page.links)
    except BlockedError as e:
        http_err = str(e)
    except FetchError as e:
        http_err = str(e)
    if p.candidates and not need_chrome_if_empty:
        return p
    if not p.candidates or "#" in url:
        try:
            page = browser.fetch(url)
            cands = extract_candidates(page.text, page.links)
            if cands or not p.page:
                p.page, p.candidates = page, cands
        except BlockedError as e:
            if not p.candidates:
                p.blocked, p.error = True, str(e)
        except FetchError as e:
            if not p.candidates:
                p.error = str(e) if not http_err else f"{http_err}; {e}"
    if not p.candidates and not p.error and not p.blocked:
        p.error = "Sayfada sürüm numarası bulunamadı"
    if p.blocked:
        p.error = (
            "Site otomatik kontrole izin vermiyor. “Sayfayı aç” ile bakıp gördüğünüz sürümü "
            "“Düzenle” → “En yeni (elle)” alanına yazabilirsiniz."
        )
    return p


def check_item(item: Item, browser: Browser) -> Item:
    """Kaydı yerinde günceller ve döner."""
    if item.installed_auto:
        v = system_bios().get("version")
        if v:
            item.installed = v
    item.last_checked = datetime.now().isoformat(timespec="seconds")
    p = probe(item.url, browser, need_chrome_if_empty=False)
    page_title = p.page.title[:80] if p.page and p.page.title and not p.blocked else ""
    if p.blocked or (p.error and not p.candidates):
        item.name = item.name or page_title or name_from_url(item.url)
        item.state = "blocked" if p.blocked else "error"
        item.message = p.error
        return item
    chosen, conf = pick_tracked(p.candidates, item.anchor)
    if chosen is None:
        # http ile bulunamadıysa Chrome ile bir kez daha dene
        if p.page and p.page.via == "http":
            try:
                page = browser.fetch(item.url)
                cands = extract_candidates(page.text, page.links)
                chosen, conf = pick_tracked(cands, item.anchor)
            except FetchError:
                chosen = None
    if chosen is None:
        item.state = "lost"
        item.message = "Takip edilen sürüm sayfada bulunamadı; sayfa değişmiş olabilir. Düzenle'den yeniden seçin."
        return item
    if not item.anchor:
        item.anchor = anchor_from(chosen)
    if not item.name:
        item.name = title_for(chosen, page_title) or page_title or name_from_url(item.url)
    item.latest = chosen.version
    item.latest_date = chosen.date
    item.link = chosen.link
    item.message = ""
    item.state = "new"
    item.recompute_state()
    return item
