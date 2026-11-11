"""Sayfa indirme: önce düz istek, gerekirse Chrome (arka planda, görünmez)."""
from __future__ import annotations

import html as htmlmod
import re
import time
from dataclasses import dataclass, field

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
_BLOCK_MARKERS = (
    "access denied",
    "you don't have permission to access",
    "attention required",
    "verify you are human",
    "are you a robot",
    "just a moment...",
)


class FetchError(Exception):
    pass


class BlockedError(FetchError):
    pass


@dataclass
class Page:
    url: str
    title: str
    text: str
    links: list[tuple[str, str]] = field(default_factory=list)
    via: str = "http"


def _is_blocked(text: str) -> bool:
    head = text[:1500].lower()
    return any(m in head for m in _BLOCK_MARKERS) and len(text) < 4000


def _html_to_text(raw: str) -> tuple[str, str, list[tuple[str, str]]]:
    title_m = re.search(r"<title[^>]*>(.*?)</title>", raw, re.I | re.S)
    title = htmlmod.unescape(re.sub(r"\s+", " ", title_m.group(1))).strip() if title_m else ""
    links = []
    for m in re.finditer(r"<a\b([^>]*)>(.*?)</a>", raw, re.I | re.S):
        hm = re.search(r"href\s*=\s*[\"']([^\"']+)", m.group(1), re.I)
        if hm:
            txt = re.sub(r"<[^>]+>", " ", m.group(2))
            links.append((htmlmod.unescape(txt).strip(), htmlmod.unescape(hm.group(1))))
    body = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", raw)
    body = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h\d|td|th|section|article|header|footer|span|a|button|label)>", "\n", body)
    body = re.sub(r"<[^>]+>", " ", body)
    text = htmlmod.unescape(body)
    return title, text, links


def fetch_http(url: str, timeout: int = 20) -> Page:
    try:
        r = requests.get(
            url,
            headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9,tr;q=0.8"},
            timeout=timeout,
        )
    except requests.RequestException as e:
        raise FetchError(f"Bağlantı kurulamadı: {e.__class__.__name__}") from e
    title, text, links = _html_to_text(r.text)
    if r.status_code in (401, 403, 429) or _is_blocked(text):
        raise BlockedError(f"Site isteği reddetti (HTTP {r.status_code})")
    if r.status_code >= 400:
        raise FetchError(f"Sayfa açılamadı (HTTP {r.status_code})")
    from urllib.parse import urljoin

    links = [(t, urljoin(r.url, h)) for t, h in links if not h.startswith(("#", "javascript:", "mailto:"))]
    return Page(url=url, title=title, text=text, links=links, via="http")


class Browser:
    """Tek bir görünmez Chrome örneği; yalnızca gerektiğinde açılır."""

    def __init__(self):
        self._driver = None

    def _ensure(self):
        if self._driver is None:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options

            o = Options()
            o.add_argument("--headless=new")
            o.add_argument("--window-size=1600,1000")
            o.add_argument("--log-level=3")
            try:
                self._driver = webdriver.Chrome(options=o)
            except Exception as e:  # noqa: BLE001
                raise FetchError(
                    "Chrome başlatılamadı. Google Chrome kurulu mu? (" + str(e).splitlines()[0][:120] + ")"
                ) from e
            self._driver.set_page_load_timeout(45)
        return self._driver

    def fetch(self, url: str, settle: float = 15.0) -> Page:
        d = self._ensure()
        try:
            d.get(url)
        except Exception as e:  # noqa: BLE001
            raise FetchError("Sayfa zaman aşımına uğradı") from e
        # İçerik JavaScript ile sonradan yükleniyorsa metin durulana kadar bekle
        last, stable, t0 = -1, 0, time.time()
        while time.time() - t0 < settle:
            time.sleep(1.0)
            n = d.execute_script("return document.body ? document.body.innerText.length : 0")
            stable = stable + 1 if n == last and n > 0 else 0
            last = n
            if stable >= 2 and time.time() - t0 > 3:
                break
        text = d.execute_script("return document.body ? document.body.innerText : ''") or ""
        title = d.title or ""
        links = d.execute_script(
            "return Array.from(document.querySelectorAll('a[href]')).map(a=>[(a.innerText||a.getAttribute('aria-label')||'').trim(), a.href]);"
        ) or []
        if _is_blocked(text):
            raise BlockedError("Site otomatik kontrole izin vermiyor")
        return Page(url=url, title=title, text=text, links=[tuple(x) for x in links], via="chrome")

    def close(self):
        if self._driver is not None:
            try:
                self._driver.quit()
            except Exception:  # noqa: BLE001
                pass
            self._driver = None
