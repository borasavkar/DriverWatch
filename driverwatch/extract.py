"""Sayfa metninden sürüm, tarih ve indirme linki çıkarma.

Eski uygulamanın sorunu sayfadaki ilk sayı benzeri ifadeyi sürüm sanmasıydı.
Burada her aday sürüm, bulunduğu satır ve bir önceki satırla birlikte
"bağlam" olarak saklanır. Kullanıcı eklerken doğru adayı seçer; sonraki
kontrollerde aynı bağlamdaki adaylar arasından en yüksek sürüm alınır.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from datetime import date

# ---------------------------------------------------------------- tarih

_MONTHS = {
    m: i + 1
    for i, names in enumerate([
        ("jan", "january", "oca", "ocak"), ("feb", "february", "şub", "şubat", "sub", "subat"),
        ("mar", "march", "mart"), ("apr", "april", "nis", "nisan"),
        ("may", "mayıs", "mayis"), ("jun", "june", "haz", "haziran"),
        ("jul", "july", "tem", "temmuz"), ("aug", "august", "ağu", "ağustos", "agu", "agustos"),
        ("sep", "sept", "september", "eyl", "eylül", "eylul"), ("oct", "october", "eki", "ekim"),
        ("nov", "november", "kas", "kasım", "kasim"), ("dec", "december", "ara", "aralık", "aralik"),
    ])
    for m in names
}
_MON = r"[A-Za-zÇĞİÖŞÜçğıöşü]{3,9}\.?"
_DATE_RES = [
    (re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b"), "dmy_or_mdy"),
    (re.compile(r"\b(\d{1,2})[-\s](" + _MON + r")[-\s,]+(\d{4})\b"), "d_mon_y"),
    (re.compile(r"\b(" + _MON + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b"), "mon_d_y"),
]


def _mk(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def find_dates(text: str) -> list[tuple[int, int, date]]:
    """(başlangıç, bitiş, tarih) listesi döner."""
    out: list[tuple[int, int, date]] = []
    for rx, kind in _DATE_RES:
        for m in rx.finditer(text):
            g = m.groups()
            dt = None
            if kind == "ymd":
                dt = _mk(int(g[0]), int(g[1]), int(g[2]))
            elif kind == "dmy_or_mdy":
                a, b, y = int(g[0]), int(g[1]), int(g[2])
                sep = text[m.start() + len(g[0])]
                # "/" çoğunlukla ABD biçimi (AA/GG/YYYY), "." Türkçe/Avrupa (GG.AA.YYYY)
                if sep == "/" and a <= 12 and b > 12:
                    dt = _mk(y, a, b)
                elif sep == "/" and a > 12:
                    dt = _mk(y, b, a)
                elif sep == "/":
                    dt = _mk(y, a, b)
                else:
                    dt = _mk(y, b, a)
            elif kind == "d_mon_y":
                mon = _MONTHS.get(g[1].rstrip(".").lower())
                dt = _mk(int(g[2]), mon, int(g[0])) if mon else None
            else:
                mon = _MONTHS.get(g[0].rstrip(".").lower())
                dt = _mk(int(g[2]), mon, int(g[1])) if mon else None
            if dt and 1995 <= dt.year <= 2100:
                out.append((m.start(), m.end(), dt))
    return out


# ---------------------------------------------------------------- sürüm

# 8.09.28.1124 · v2.04.00_r1 · 32.0.101.6881 · Version 1.2
_VER_DOTTED = re.compile(
    r"(?<![\w.\-/])([vV]?\d{1,4}(?:\.\d{1,6}){1,4}(?:[_\-]?[a-zA-Z]{1,3}\d{0,3})?)(?![\w.]*\d)(?!\.\w)"
)
# MSI biçimi: 7E16v1D4, 7E16v1CC
_VER_MSI = re.compile(r"(?<![\w])([0-9A-Z]{4}v[0-9A-Z]{2,5})(?![\w])")
# Etiketli sürüm: "Sürüm MCM102", "Version: 0302", "Rev. A12" — etiketten sonraki ilk sözcük
_VER_LABELED = re.compile(
    r"(?:\bversion|\bsürüm|\bsurum|\bver\.?|\brevision|\brev\.?|\bfirmware version)\s*[:#]?\s*"
    r"(?![vV]?\d{1,4}(?:\.\d)+\b)([A-Za-z0-9][A-Za-z0-9_.\-]{1,29})(?![\w])",
    re.IGNORECASE,
)
_LABEL_STOP = {"history", "notes", "number", "numarası", "bilgisi", "info", "date", "tarihi", "details", "seçin", "select"}

_KEYWORDS = re.compile(
    r"version|ver\.|sürüm|surum|firmware|driver|sürücü|bios|updater|release|chipset|software|"
    r"package|update|güncelle|download|indir|\bv\d",
    re.IGNORECASE,
)
_NOISE = re.compile(r"copyright|©|all rights reserved|cookie|privacy|telif", re.IGNORECASE)
_URL = re.compile(r"https?://[^\s|\"'<>]+")
_UNIT_AFTER = re.compile(r"\s*(?:mb|gb|kb|tb|bytes?|ghz|mhz|hz|mm|cm|inch|inç|in\b|\"|”)(?![a-z])|\s*%", re.IGNORECASE)


@dataclass
class Candidate:
    version: str
    line: str
    prev: str
    template: str  # satırın sürüm yerine {V} konmuş hali
    index: int  # sayfadaki sırası
    after: str = ""  # sonraki birkaç satır (aynı kutudaki etiketler)
    score: float = 0.0
    date: str = ""  # ISO
    link: str = ""
    shape: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def by_date(self) -> bool:
        return self.shape == "date"

    def context_label(self) -> str:
        """Kullanıcıya gösterilecek kısa açıklama."""
        parts = [p for p in self.prev.split(" | ")[-2:] if p] + [self.line]
        s = "  ›  ".join(parts)
        return s if len(s) <= 140 else s[:137] + "…"


def shape_of(v: str) -> str:
    v = v.strip()
    if _VER_MSI.fullmatch(v):
        return "msi"
    pre = "v" if v[:1] in "vV" else ""
    return f"{pre}{v.count('.') + 1}"


def version_key(v: str) -> tuple:
    """Karşılaştırma anahtarı: '8.09.28.1124' > '8.02.18.557'."""
    s = v.strip()
    m = re.fullmatch(r"[0-9A-Za-z]{4}v(.+)", s)  # MSI önekini at
    if m:
        s = m.group(1)
    s = re.sub(r"^[vV](?=\d)", "", s)
    key = []
    for tok in re.findall(r"\d+|[A-Za-z]+", s):
        if tok.isdigit():
            key.append((1, int(tok), ""))
        else:
            key.append((0, 0, tok.lower()))
    return tuple(key)


def same_version(a: str, b: str) -> bool:
    """'1.D4' (Windows'tan okunan) ile '7E16v1D4' (MSI sitesi) aynı sayılır."""
    if not a or not b:
        return False
    if version_key(a) == version_key(b):
        return True
    na = re.sub(r"[^0-9a-z]", "", a.lower())
    nb = re.sub(r"[^0-9a-z]", "", b.lower())
    if not na or not nb:
        return False
    if na == nb:
        return True
    short, long_ = sorted((na, nb), key=len)
    return len(short) >= 2 and long_.endswith(short) and not long_[-len(short) - 1].isdigit()


def is_newer(latest: str, installed: str) -> bool:
    if not latest or not installed or same_version(latest, installed):
        return False
    return version_key(latest) > version_key(installed)


def _looks_like_date(v: str) -> bool:
    core = v.lstrip("vV")
    parts = core.split(".")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        a, b, c = (int(p) for p in parts)
        if (1995 <= a <= 2100 and 1 <= b <= 12 and 1 <= c <= 31) or (
            1995 <= c <= 2100 and 1 <= b <= 12 and 1 <= a <= 31
        ):
            return True
    return False


def _clean_lines(text: str) -> list[str]:
    lines = []
    for raw in text.replace("\r", "\n").split("\n"):
        s = re.sub(r"\s+", " ", raw).strip()
        if s:
            lines.append(s)
    return lines


_DATE_KW = re.compile(r"\bdate\b|tarih|\breleased?\b|yayın|\bupdated\b|güncellen", re.IGNORECASE)
_LABEL_START = (
    "revision", "version", "sürüm", "surum", "ver.", "release", "file size", "boyut", "download", "indir",
    "applicable", "driver details", "sha-", "md5", "date", "tarih", "updated", "description", "açıklama",
)
_SIZE_LINE = re.compile(r"^[\d.,]+\s*(?:kb|mb|gb|bytes?)$", re.IGNORECASE)


def title_for(c: "Candidate", page_title: str = "") -> str:
    """Sürümün hemen üstündeki başlık satırı: 'AMD Chipset Drivers', 'ASUS_XG27ACSR_WHQL_Driver' gibi."""
    for line in reversed(c.prev.split(" | ")):
        low = line.lower().strip()
        if (
            len(line) <= 3
            or any(low.startswith(k) for k in _LABEL_START)
            or _SIZE_LINE.match(low)
            or find_dates(line)
            or low.endswith(" -")
        ):
            continue
        return line[:80] if len(line) < 70 else page_title
    return page_title


def _norm(s: str) -> str:
    return re.sub(r"[^0-9a-z]", "", s.lower())


def find_link_by_title(title: str, links: list[tuple[str, str]], files: list[str]) -> str:
    """Başlığı ('ASUS_XG27ACSR_WHQL_Driver') linkin metninde, adresinde ya da sayfadaki dosya adlarında ara."""
    t = _norm(title)
    if len(t) < 6:
        return ""
    for f in files:
        if t in _norm(f.rsplit("/", 1)[-1]):
            return f
    for text, href in links:
        if href.startswith(("http://", "https://")) and (t in _norm(text) or t in _norm(href)):
            return href
    return ""


def extract_candidates(
    text: str, links: list[tuple[str, str]] | None = None, files: list[str] | None = None
) -> list[Candidate]:
    links, files = links or [], files or []
    lines = _clean_lines(text)
    cands: list[Candidate] = []
    seen: set[tuple[str, str]] = set()
    version_lines: list[int] = []
    idx = 0

    def ctx(i):
        prev = " | ".join(x[:100] for x in lines[max(0, i - 3):i])
        after = " | ".join(x[:100] for x in lines[i + 1:i + 7])
        return prev, after

    for i, line in enumerate(lines):
        if _NOISE.search(line) or len(line) > 400:
            continue
        found = []
        for m in _VER_DOTTED.finditer(line):
            a = m.start(1)
            # uzun cümlenin içindeki sayı ("USB 3.0, 3.1, 3.2 ...") sürüm değildir; hemen önünde etiket olmalı
            if len(line) > 80 and not _KEYWORDS.search(line[max(0, a - 25):a]):
                continue
            found.append((a, m.end(1), m.group(1), False))
        found += [(m.start(1), m.end(1), m.group(1), False) for m in _VER_MSI.finditer(line)]
        taken = [(a, b) for a, b, *_ in found]
        for m in _VER_LABELED.finditer(line):
            v = m.group(1).rstrip(".-_")
            if (
                len(line) > 80
                or v.lower() in _LABEL_STOP
                or not re.search(r"\d", v)
                or any(m.start(1) < y and m.end(1) > x for x, y in taken)
            ):
                continue
            found.append((m.start(1), m.start(1) + len(v), v, True))
        date_spans = [(a, b) for a, b, _ in find_dates(line)]
        url_spans = [(m.start(), m.end()) for m in _URL.finditer(line)]
        for a, b, v, labeled in found:
            if any(a >= x and b <= y for x, y in date_spans + url_spans):
                continue
            if _looks_like_date(v) or _UNIT_AFTER.match(line, b):
                continue
            version_lines.append(i)
            prev, after = ctx(i)
            key = (v, _generic(prev + line + after))
            if key in seen:
                continue
            seen.add(key)
            c = Candidate(
                version=v,
                line=line[:200],
                prev=prev,
                template=line[:a] + "{V}" + line[b:],
                index=idx,
                after=after,
                shape="label" if labeled else shape_of(v),
            )
            idx += 1
            # tarih: aynı satır, sonra sonraki satırlar, sonra önceki satır
            for j in (i, i + 1, i + 2, i + 3, i + 4, i - 1):
                if 0 <= j < len(lines):
                    ds = find_dates(lines[j])
                    if ds:
                        c.date = ds[0][2].isoformat()
                        break
            # link: satırdaki ya da sonraki satırlardaki adres, sonra sürümü içeren href, sonra başlık
            for j in (i, i + 1, i + 2):
                if 0 <= j < len(lines):
                    um = _URL.search(lines[j])
                    if um:
                        c.link = um.group(0).rstrip(".,);")
                        break
            if not c.link:
                c.link = find_link_for(v, links + [("", f) for f in files])
            if not c.link:
                c.link = find_link_by_title(title_for(c), links, files)
            c.score = _score(c, line, prev)
            cands.append(c)

    # Sürüm numarası olmayan kalemler (ör. ASUS "Sürüm -"): yayın tarihiyle takip
    for i, line in enumerate(lines):
        if _NOISE.search(line) or len(line) > 120:
            continue
        if any(i - 6 <= vl <= i for vl in version_lines):
            continue  # bu tarih zaten bir sürüm numarasına ait
        ds = find_dates(line)
        if not ds:
            continue
        a, b, dt = ds[0]
        rest = (line[:a] + line[b:]).strip(" :|-·")
        prev, after = ctx(i)
        if len(rest) > 40 and not _DATE_KW.search(line):
            continue  # cümle içindeki tarih, kalem değil
        v = dt.isoformat()
        key = (v, _generic(prev + line + after))
        if key in seen:
            continue
        seen.add(key)
        c = Candidate(
            version=v, line=line[:200], prev=prev, template=line[:a] + "{V}" + line[b:],
            index=idx, after=after, shape="date", date=v,
        )
        idx += 1
        title = title_for(c)
        if not title:
            continue  # neyin tarihi olduğu belli değil
        c.link = find_link_by_title(title, links, files)
        if not c.link:
            for j in (i, i + 1, i + 2, i + 3):
                um = _URL.search(lines[j]) if j < len(lines) else None
                if um:
                    c.link = um.group(0).rstrip(".,);")
                    break
        c.score = 1.0 + (1.5 if _DATE_KW.search(line + " " + prev) else 0) + (1 if title else -1) + (2 if c.link else 0)
        c.score -= min(c.index, 40) * 0.02
        cands.append(c)

    cands.sort(key=lambda c: (-c.score, c.index))
    return cands


def page_candidates(text: str, links, files, data_text: str = "") -> list[Candidate]:
    """Görünen metindeki adaylar + yalnızca gömülü veride olan (tarihli, başlıklı) kalemler."""
    cands = extract_candidates(text, links, files)
    if not data_text:
        return cands
    have = {_norm(title_for(c)) for c in cands}
    have_v = {c.version for c in cands}
    extra = []
    for c in extract_candidates(data_text, links, files):
        t = _norm(title_for(c))
        if not c.date or len(t) < 6 or t in have or (c.version in have_v and not c.by_date):
            continue
        have.add(t)
        c.extra["src"] = "data"
        c.score -= 1.5
        c.index += 10000
        extra.append(c)
    out = cands + extra
    out.sort(key=lambda c: (-c.score, c.index))
    return out


def find_link_for(version: str, links: list[tuple[str, str]]) -> str:
    core = version.lstrip("vV").lower()
    if len(core.replace(".", "")) < 4:
        return ""  # "3.1" gibi kısa sayılar her adreste geçebilir
    variants = {core, core.replace(".", "_")} | ({core.replace(".", "")} if len(core.replace(".", "")) >= 5 else set())
    for _text, href in links:
        # yalnızca dosya adında ara (ürün sayfasının adresindeki sayılar sayılmasın)
        name = href.lower().split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]
        if any(v in name for v in variants):
            return href
    return ""


