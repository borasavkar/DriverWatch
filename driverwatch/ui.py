"""PyQt6 arayüzü."""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, QTimer, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from . import __version__
from .core import (
    KINDS, Item, Probe, Store, check_item, guess_kind, installed_programs, probe, suggest_device, suggest_program,
    system_bios, system_devices,
)
from .extract import find_dates, title_for
from .extract import anchor_from, is_newer, same_version
from .fetch import Browser

# ---------------------------------------------------------------- görünüm

C = {
    "bg": "#14171c", "panel": "#1d2128", "panel2": "#252a33", "line": "#323844",
    "text": "#e8ebf0", "muted": "#9aa3b2", "accent": "#4c8dff",
    "green": "#2fbf71", "green_bg": "#163a28", "red": "#ff5a4f", "red_bg": "#45201d",
    "amber": "#f0b429", "amber_bg": "#3d3214", "blue": "#5aa9ff", "blue_bg": "#18304d",
    "gray": "#8b95a5", "gray_bg": "#2a303a",
}

STATES = {
    # durum: (rozet metni, renk, arka plan, sıralama)
    "update": ("YENİ SÜRÜM VAR", C["red"], C["red_bg"], 0),
    "lost": ("SÜRÜM BULUNAMADI", C["amber"], C["amber_bg"], 1),
    "blocked": ("SİTE ENGELLİYOR", C["amber"], C["amber_bg"], 2),
    "error": ("KONTROL EDİLEMEDİ", C["amber"], C["amber_bg"], 2),
    "noinstalled": ("YÜKLÜ SÜRÜM GİRİLMEDİ", C["blue"], C["blue_bg"], 3),
    "new": ("HENÜZ KONTROL EDİLMEDİ", C["gray"], C["gray_bg"], 4),
    "ok": ("GÜNCEL", C["green"], C["green_bg"], 5),
    "checking": ("KONTROL EDİLİYOR…", C["blue"], C["blue_bg"], 6),
}

