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

from .extract import Candidate, anchor_from, page_candidates, is_newer, pick_tracked, same_version, title_for
from .fetch import BlockedError, Browser, FetchError, Page, fetch_http
from .i18n import _

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
    installed: str = ""  # yüklü sürüm (ya da elle girilmiş tarih)
    installed_date: str = ""  # yüklü olanın tarihi (sürücü tarihi, BIOS tarihi ya da kurulum tarihi), ISO
    installed_auto: bool = False  # BIOS: yüklü sürümü bilgisayardan oku
    installed_app: str = ""  # Windows "Yüklü uygulamalar" listesindeki ad; sürüm her kontrolde oradan okunur
    installed_device: str = ""  # Aygıt Yöneticisi'ndeki aygıt adı; sürücü sürümü/tarihi oradan okunur
    installed_dev_version: str = ""  # o aygıtın yüklü sürücü sürümü (ör. 1.0.0.0)
    pkg_version: str = ""  # sitedeki paketin içindeki sürücü sürümü (INF DriverVer)
    pkg_date: str = ""  # paketin içindeki sürücü tarihi (ISO)
    via: str = ""  # son kontrolde sayfa nasıl okundu: http | chrome | chrome-kimlik
    latest: str = ""
    latest_date: str = ""
    link: str = ""
    anchor: dict = field(default_factory=dict)
    state: str = "new"  # new | ok | update | noinstalled | nocompare | blocked | error | lost
    compared: str = ""  # son karar neye göre verildi: "version" | "date" | ""
    message: str = ""
    last_checked: str = ""
    added: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])

    # -- karşılaştırma: sürüm sürümle, tarih tarihle; çift yoksa karar verilmez

    def installed_pair(self) -> tuple[str, str]:
        """(yüklü sürüm, yüklü tarih)."""
        ver, dt = self.installed, self.installed_date
        if is_iso_date(ver):
            ver, dt = "", ver  # tarih olarak girilmiş
        if self.installed_device and self.installed_dev_version:
            ver = self.installed_dev_version
        return ver, dt

    def site_pair(self) -> tuple[str, str]:
        """(sitedeki sürüm, sitedeki tarih). Paketin içi okunduysa paketteki sürücü esas alınır."""
        if self.pkg_version:
            return self.pkg_version, self.pkg_date
        if self.anchor.get("shape") == "date" or is_iso_date(self.latest):
            return "", self.latest
        return self.latest, self.latest_date

    def recompute_state(self):
        if self.state in ("blocked", "error", "lost") and not self.latest:
            return
        sv, sd = self.site_pair()
        iv, idt = self.installed_pair()
        self.compared = ""
        if not (sv or sd):
            self.state = "new"
        elif not (iv or idt):
            self.state = "noinstalled"
        elif sv and iv:
            self.compared = "version"
            if is_newer(sv, iv):
                self.state = "update"
            elif same_version(sv, iv) and self.pkg_version and sd and idt and sd > idt:
                self.state = "update"  # paketteki sürücü aynı numaralı ama daha yeni tarihli
            else:
                self.state = "ok"
        elif sd and idt:
            self.compared = "date"
            self.state = "update" if sd > idt else "ok"
        else:
            # ör. sitede yalnızca tarih var, bilgisayarda yalnızca sürüm numarası
            self.state = "nocompare"


def is_iso_date(s: str) -> bool:
    import re

    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", s or ""))


class Store:
    def __init__(self, path: Path | None = None):
        self.path = path or (data_dir() / "items.json")
        self.items: list[Item] = []
        self.settings: dict = {"check_on_start": True, "identity_fallback": True}
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


_prog_cache: dict[str, str] | None = None
_GENERIC_WORDS = {
    "driver", "drivers", "software", "the", "for", "and", "download", "downloads", "package", "update",
    "utility", "tool", "tools", "windows", "win", "bit", "x64", "64", "latest", "version", "sürücü",
}


def installed_programs(refresh: bool = False) -> dict[str, str]:
    """Windows'un 'Yüklü uygulamalar' listesi: {ad: sürüm}."""
    global _prog_cache
    if _prog_cache is not None and not refresh:
        return _prog_cache
    out: dict[str, str] = {}
    if os.name == "nt":
        import winreg

        roots = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]
        for hive, path in roots:
            try:
                root = winreg.OpenKey(hive, path)
            except OSError:
                continue
            for i in range(winreg.QueryInfoKey(root)[0]):
                try:
                    sub = winreg.OpenKey(root, winreg.EnumKey(root, i))
                    name = str(winreg.QueryValueEx(sub, "DisplayName")[0]).strip()
                    ver = str(winreg.QueryValueEx(sub, "DisplayVersion")[0]).strip()
                except OSError:
                    continue
                if name and ver and name not in out:
                    out[name] = ver
                    try:
                        d = str(winreg.QueryValueEx(sub, "InstallDate")[0]).strip()  # YYYYMMDD
                        if len(d) == 8 and d.isdigit():
                            _prog_dates[name] = f"{d[:4]}-{d[4:6]}-{d[6:]}"
                    except OSError:
                        pass
    _prog_cache = dict(sorted(out.items(), key=lambda kv: kv[0].lower()))
    return _prog_cache