def _score(c: Candidate, line: str, prev: str) -> float:
    s = 0.0
    if _KEYWORDS.search(line):
        s += 3
    elif _KEYWORDS.search(prev.split(" | ")[-1] if prev else ""):
        s += 2.5
    elif _KEYWORDS.search(prev):
        s += 1
    if c.date:
        s += 2
    if c.link:
        s += 2
    if c.shape in ("msi", "label"):
        s += 3
    else:
        n = c.version.count(".") + 1
        s += {2: 0, 3: 1.5, 4: 2}.get(n, 2)
        if c.version[:1] in "vV":
            s += 1
    if len(line) <= len(c.version) + 40:
        s += 1  # kısa satır: büyük olasılıkla bir başlık/etiket
    s -= min(c.index, 40) * 0.03
    return s


# ---------------------------------------------------------------- takip

def _sim(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _generic(template: str) -> str:
    """Satırdaki diğer sayıları da yok say (tarih, boyut değişebilir)."""
    t = _VER_DOTTED.sub("#", template)
    t = re.sub(r"\d+", "#", t)
    return t


def _last2(prev: str) -> str:
    return " | ".join(prev.split(" | ")[-2:])


def pick_tracked(cands: list[Candidate], anchor: dict) -> tuple[Candidate | None, float]:
    """Kaydedilmiş bağlama en çok benzeyen adaylar arasından en yeni sürümü seç."""
    if not cands:
        return None, 0.0
    if not anchor:
        return cands[0], 1.0
    at = _generic(anchor.get("template", ""))
    ap = _generic(anchor.get("prev", ""))
    aa = _generic(anchor.get("after", ""))
    ashape = anchor.get("shape", "")
    scored = []
    for c in cands:
        cp = _generic(c.prev)
        psim = 0.6 * _sim(_last2(cp), _last2(ap)) + 0.4 * _sim(cp, ap)
        m = 0.35 * _sim(_generic(c.template), at) + 0.25 * psim
        m += 0.25 * _sim(_generic(c.after), aa) if "after" in anchor else 0.25 * psim
        m += 0.15 if c.shape == ashape else 0.0
        scored.append((m, c))
    best = max(m for m, _ in scored)
    if best < 0.55:
        return None, best
    pool = [c for m, c in scored if m >= best - 0.06 and c.shape == ashape] or [
        c for m, c in scored if m >= best - 0.06
    ]
    top = max(pool, key=lambda c: version_key(c.version))
    return top, best


def anchor_from(c: Candidate) -> dict:
    return {"template": c.template, "prev": c.prev, "after": c.after, "shape": c.shape}