QSS = f"""
* {{ font-family: 'Segoe UI', sans-serif; font-size: 10pt; color: {C['text']}; }}
QMainWindow, QDialog, QScrollArea, #list {{ background: {C['bg']}; }}
QLineEdit, QComboBox {{ background: {C['panel2']}; border: 1px solid {C['line']}; border-radius: 6px; padding: 7px 9px; }}
QLineEdit:focus, QComboBox:focus {{ border-color: {C['accent']}; }}
QPushButton {{ background: {C['panel2']}; border: 1px solid {C['line']}; border-radius: 6px; padding: 6px 12px; }}
QPushButton:hover {{ border-color: {C['accent']}; }}
QPushButton:disabled {{ color: {C['muted']}; }}
QPushButton#primary {{ background: {C['accent']}; border-color: {C['accent']}; color: white; font-weight: 600; padding: 8px 16px; }}
QPushButton#primary:disabled {{ background: {C['panel2']}; border-color: {C['line']}; }}
QPushButton#danger:hover {{ border-color: {C['red']}; color: {C['red']}; }}
QPushButton#good {{ border-color: {C['green']}; color: {C['green']}; }}
QPushButton#dl {{ border-color: {C['red']}; color: white; background: {C['red_bg']}; font-weight: 600; }}
QListWidget {{ background: {C['panel']}; border: 1px solid {C['line']}; border-radius: 6px; }}
QListWidget::item {{ padding: 6px; border-bottom: 1px solid {C['line']}; }}
QListWidget::item:selected {{ background: {C['blue_bg']}; }}
QCheckBox {{ color: {C['muted']}; }}
QScrollBar:vertical {{ background: {C['bg']}; width: 10px; }}
QScrollBar::handle:vertical {{ background: {C['line']}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""


def fmt_date(iso: str) -> str:
    if not iso:
        return ""
    try:
        if "T" in iso:
            return datetime.fromisoformat(iso).strftime("%d.%m.%Y %H:%M")
        return date.fromisoformat(iso).strftime("%d.%m.%Y")
    except ValueError:
        return iso


def pill(text: str, fg: str, bg: str, big: bool = True) -> QLabel:
    lb = QLabel(text)
    size = "11pt" if big else "9pt"
    lb.setStyleSheet(
        f"background:{bg}; color:{fg}; border:1px solid {fg}; border-radius:12px;"
        f"padding:4px 12px; font-weight:700; font-size:{size};"
    )
    lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lb


# ---------------------------------------------------------------- iş parçacıkları

class CheckWorker(QThread):
    started_item = pyqtSignal(str)
    done_item = pyqtSignal(str)
    all_done = pyqtSignal()

    def __init__(self, store: Store, ids: list[str]):
        super().__init__()
        self.store, self.ids = store, ids

    def run(self):
        installed_programs(refresh=True)  # kurulumdan sonra yeni sürüm görünsün
        system_devices(refresh=True)
        browser = Browser(allow_identity=bool(self.store.settings.get("identity_fallback", True)))
        try:
            for item_id in self.ids:
                item = self.store.get(item_id)
                if item is None:
                    continue
                self.started_item.emit(item_id)
                try:
                    check_item(item, browser)
                except Exception as e:  # noqa: BLE001
                    item.state, item.message = "error", f"Beklenmeyen hata: {e}"
                self.done_item.emit(item_id)
        finally:
            browser.close()
            self.all_done.emit()


class ProbeWorker(QThread):
    finished_probe = pyqtSignal(object)

    def __init__(self, url: str, allow_identity: bool = True):
        super().__init__()
        self.url, self.allow_identity = url, allow_identity

    def run(self):
        browser = Browser(allow_identity=self.allow_identity)
        try:
            system_devices()  # Aygıt Yöneticisi listesi sayfa okunurken hazırlansın
            res = probe(self.url, browser)
        except Exception as e:  # noqa: BLE001
            res = Probe(error=f"Beklenmeyen hata: {e}")
        finally:
            browser.close()
        self.finished_probe.emit(res)


# ---------------------------------------------------------------- ekle / düzenle

class ItemDialog(QDialog):
    """Yeni link ekleme ya da mevcut kaydı düzenleme."""

    def __init__(self, parent, url: str, item: Item | None = None):
        super().__init__(parent)
        self.url, self.item = url, item
        self.result_probe: Probe | None = None
        self.setWindowTitle("Kaydı düzenle" if item else "Yeni takip ekle")
        self.resize(820, 620)

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        u = QLabel(f"<span style='color:{C['muted']}'>Sayfa:</span> {url}")
        u.setWordWrap(True)
        u.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(u)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        self.name = QLineEdit(item.name if item else "")
        self.name.setPlaceholderText("Ör. MSI X670E BIOS, AMD Chipset sürücüsü…")
        self.kind = QComboBox()
        self.kind.addItems(KINDS)
        self.kind.setCurrentText(item.kind if item else guess_kind(url))
        grid.addWidget(QLabel("Ad"), 0, 0)
        grid.addWidget(self.name, 0, 1)
        grid.addWidget(QLabel("Tür"), 0, 2)
        grid.addWidget(self.kind, 0, 3)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)

        self.status = QLabel("Sayfa okunuyor, sürüm numaraları aranıyor… (JavaScript'li sayfalarda 20 saniyeyi bulabilir)")
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color:{C['blue']}; padding:6px 0;")
        lay.addWidget(self.status)

        self.list_hint = QLabel(
            "<b>Sayfada bulunanlar</b> — takip etmek istediklerinizi işaretleyin (birden fazla seçebilirsiniz):"
            if not item else "<b>Sayfada bulunanlar</b> — takip edileni seçin:"
        )
        lay.addWidget(self.list_hint)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.currentRowChanged.connect(self._on_pick)
        lay.addWidget(self.list, 1)

        g2 = QGridLayout()
        g2.setHorizontalSpacing(10)
        self.installed = QLineEdit(item.installed if item else "")
        self.installed.setPlaceholderText("Bilgisayarınızda şu an yüklü olan sürüm (tarihle takipte: yüklediğiniz dosyanın tarihi)")
        self.btn_same = QPushButton("Seçili sürüm yüklü")
        self.btn_same.setToolTip("Bilgisayarınızda bu sürüm zaten kuruluysa tıklayın")
        self.btn_same.clicked.connect(self._mark_same)
        # Yüklü sürüm nereden okunsun: elle / BIOS / Windows'taki yüklü program
        self.source = QComboBox()
        self.source.addItem("Elle gireceğim (ya da kurunca “Yükledim ✓” derim)", ("manual", ""))
        if system_bios().get("version"):
            self.source.addItem(f"BIOS — bilgisayardan oku ({system_bios()['version']})", ("bios", ""))
        for prog, ver in installed_programs().items():
            self.source.addItem(f"{prog} — {ver}", ("app", prog))
        self.source.setToolTip("Seçerseniz yüklü sürüm her kontrolde Windows'tan okunur; kurulum yapınca kart kendiliğinden güncellenir.")
        self._source_touched = False
        self.source.activated.connect(lambda *_: setattr(self, "_source_touched", True))
        self.source.currentIndexChanged.connect(self._on_source)
        if item and item.installed_auto:
            self._select_source("bios", "")
        elif item and item.installed_app:
            self._select_source("app", item.installed_app)
        self._devices_added = False
        self.manual_latest = QLineEdit(item.latest if item else "")
        self.manual_latest.setPlaceholderText("Site engelliyorsa sitede gördüğünüz en yeni sürümü buraya yazabilirsiniz")
        g2.addWidget(QLabel("Yüklü sürüm"), 0, 0)
        g2.addWidget(self.installed, 0, 1)
        g2.addWidget(self.btn_same, 0, 2)
        g2.addWidget(QLabel("Windows'tan oku"), 1, 0)
        g2.addWidget(self.source, 1, 1, 1, 2)
        g2.addWidget(QLabel("En yeni (elle)"), 2, 0)
        g2.addWidget(self.manual_latest, 2, 1, 1, 2)
        g2.setColumnStretch(1, 1)
        lay.addLayout(g2)
        self.lbl_manual = g2.itemAtPosition(2, 0).widget()

        bios = system_bios()
        self.bios_info = QLabel("")
        if bios.get("version"):
            self.bios_info.setText(
                f"<span style='color:{C['muted']}'>Bu bilgisayar: {bios.get('board','')} · BIOS sürümü "
                f"<b style='color:{C['text']}'>{bios['version']}</b> ({fmt_date(bios.get('date',''))})</span>"
            )
        lay.addWidget(self.bios_info)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Kaydet")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Vazgeç")
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primary")
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)

        self._on_kind()
        self.kind.currentTextChanged.connect(self._on_kind)
        self._set_manual_visible(bool(item and item.state == "blocked"))

        st = getattr(parent, "store", None)
        self.worker = ProbeWorker(url, bool(st.settings.get("identity_fallback", True)) if st else True)
        self.worker.finished_probe.connect(self._on_probe)
        self.worker.start()

    # -- yardımcılar
    def _set_manual_visible(self, v: bool):
        self.manual_latest.setVisible(v)
        self.lbl_manual.setVisible(v)

    def _select_source(self, kind: str, name: str) -> bool:
        for i in range(self.source.count()):
            if self.source.itemData(i) == (kind, name):
                self.source.setCurrentIndex(i)
                return True
        return False

    def _on_kind(self, *_):
        is_bios = self.kind.currentText() == "BIOS" and bool(system_bios().get("version"))
        kind, _n = self.source.currentData()
        if is_bios and not self.item and not self._source_touched:
            self._select_source("bios", "")
        elif not is_bios and kind == "bios":
            self._select_source("manual", "")

    def _on_source(self, *_):
        kind, name = self.source.currentData()
        if kind == "bios":
            self.installed.setText(system_bios().get("version", ""))
        elif kind == "app":
            self.installed.setText(installed_programs().get(name, ""))
        elif kind == "device":
            dev = system_devices().get(name, {})
            c = self._current()
            self.installed.setText(fmt_date(dev.get("date", "")) if (c and c.by_date) else dev.get("version", ""))
        auto = kind != "manual"
        self.installed.setReadOnly(auto)
        self.btn_same.setEnabled(not auto)

    def _suggest_source(self, c):
        """Seçilen kalemin adına uyan yüklü programı öner (kullanıcı kendisi seçmediyse)."""
        if self._source_touched or self.kind.currentText() == "BIOS":
            return
        title = self._title(c) or self.name.text()
        prog = suggest_program(title, "" if c.by_date else c.version)
        if prog and self._select_source("app", prog):
            return
        # firmware / BIOS sürücü değildir; Aygıt Yöneticisi önerisi yalnızca sürücü ve yazılımlar için
        if self.kind.currentText() in ("Sürücü", "Yazılım", "Diğer") and c.shape != "label":
            dev = suggest_device(title)
            if dev and self._select_source("device", dev):
                return
        self._select_source("manual", "")

    def _add_devices(self):
        if self._devices_added:
            return
        self._devices_added = True
        for dev, info in system_devices().items():
            when = fmt_date(info.get("date", ""))
            self.source.addItem(f"Aygıt Yöneticisi: {dev} — {info.get('version', '')} ({when})", ("device", dev))
        if self.item and self.item.installed_device:
            self._select_source("device", self.item.installed_device)

    def _mark_same(self):
        c = self._current()
        if c:
            self.installed.setText(fmt_date(c.version) if c.by_date else c.version)

    def _checked(self) -> list:
        if not self.result_probe:
            return []
        out = []
        for r in range(self.list.count()):
            if self.list.item(r).checkState() == Qt.CheckState.Checked:
                out.append(self.result_probe.candidates[r])
        return out

    def _main_candidate(self):
        """Ad / yüklü sürüm alanları listede seçili (mavi) satır içindir."""
        c = self._current()
        if self.item:
            return c
        checked = self._checked()
        if c in checked:
            return c
        return checked[0] if checked else None

    def _title(self, c) -> str:
        title = (self.result_probe.page.title if self.result_probe and self.result_probe.page else "") or ""
        return title_for(c, title[:80])

    def _current(self):
        r = self.list.currentRow()
        if self.result_probe and 0 <= r < len(self.result_probe.candidates):
            return self.result_probe.candidates[r]
        return None

    def _on_pick(self, _row):
        """Ad kullanıcı tarafından değiştirilmediyse seçilen sürümün başlığını ad yap."""
        c = self._current()
        if not c or self.item or self.name.isModified():
            return
        t = self._title(c)
        if t:
            self.name.setText(t)
        self._suggest_source(c)
        self._on_source()

    def _on_probe(self, res: Probe):
        self.result_probe = res
        self._add_devices()
        if res.page and not self.name.text().strip():
            self.name.setText((res.page.title or "")[:80])
            if self.kind.currentText() == "Diğer":
                self.kind.setCurrentText(guess_kind(self.url, res.page.title))
        if not res.candidates:
            msg = res.error or "Sayfada sürüm numarası bulunamadı."
            extra = (
                " Bu site otomatik kontrolü engelliyor. Linki yine de kaydedebilirsiniz: kart üzerindeki "
                "“Sayfayı aç” ile kendiniz bakar, gördüğünüz sürümü “En yeni (elle)” alanına yazarsınız."
                if res.blocked else " Linki yine de kaydedebilirsiniz."
            )
            self.status.setText(msg + "." + extra if not msg.endswith(".") else msg + extra)
            self.status.setStyleSheet(f"color:{C['amber']}; padding:6px 0;")
            self._set_manual_visible(True)
            return
        self.status.setText(
            f"{len(res.candidates)} kalem bulundu. En olası olan en üstte ve işaretli; doğru değilse başkasını işaretleyin."
            + ("" if self.item else " Ad ve yüklü sürüm alanları listede seçili (mavi) satır içindir; işaretlediğiniz diğerleri kendi adlarıyla eklenir.")
        )
        self.status.setStyleSheet(f"color:{C['green']}; padding:6px 0;")
        pre = 0
        for i, c in enumerate(res.candidates[:60]):
            ctx = self._title(c) if (c.extra.get("src") == "data" or c.by_date) else c.context_label()
            ctx = ctx or c.context_label()
            if c.by_date:
                head = f"{fmt_date(c.date)}   ·   sürüm numarası yok, yayın tarihiyle takip edilir"
            else:
                head = c.version + (f"   ·   {fmt_date(c.date)}" if c.date else "")
            if c.link:
                head += "   ·   indirme linki bulundu"
            it = QListWidgetItem(f"{head}\n{ctx}")
            if not self.item:
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(Qt.CheckState.Checked if i == 0 else Qt.CheckState.Unchecked)
            f = it.font()
            f.setPointSize(10)
            it.setFont(f)
            self.list.addItem(it)
            if self.item and self.item.anchor and c.template == self.item.anchor.get("template") and c.prev == self.item.anchor.get("prev"):
                pre = i
        self.list.setCurrentRow(pre)

    def _save(self):
        if self.result_probe and self.result_probe.candidates and not self.item and not self._checked():
            QMessageBox.information(self, "Seçim yok", "Takip etmek istediğiniz en az bir kalemi işaretleyin.")
            return
        if not self.name.text().strip():
            self.name.setText(self.url[:80])
        self.accept()

    @staticmethod
    def _norm_installed(text: str, c) -> str:
        text = text.strip()
        if c is not None and c.by_date and text:
            ds = find_dates(text)
            if ds:
                return ds[0][2].isoformat()
        return text

    def extra_items(self) -> list[Item]:
        """İşaretlenen diğer kalemler için ayrı kayıtlar."""
        main = self._main_candidate()
        out = []
        for c in self._checked():
            if c is main:
                continue
            it = Item(url=self.url, name=self._title(c) or self.name.text().strip(), kind=self.kind.currentText())
            prog = "" if c.by_date else suggest_program(it.name, c.version)
            if prog:
                it.installed_app, it.installed = prog, installed_programs().get(prog, "")
            elif it.kind in ("Sürücü", "Yazılım", "Diğer") and c.shape != "label":
                dev = suggest_device(it.name)
                if dev:
                    info = system_devices().get(dev, {})
                    it.installed_device = dev
                    it.installed_dev_version = info.get("version", "")
                    it.installed = info.get("date", "") if c.by_date else info.get("version", "")
            it.anchor = anchor_from(c)
            it.latest, it.latest_date, it.link = c.version, c.date, c.link
            it.last_checked = datetime.now().isoformat(timespec="seconds")
            it.recompute_state()
            out.append(it)
        return out

    def apply_to(self, item: Item) -> Item:
        item.name = self.name.text().strip()
        item.kind = self.kind.currentText()
        kind, prog = self.source.currentData()
        item.installed_auto = kind == "bios"
        item.installed_app = prog if kind == "app" else ""
        item.installed_device = prog if kind == "device" else ""
        item.installed_dev_version = system_devices().get(prog, {}).get("version", "") if kind == "device" else ""
        c = self._main_candidate()
        if c is not None and c is not self._current() and not self.name.isModified():
            item.name = self._title(c) or item.name
        item.installed = self._norm_installed(self.installed.text(), c)
        if c:
            item.anchor = anchor_from(c)
            item.latest, item.latest_date, item.link = c.version, c.date, c.link
            item.message = ""
            item.last_checked = datetime.now().isoformat(timespec="seconds")
            item.state = "new"
        elif self.manual_latest.text().strip():
            item.latest = self.manual_latest.text().strip()
            item.message = "Sürüm elle girildi."
            item.state = "new"
        elif self.result_probe and self.result_probe.blocked:
            item.state, item.message = "blocked", self.result_probe.error
        item.recompute_state()
        if item.installed_device and c is not None and c.by_date and c.link.lower().split("?")[0].endswith(".zip"):
            item.state = "new"  # paketin içi kontrolde okununca karar verilir; tarihe bakıp yanlış uyarı verme
        return item

    def done(self, r):
        if self.worker.isRunning():
            self.worker.finished_probe.disconnect()
            self.worker.wait(100)
        super().done(r)


# ---------------------------------------------------------------- kart

class Card(QFrame):
    def __init__(self, win: "MainWindow", item: Item, checking: bool):
        super().__init__()
        self.win, self.item = win, item
        state = "checking" if checking else item.state
        label, fg, bg, _ = STATES.get(state, STATES["new"])
        self.setObjectName("card")
        self.setStyleSheet(
            f"#card {{ background:{C['panel']}; border:1px solid {C['line']}; border-left:6px solid {fg}; border-radius:10px; }}"
            f"#card QLabel {{ background: transparent; }}"
        )
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 12, 14, 12)
        v.setSpacing(8)

        # başlık satırı
        top = QHBoxLayout()
        kind = pill(item.kind, C["muted"], C["panel2"], big=False)
        name = QLabel(item.name or item.url)
        name.setStyleSheet("font-size:13pt; font-weight:600;")
        name.setWordWrap(True)
        name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        top.addWidget(kind)
        top.addWidget(name, 1)
        top.addWidget(pill(label, fg, bg))
        v.addLayout(top)

        # sürümler
        row = QHBoxLayout()
        row.setSpacing(12)
        by_date = item.anchor.get("shape") == "date"
        inst_txt = (fmt_date(item.installed) if by_date else item.installed) or "—"
        if by_date and item.pkg_version and item.installed_dev_version:
            inst_txt = item.installed_dev_version
        inst_sub = (
            "bilgisayardan okundu" if item.installed_auto
            else "Windows'tan okundu" if item.installed_app
            else "Aygıt Yöneticisi'nden okundu" if item.installed_device
            else ("girilmedi" if not item.installed else "")
        )
        cap = (
            ("YÜKLÜ SÜRÜCÜNÜN TARİHİ" if item.installed_device else "YÜKLEDİĞİNİZ DOSYANIN TARİHİ")
            if by_date else "YÜKLÜ SÜRÜM"
        )
        if by_date and item.pkg_version and item.installed_dev_version:
            cap = "YÜKLÜ SÜRÜCÜ"
            inst_sub = f"sürücü tarihi {fmt_date(item.installed)} · Aygıt Yöneticisi"
        row.addWidget(self._vbox(cap, inst_txt, inst_sub, C["text"]))
        arrow = QLabel("→")
        arrow.setStyleSheet(f"font-size:20pt; color:{fg if state=='update' else C['muted']};")
        row.addWidget(arrow)
        latest_color = C["red"] if state == "update" else (C["green"] if state == "ok" else C["text"])
        if by_date and item.pkg_version:
            # sitedeki paketin içindeki sürücüyle, bilgisayardaki sürücü karşılaştırıldı
            row.addWidget(self._vbox("SİTEDEKİ PAKETİN SÜRÜCÜSÜ", item.pkg_version,
                                     f"sürücü tarihi {fmt_date(item.pkg_date)} · paket yayını {fmt_date(item.latest)}",
                                     latest_color))
        elif by_date:
            row.addWidget(self._vbox("SİTEDEKİ EN YENİ TARİH", fmt_date(item.latest) or "—",
                                     "sürüm numarası yok, tarihle takip", latest_color))
        else:
            row.addWidget(self._vbox("SİTEDEKİ EN YENİ", item.latest or "—",
                                     ("yayın: " + fmt_date(item.latest_date)) if item.latest_date else "", latest_color))
        row.addStretch(1)
        v.addLayout(row)

        if item.message and not checking:
            m = QLabel(item.message)
            m.setWordWrap(True)
            m.setStyleSheet(f"color:{C['amber']};")
            v.addWidget(m)

        # alt satır
        bot = QHBoxLayout()
        meta = QLabel(
            f"<span style='color:{C['muted']}'>Son kontrol: {fmt_date(item.last_checked) or 'hiç'}"
            + (" · tarayıcı kimliğiyle okundu" if item.via == "chrome-kimlik" else "")
            + f" · {self._short(item.url)}</span>"
        )
        meta.setToolTip(item.url)
        meta.setWordWrap(True)
        meta.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        bot.addWidget(meta, 1)
        b_check = QPushButton("Kontrol et")
        b_check.clicked.connect(lambda: win.check([item.id]))
        b_check.setEnabled(not win.busy)
        b_open = QPushButton("Sayfayı aç")
        b_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(item.url)))
        bot.addWidget(b_check)
        bot.addWidget(b_open)
        if item.link:
            b_dl = QPushButton("İndir")
            b_dl.setToolTip(item.link)
            if state == "update":
                b_dl.setObjectName("dl")
            b_dl.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(item.link)))
            bot.addWidget(b_dl)
        if state in ("update", "noinstalled") and item.latest and not item.installed_auto and not item.installed_app and not item.installed_device:
            b_inst = QPushButton("Yükledim ✓")
            b_inst.setObjectName("good")
            b_inst.setToolTip(f"Yüklü sürümü {item.latest} olarak işaretle")
            b_inst.clicked.connect(lambda: win.mark_installed(item.id))
            bot.addWidget(b_inst)
        b_edit = QPushButton("Düzenle")
        b_edit.clicked.connect(lambda: win.edit(item.id))
        b_edit.setEnabled(not win.busy)
        b_del = QPushButton("Sil")
        b_del.setObjectName("danger")
        b_del.clicked.connect(lambda: win.delete(item.id))
        b_del.setEnabled(not win.busy)
        bot.addWidget(b_edit)
        bot.addWidget(b_del)
        v.addLayout(bot)

    @staticmethod
    def _short(url: str) -> str:
        s = url.split("://", 1)[-1]
        return s if len(s) <= 70 else s[:67] + "…"

    @staticmethod
    def _vbox(cap: str, value: str, sub: str, color: str) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background:{C['panel2']}; border-radius:8px;")
        l = QVBoxLayout(w)
        l.setContentsMargins(14, 8, 14, 8)
        l.setSpacing(1)
        a = QLabel(cap)
        a.setStyleSheet(f"color:{C['muted']}; font-size:8pt; font-weight:600; letter-spacing:1px;")
        b = QLabel(value)
        b.setStyleSheet(f"color:{color}; font-size:16pt; font-weight:700; font-family:'Cascadia Mono','Consolas',monospace;")
        b.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        l.addWidget(a)
        l.addWidget(b)
        if sub:
            c = QLabel(sub)
            c.setStyleSheet(f"color:{C['muted']}; font-size:8pt;")
            l.addWidget(c)
        w.setMinimumWidth(190)
        return w


# ---------------------------------------------------------------- ana pencere

class MainWindow(QMainWindow):
    def __init__(self, store: Store):
        super().__init__()
        self.store = store
        self.busy = False
        self.checking: set[str] = set()
        self.worker: CheckWorker | None = None
        self.setWindowTitle("DriverWatch — BIOS, sürücü ve firmware takibi")
        self.resize(1040, 760)

        root = QWidget()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(18, 16, 18, 12)
        v.setSpacing(12)

        head = QHBoxLayout()
        t = QLabel("DriverWatch")
        t.setStyleSheet("font-size:18pt; font-weight:700;")
        head.addWidget(t)
        self.summary = QHBoxLayout()
        self.summary.setSpacing(8)
        head.addSpacing(12)
        head.addLayout(self.summary)
        head.addStretch(1)
        v.addLayout(head)

        add = QHBoxLayout()
        self.url = QLineEdit()
        self.url.setPlaceholderText("Takip etmek istediğiniz indirme/destek sayfasının linkini yapıştırın ve Enter'a basın")
        self.url.returnPressed.connect(self.add)
        b_add = QPushButton("Ekle")
        b_add.setObjectName("primary")
        b_add.clicked.connect(self.add)
        add.addWidget(self.url, 1)
        add.addWidget(b_add)
        v.addLayout(add)

        bar = QHBoxLayout()
        self.b_all = QPushButton("Hepsini kontrol et")
        self.b_all.setObjectName("primary")
        self.b_all.clicked.connect(lambda: self.check([i.id for i in self.store.items]))
        self.cb_start = QCheckBox("Program açılınca otomatik kontrol et")
        self.cb_start.setChecked(bool(self.store.settings.get("check_on_start", True)))
        self.cb_start.toggled.connect(self._toggle_start)
        self.progress = QLabel("")
        self.progress.setStyleSheet(f"color:{C['blue']};")
        b_imp = QPushButton("Eski listeyi içe aktar…")
        b_imp.setToolTip("Eski uygulamanın tracker_data.json dosyasındaki linkleri ekler")
        b_imp.clicked.connect(self.import_legacy)
        self.cb_ident = QCheckBox("Engelleyen sitelerde normal tarayıcı kimliği kullan")
        self.cb_ident.setToolTip(
            "Bazı siteler (ör. MSI) görünmez Chrome'u reddediyor. Açıkken bu sitelerde Chrome kendini normal "
            "masaüstü Chrome olarak tanıtır. Site kurallarına aykırı olabilir; istemezseniz kapatın."
        )
        self.cb_ident.setChecked(bool(self.store.settings.get("identity_fallback", True)))
        self.cb_ident.toggled.connect(self._toggle_ident)
        bar.addWidget(self.b_all)
        bar.addWidget(self.progress, 1)
        bar.addWidget(self.cb_ident)
        bar.addWidget(self.cb_start)
        bar.addWidget(b_imp)
        v.addLayout(bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.listw = QWidget()
        self.listw.setObjectName("list")
        self.listl = QVBoxLayout(self.listw)
        self.listl.setContentsMargins(0, 0, 4, 0)
        self.listl.setSpacing(10)
        self.scroll.setWidget(self.listw)
        v.addWidget(self.scroll, 1)

        foot = QLabel(
            f"<span style='color:{C['muted']}'>Kayıtlar: {self.store.path} · Sürüm {__version__}</span>"
        )
        foot.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        v.addWidget(foot)

        self.render()
        if self.store.items and self.cb_start.isChecked():
            QTimer.singleShot(400, lambda: self.check([i.id for i in self.store.items]))

    # -- çizim
    def render(self):
        while self.listl.count():
            w = self.listl.takeAt(0).widget()
            if w:
                w.deleteLater()
        items = sorted(self.store.items, key=lambda i: (STATES.get(i.state, STATES["new"])[3], i.name.lower()))
        if not items:
            e = QLabel(
                "<div style='font-size:12pt'><b>Henüz takip edilen bir şey yok.</b></div>"
                f"<div style='color:{C['muted']}; margin-top:6px'>Anakartınızın BIOS sayfasını, ekran kartı ya da "
                "chipset sürücü sayfasını veya bir cihazın firmware sayfasını yukarıdaki kutuya yapıştırın. "
                "Program sayfadaki sürümleri bulur, siz takip edileni seçersiniz. Link siz silene kadar listede kalır.</div>"
            )
            e.setWordWrap(True)
            e.setStyleSheet(f"background:{C['panel']}; border:1px dashed {C['line']}; border-radius:10px; padding:24px;")
            self.listl.addWidget(e)
        for it in items:
            self.listl.addWidget(Card(self, it, it.id in self.checking))
        self.listl.addStretch(1)
        self._render_summary()

    def _render_summary(self):
        while self.summary.count():
            w = self.summary.takeAt(0).widget()
            if w:
                w.deleteLater()
        counts: dict[str, int] = {}
        for i in self.store.items:
            k = {"blocked": "error", "lost": "error"}.get(i.state, i.state)
            counts[k] = counts.get(k, 0) + 1
        n_up = counts.get("update", 0)
        if n_up:
            self.summary.addWidget(pill(f"{n_up} güncelleme var", C["red"], C["red_bg"]))
        if counts.get("ok"):
            self.summary.addWidget(pill(f"{counts['ok']} güncel", C["green"], C["green_bg"]))
        if counts.get("error"):
            self.summary.addWidget(pill(f"{counts['error']} kontrol edilemedi", C["amber"], C["amber_bg"]))
        rest = counts.get("noinstalled", 0) + counts.get("new", 0)
        if rest:
            self.summary.addWidget(pill(f"{rest} bilgi bekliyor", C["blue"], C["blue_bg"]))
        self.setWindowTitle(
            (f"({n_up}) " if n_up else "") + "DriverWatch — BIOS, sürücü ve firmware takibi"
        )

    # -- eylemler
    def _toggle_ident(self, on: bool):
        self.store.settings["identity_fallback"] = on
        self.store.save()

    def _toggle_start(self, on: bool):
        self.store.settings["check_on_start"] = on
        self.store.save()

    def add(self):
        url = self.url.text().strip()
        if not url:
            return
        if not url.lower().startswith(("http://", "https://")):
            url = "https://" + url
        if self.store.has_url(url):
            r = QMessageBox.question(
                self, "Bu sayfa zaten listede",
                "Bu sayfadan takip ettiğiniz bir kalem var. Aynı sayfadaki başka bir dosyayı da eklemek ister misiniz?",
            )
            if r != QMessageBox.StandardButton.Yes:
                return
        dlg = ItemDialog(self, url)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            item = dlg.apply_to(Item(url=url))
            new = [item] + dlg.extra_items()
            self.store.items.extend(new)
            self.store.save()
            self.url.clear()
            self.render()
            if any(i.installed_device for i in new):
                self.check([i.id for i in new])

    def edit(self, item_id: str):
        item = self.store.get(item_id)
        if not item:
            return
        dlg = ItemDialog(self, item.url, item)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            dlg.apply_to(item)
            self.store.save()
            self.render()

    def delete(self, item_id: str):
        item = self.store.get(item_id)
        if not item:
            return
        r = QMessageBox.question(
            self, "Silinsin mi?", f"“{item.name or item.url}” takip listesinden silinsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if r == QMessageBox.StandardButton.Yes:
            self.store.items.remove(item)
            self.store.save()
            self.render()

    def mark_installed(self, item_id: str):
        item = self.store.get(item_id)
        if item and item.latest:
            item.installed = item.latest
            item.recompute_state()
            self.store.save()
            self.render()

    def import_legacy(self):
        path, _ = QFileDialog.getOpenFileName(self, "tracker_data.json dosyasını seçin", "", "JSON (*.json)")
        if not path:
            return
        try:
            n = self.store.import_legacy(Path(path))
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "İçe aktarılamadı", str(e))
            return
        self.render()
        QMessageBox.information(self, "İçe aktarıldı", f"{n} link eklendi. Şimdi kontrol ediliyor.")
        if n:
            self.check([i.id for i in self.store.items if i.state == "new"])

    def check(self, ids: list[str]):
        if self.busy or not ids:
            return
        self.busy = True
        self.checking = set(ids)
        self._total, self._done = len(ids), 0
        self.b_all.setEnabled(False)
        self.progress.setText(f"Kontrol ediliyor… 0 / {self._total}")
        self.render()
        self.worker = CheckWorker(self.store, ids)
        self.worker.done_item.connect(self._on_done_item)
        self.worker.all_done.connect(self._on_all_done)
        self.worker.start()

    def _on_done_item(self, item_id: str):
        self.checking.discard(item_id)
        self._done += 1
        self.progress.setText(f"Kontrol ediliyor… {self._done} / {self._total}")
        self.store.save()
        self.render()

    def _on_all_done(self):
        self.busy = False
        self.checking.clear()
        self.b_all.setEnabled(True)
        n_up = sum(1 for i in self.store.items if i.state == "update")
        self.progress.setText(
            f"Bitti · {datetime.now():%H:%M}" + (f" · {n_up} güncelleme var" if n_up else " · yeni sürüm yok")
        )
        self.store.save()
        self.render()
        if n_up:
            QApplication.alert(self)

    def closeEvent(self, e):
        if self.worker and self.worker.isRunning():
            self.worker.wait(3000)
        super().closeEvent(e)


def resource(name: str) -> str:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return str(base / name)


def run(argv: list[str]) -> int:
    store = Store()
    if "--import" in argv:
        i = argv.index("--import")
        n = store.import_legacy(Path(argv[i + 1]))
        print(f"{n} link içe aktarıldı → {store.path}")
        return 0
    if "--selftest" in argv:
        # Tanı için: verilen sayfayı Chrome dahil okuyup sonucu dosyaya yazar (exe'de konsol yok)
        i = argv.index("--selftest")
        url, out = argv[i + 1], Path(argv[i + 2])
        from .fetch import Browser as _B
        b = _B()
        try:
            lines = []
            try:
                pg = b.fetch(url)
                lines.append(f"chrome ok, {len(pg.text)} karakter")
            except Exception as e:  # noqa: BLE001
                lines.append(f"chrome HATA: {e}")
            p = probe(url, b)
            lines.append(f"aday: {len(p.candidates)} hata: {p.error}")
            lines += [f"{c.version} {c.date} {c.link}" for c in p.candidates[:5]]
        finally:
            b.close()
        out.write_text("\n".join(lines), encoding="utf-8")
        return 0
    app = QApplication(argv)
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    app.setFont(QFont("Segoe UI", 10))
    ico = resource("icon.ico")
    if Path(ico).exists():
        app.setWindowIcon(QIcon(ico))
    # Aynı anda iki pencere açıksa biri diğerinin kayıtlarının üzerine yazar; tek örnek çalışsın
    from PyQt6.QtCore import QLockFile

    lock = QLockFile(str(store.path.parent / "driverwatch.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(
            None, "DriverWatch zaten açık",
            "DriverWatch zaten çalışıyor. Görev çubuğundaki pencereyi kullanın; "
            "iki pencere aynı anda açıkken kayıtlar birbirinin üzerine yazılabilir.",
        )
        return 0
    w = MainWindow(store)
    w.show()
    return app.exec()
