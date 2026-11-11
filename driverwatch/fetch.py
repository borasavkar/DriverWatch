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
    files: list[str] = field(default_factory=list)  # sayfa kaynağındaki indirilebilir dosya adresleri
    data_text: str = ""  # sayfanın gömülü verisindeki (JSON) metinler, satır satır


_JS_STR = re.compile(r'"((?:[^"\\\n]|\\.)*)"')  # uzunluk sınırı yok: tırnak eşleşmesi kaymasın


def data_text_of(raw: str) -> str:
    """<script> içindeki gömülü verideki metinleri sırayla çıkar.

    Bazı siteler (ör. ASUS) ikinci dosyanın tarihini ya da linkini ekrana basmadan
    yalnızca bu veride tutuyor.
    """
    out: list[str] = []
    for m in re.finditer(r"(?is)<script\b[^>]*>(.*?)</script>", raw):
        body = m.group(1)
        if len(body) < 2000:
            continue
        for sm in _JS_STR.finditer(body):
            s = sm.group(1).replace("\\u002F", "/").replace("\\/", "/")
            if not (2 <= len(s) <= 160) or "\\u" in s or "{" in s or "<" in s:
                continue
            out.append(s)
            if len(out) > 60000:
                break
    return "\n".join(out)


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


_EXT = r"(?:zip|exe|7z|msi|cab|rar|bin|cap|rom|inf|tar\.gz)"
_ABS_FILE = re.compile(r"https?://[^\"'<>\s\\]+?\." + _EXT + r"(?=[\"'<>\s?#\\]|$)", re.I)
_REL_FILE = re.compile(r"[\"'](/[^\"'<>]{3,300}?\." + _EXT + r")[\"']", re.I)


def find_files(raw: str, page_url: str) -> list[str]:
    """Düğmelerin arkasında (JavaScript verisinde) duran dosya adreslerini topla."""
    from urllib.parse import quote, urlparse

    raw = raw.replace("\\u002F", "/").replace("\\/", "/").replace("&amp;", "&")
    out: list[str] = []
    for m in _ABS_FILE.finditer(raw):
        out.append(m.group(0))
    # göreli yollar için indirme sunucusunu tahmin et (ör. ASUS: dlcdnets.asus.com)
    hosts: dict[str, int] = {}
    for m in re.finditer(r"https?://([a-z0-9.-]+)/", raw, re.I):
        h = m.group(1).lower()
        if any(k in h for k in ("dl", "download", "drivers")):
            hosts[h] = hosts.get(h, 0) + 1
    pu = urlparse(page_url)
    fallback = f"https://{max(hosts, key=hosts.get)}" if hosts else f"{pu.scheme}://{pu.netloc}"
    for m in _REL_FILE.finditer(raw):
        path = m.group(1)
        if path.startswith("//"):
            continue
        # aynı ilk klasörle başlayan mutlak adresler hangi sunucudaysa onu kullan (/pub/… → dlcdnets)
        first = "/" + path.strip("/").split("/", 1)[0] + "/"
        same = re.findall(r"https?://([a-z0-9.-]+)" + re.escape(first), raw, re.I)
        base = f"https://{max(set(same), key=same.count).lower()}" if same else fallback
        out.append(base + quote(path, safe="/-_.~%"))
    seen, uniq = set(), []
    for f in out:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
    return uniq[:500]


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
    return Page(
        url=url, title=title, text=text, links=links, via="http",
        files=find_files(r.text, r.url), data_text=data_text_of(r.text),
    )


_API_HINT = re.compile(r"bios|driver|firmware|download|support|software|utility|file", re.I)


def fetch_api_texts(urls: list[str], limit: int = 8) -> str:
    """Sayfanın yüklediği, indirmeyle ilgili görünen veri yanıtlarını metin olarak döndür."""
    out = []
    for u in [u for u in urls if _API_HINT.search(u)][:limit]:
        try:
            r = requests.get(u, headers={"User-Agent": UA}, timeout=10)
        except requests.RequestException:
            continue
        if r.ok and len(r.content) < 3_000_000 and "json" in r.headers.get("content-type", "") + u.lower():
            out.append(r.text)
    return "\n".join(out)


class Browser:
    """Görünmez Chrome; yalnızca gerektiğinde açılır.

    allow_identity açıksa ve bir site görünmez Chrome'u reddederse ("HeadlessChrome" kimliği),
    sayfa bir kez daha, Chrome'un kendisini normal masaüstü Chrome olarak tanıttığı ikinci bir
    örnekle açılır (eski Gemini uygulamasının kullandığı yöntem). Kullanıcı ayarlardan kapatabilir.
    """

    def __init__(self, allow_identity: bool = False):
        self.allow_identity = allow_identity
        self._driver = None
        self._driver_id = None
        self._version = ""

    def _start(self, identity: bool):
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        o = Options()
        o.add_argument("--headless=new")
        o.add_argument("--window-size=1600,1000")
        o.add_argument("--log-level=3")
        if identity:
            ver = self._version or "130.0.0.0"
            o.add_argument(
                f"--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                f"(KHTML, like Gecko) Chrome/{ver} Safari/537.36"
            )
        try:
            d = webdriver.Chrome(options=o)
        except Exception as e:  # noqa: BLE001
            raise FetchError(
                "Chrome başlatılamadı. Google Chrome kurulu mu? (" + str(e).splitlines()[0][:120] + ")"
            ) from e
        d.set_page_load_timeout(45)
        if not self._version:
            # kurulu Chrome'un gerçek sürümü; kimlikte de bu kullanılır
            self._version = (d.capabilities or {}).get("browserVersion", "") or ""
        return d

    def _ensure(self, identity: bool = False):
        if identity:
            if self._driver_id is None:
                if not self._version:
                    self._ensure(False)
                self._driver_id = self._start(True)
            return self._driver_id
        if self._driver is None:
            self._driver = self._start(False)
        return self._driver

    def fetch(self, url: str, settle: float = 15.0) -> Page:
        try:
            return self._fetch_with(self._ensure(False), url, settle, "chrome")
        except BlockedError:
            if not self.allow_identity:
                raise
        return self._fetch_with(self._ensure(True), url, settle, "chrome-kimlik")

    def _fetch_with(self, d, url: str, settle: float, via: str) -> Page:
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
            "return Array.from(document.querySelectorAll('a[href]')).map(a=>[((a.innerText||'')+' '+(a.getAttribute('aria-label')||'')).trim(), a.href]);"
        ) or []
        if _is_blocked(text):
            raise BlockedError("Site otomatik kontrole izin vermiyor")
        try:
            src = d.page_source or ""
            # Sayfanın arka planda kendisinin çağırdığı veri adreslerini (ör. ASUS GetPDBIOS) de oku:
            # indirme düğmesinin adresi çoğu zaman yalnızca bu yanıtlarda bulunur.
            api = d.execute_script(
                "return performance.getEntriesByType('resource')"
                ".filter(r=>r.initiatorType==='xmlhttprequest'||r.initiatorType==='fetch').map(r=>r.name)"
            ) or []
            src += "\n" + fetch_api_texts(api)
            files, data = find_files(src, d.current_url or url), data_text_of(src)
        except Exception:  # noqa: BLE001
            files, data = [], ""
        return Page(
            url=url, title=title, text=text, links=[tuple(x) for x in links], via=via,
            files=files, data_text=data,
        )

    def close(self):
        for d in (self._driver, self._driver_id):
            if d is not None:
                try:
                    d.quit()
                except Exception:  # noqa: BLE001
                    pass
        self._driver = self._driver_id = None