_prog_dates: dict[str, str] = {}


def installed_program_date(name: str) -> str:
    """Programın Windows'a kurulduğu tarih (ISO); kayıtta yoksa boş."""
    installed_programs()
    return _prog_dates.get(name, "")


def installed_info(item: Item) -> None:
    """Seçilen kaynaktan (BIOS / yüklü program / Aygıt Yöneticisi) yüklü sürümü ve tarihini oku."""
    if item.installed_auto:
        b = system_bios()
        if b.get("version"):
            item.installed, item.installed_date = b["version"], b.get("date", "")
    elif item.installed_app:
        v = installed_programs().get(item.installed_app)
        if v:
            item.installed, item.installed_date = v, installed_program_date(item.installed_app)
    elif item.installed_device:
        dev = system_devices().get(item.installed_device)
        if dev:
            item.installed, item.installed_date = dev["version"], dev["date"]
            item.installed_dev_version = dev["version"]


_dev_cache: dict[str, dict] | None = None


def system_devices(refresh: bool = False) -> dict[str, dict]:
    """Aygıt Yöneticisi'ndeki (Microsoft dışı) sürücüler: {aygıt adı: {version, date, provider}}."""
    global _dev_cache
    if _dev_cache is not None and not refresh:
        return _dev_cache
    out: dict[str, dict] = {}
    if os.name == "nt":
        ps = (
            "Get-CimInstance Win32_PnPSignedDriver | Where-Object { $_.DeviceName -and $_.DriverProviderName "
            "-and $_.DriverProviderName -ne 'Microsoft' } | ForEach-Object { [pscustomobject]@{ n=$_.DeviceName; "
            "v=$_.DriverVersion; p=$_.DriverProviderName; d=$(if ($_.DriverDate) { $_.DriverDate.ToString('yyyy-MM-dd') } else { '' }) } } "
            "| ConvertTo-Json -Compress"
        )
        try:
            raw = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                capture_output=True, text=True, encoding="utf-8", timeout=40,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout
            rows = json.loads(raw) if raw.strip() else []
            if isinstance(rows, dict):
                rows = [rows]
            for r in rows:
                name = (r.get("n") or "").strip()
                if not name:
                    continue
                entry = {"version": (r.get("v") or "").strip(), "date": r.get("d") or "", "provider": r.get("p") or ""}
                # aynı adlı birden fazla aygıt varsa en yeni sürücü tarihlisini tut
                if name not in out or entry["date"] > out[name]["date"]:
                    out[name] = entry
        except Exception:  # noqa: BLE001
            pass
    _dev_cache = dict(sorted(out.items(), key=lambda kv: kv[0].lower()))
    return _dev_cache


def suggest_device(name: str, devices: dict[str, dict] | None = None) -> str:
    """'ASUS_XG27ACSR_WHQL_Driver' → 'ROG STRIX XG27ACSR' (model numarası eşleşmesi)."""
    devices = system_devices() if devices is None else devices
    want = _words(name.replace("_", " "))
    # model numarası gibi (harf + rakam, en az 5 karakter) sözcükler tek başına yeterli
    models = {w for w in want if len(w) >= 5 and any(ch.isdigit() for ch in w) and any(ch.isalpha() for ch in w)}
    best, best_key = "", (0, 0)
    for dev in devices:
        have = _words(dev)
        common = want & have
        if not (common & models or len(common) >= 2):
            continue
        key = (len(common & models), len(common))
        if key > best_key:
            best, best_key = dev, key
    return best


PKG_MAX_BYTES = 30 * 1024 * 1024  # yalnızca küçük sürücü paketleri indirilir


def package_driver_info(link: str, model_hint: str = "", site_date: str = "") -> dict | None:
    """Sitedeki .zip paketini indirip içindeki .inf dosyasından DriverVer'i okur.

    Hiçbir dosya çalıştırılmaz ya da diske açılmaz; yalnızca .inf metni okunur.
    Sonuç aynı link için önbellekte tutulur (paket değişince link ya da sitedeki tarih değişir).
    """
    import io
    import re
    import zipfile

    import requests

    from .fetch import UA

    if not link.lower().split("?")[0].endswith(".zip"):
        return None
    cache_path = data_dir() / "packages.json"
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    key = f"{link}|{site_date}"  # ASUS aynı adla yeniden yayınlıyor; tarih değişince yeniden bak
    if key in cache:
        return cache[key] or None
    info = None
    try:
        with requests.get(link, headers={"User-Agent": UA}, timeout=30, stream=True) as r:
            r.raise_for_status()
            if int(r.headers.get("content-length") or 0) > PKG_MAX_BYTES:
                return None
            buf = io.BytesIO()
            for chunk in r.iter_content(65536):
                buf.write(chunk)
                if buf.tell() > PKG_MAX_BYTES:
                    return None
        z = zipfile.ZipFile(buf)
        infs = [n for n in z.namelist() if n.lower().endswith(".inf")]
        # birden fazla .inf varsa adında model numarası geçeni öne al
        tokens = re.findall(r"[a-z]+\d+[a-z\d]*|\d+[a-z]+[a-z\d]*", model_hint.lower())
        infs.sort(key=lambda n: not any(t in n.lower() for t in tokens))
        for name in infs:
            raw = z.read(name)
            enc = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8"
            m = re.search(r"DriverVer\s*=\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*,\s*([\d.]+)", raw.decode(enc, errors="replace"), re.I)
            if m:
                mo, da, yr, ver = m.groups()
                info = {"version": ver, "date": f"{yr}-{int(mo):02d}-{int(da):02d}", "inf": name.rsplit("/", 1)[-1]}
                break
    except Exception:  # noqa: BLE001
        return None
    cache[key] = info or {}
    try:
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    return info


def _words(s: str) -> set[str]:
    import re

    return {w for w in re.split(r"[^0-9a-zçğıöşü]+", s.lower()) if len(w) >= 3 and w not in _GENERIC_WORDS}


def suggest_program(name: str, latest: str = "", programs: dict[str, str] | None = None) -> str:
    """Kaydın adına en çok benzeyen yüklü program ('AMD Chipset Drivers' → 'AMD Chipset Software')."""
    programs = installed_programs() if programs is None else programs
    want = _words(name)
    if len(want) < 2:
        return ""
    best, best_key = "", (0, 0, 0)
    for prog, ver in programs.items():
        have = _words(prog)
        common = len(want & have)
        if common < 2:
            continue
        # aynı biçimde sürüm (aynı sayıda nokta) olanı ve sitedekiyle aynı ya da daha eski olanı öne al
        same_shape = int(bool(latest) and ver.count(".") == latest.count("."))
        key = (common, same_shape, -len(have - want))
        if key > best_key:
            best, best_key = prog, key
    return best


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
        p.candidates = page_candidates(p.page.text, p.page.links, p.page.files, p.page.data_text)
    except BlockedError as e:
        http_err = str(e)
    except FetchError as e:
        http_err = str(e)
    if p.candidates and not need_chrome_if_empty:
        return p
    # Düz okumada güçlü bir aday yoksa içerik büyük olasılıkla JavaScript ile yükleniyordur
    weak = not p.candidates or p.candidates[0].score < 5
    if weak or "#" in url:
        try:
            page = browser.fetch(url)
            cands = page_candidates(page.text, page.links, page.files, page.data_text)
            best_http = p.candidates[0].score if p.candidates else -99
            if (cands and cands[0].score >= best_http) or not p.page:
                p.page, p.candidates = page, cands
        except BlockedError as e:
            if not p.candidates:
                p.blocked, p.error = True, str(e)
        except FetchError as e:
            if not p.candidates:
                p.error = str(e) if not http_err else f"{http_err}; {e}"
    if not p.candidates and not p.error and not p.blocked:
        p.error = _("No version number found on the page")
    if p.blocked:
        p.error = _(
            "The site does not allow automatic checks. Look with “Open page” and type the version you see into "
            "“Edit” → “Latest (manual)”."
        )
    return p


def check_item(item: Item, browser: Browser) -> Item:
    """Kaydı yerinde günceller ve döner."""
    installed_info(item)
    item.last_checked = datetime.now().isoformat(timespec="seconds")
    p = probe(item.url, browser, need_chrome_if_empty=False)
    item.via = p.page.via if p.page else ""
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
                cands = page_candidates(page.text, page.links, page.files, page.data_text)
                chosen, conf = pick_tracked(cands, item.anchor)
                item.via = page.via
            except FetchError:
                chosen = None
    if chosen is None:
        item.state = "lost"
        item.message = _("The tracked version was not found on the page; the page may have changed. Pick it again under “Edit”.")
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
    update_package_info(item)
    item.recompute_state()
    return item


def update_package_info(item: Item):
    """Tarihle takip edilen, Aygıt Yöneticisi'ne bağlı sürücülerde paketin içindeki sürümü oku."""
    item.pkg_version = item.pkg_date = ""
    if not (item.installed_device and item.anchor.get("shape") == "date" and item.link):
        return
    info = package_driver_info(item.link, item.name + " " + item.installed_device, item.latest)
    if info:
        item.pkg_version, item.pkg_date = info["version"], info["date"]
