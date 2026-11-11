"""PyQt6 user interface."""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

from PyQt6.QtCore import QThread, QTimer, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from . import __version__
from .core import (
    KINDS, Item, Probe, Store, check_item, guess_kind, installed_info, installed_programs, probe, suggest_device,
    suggest_program, system_bios, system_devices,
)
from .extract import anchor_from, find_dates, title_for
from .fetch import Browser
from .i18n import LANGS, _, kind_label, lang, set_lang

# ---------------------------------------------------------------- look

C = {
    "bg": "#14171c", "panel": "#1d2128", "panel2": "#252a33", "line": "#323844",
    "text": "#e8ebf0", "muted": "#9aa3b2", "accent": "#4c8dff",
    "green": "#2fbf71", "green_bg": "#163a28", "red": "#ff5a4f", "red_bg": "#45201d",
    "amber": "#f0b429", "amber_bg": "#3d3214", "blue": "#5aa9ff", "blue_bg": "#18304d",
    "gray": "#8b95a5", "gray_bg": "#2a303a",
}

# Kind tags have their own colours, kept apart from the status colours (red / green / amber)
KIND_COLORS = {
    "BIOS": ("#b39dff", "#2a2342"),
    "Sürücü": ("#4cc3ff", "#13314a"),
    "Firmware": ("#ff8fc8", "#45203a"),
    "Yazılım": ("#3fd9c3", "#123b37"),
    "Diğer": ("#a3acba", "#2a303a"),
}


def states() -> dict:
    # state: (badge text, colour, background, sort order)
    return {
        "update": (_("NEW VERSION AVAILABLE"), C["red"], C["red_bg"], 0),
        "lost": (_("VERSION NOT FOUND"), C["amber"], C["amber_bg"], 1),
        "blocked": (_("SITE BLOCKS CHECKS"), C["amber"], C["amber_bg"], 2),
        "error": (_("COULD NOT CHECK"), C["amber"], C["amber_bg"], 2),
        "nocompare": (_("CANNOT COMPARE"), C["amber"], C["amber_bg"], 2),
        "noinstalled": (_("INSTALLED VERSION NOT SET"), C["blue"], C["blue_bg"], 3),
        "new": (_("NOT CHECKED YET"), C["gray"], C["gray_bg"], 4),
        "ok": (_("UP TO DATE"), C["green"], C["green_bg"], 5),
        "checking": (_("CHECKING…"), C["blue"], C["blue_bg"], 6),
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
    """English: 2026-07-13 · Turkish: 13.07.2026."""
    if not iso:
        return ""
    try:
        if "T" in iso:
            dt = datetime.fromisoformat(iso)
            return dt.strftime("%d.%m.%Y %H:%M") if lang() == "tr" else dt.strftime("%Y-%m-%d %H:%M")
        d = date.fromisoformat(iso)
        return d.strftime("%d.%m.%Y") if lang() == "tr" else d.isoformat()
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


def kind_pill(kind: str) -> QLabel:
    fg, bg = KIND_COLORS.get(kind, KIND_COLORS["Diğer"])
    return pill(kind_label(kind), fg, bg, big=False)


# ---------------------------------------------------------------- workers

class CheckWorker(QThread):
    started_item = pyqtSignal(str)
    done_item = pyqtSignal(str)
    all_done = pyqtSignal()

    def __init__(self, store: Store, ids: list[str]):
        super().__init__()
        self.store, self.ids = store, ids

    def run(self):
        installed_programs(refresh=True)  # so a version installed meanwhile shows up
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
                    item.state, item.message = "error", _("Unexpected error: {e}", e=e)
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
            system_devices()  # prepare the Device Manager list while the page is read
            res = probe(self.url, browser)
        except Exception as e:  # noqa: BLE001
            res = Probe(error=_("Unexpected error: {e}", e=e))
        finally:
            browser.close()
        self.finished_probe.emit(res)


# ---------------------------------------------------------------- add / edit

class ItemDialog(QDialog):
    """Add a new link or edit an existing item."""

    def __init__(self, parent, url: str, item: Item | None = None):
        super().__init__(parent)
        self.url, self.item = url, item
        self.result_probe: Probe | None = None
        self.setWindowTitle(_("Edit item") if item else _("Track a new item"))
        self.resize(820, 620)

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        u = QLabel(f"<span style='color:{C['muted']}'>{_('Page:')}</span> {url}")
        u.setWordWrap(True)
        u.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(u)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        self.name = QLineEdit(item.name if item else "")
        self.name.setPlaceholderText(_("e.g. MSI X670E BIOS, AMD chipset driver…"))
        self.kind = QComboBox()
        for k in KINDS:
            self.kind.addItem(kind_label(k), k)
        self._set_kind(item.kind if item else guess_kind(url))
        grid.addWidget(QLabel(_("Name")), 0, 0)
        grid.addWidget(self.name, 0, 1)
        grid.addWidget(QLabel(_("Kind")), 0, 2)
        grid.addWidget(self.kind, 0, 3)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)

        self.status = QLabel(_("Reading the page and looking for version numbers… (can take up to 20 seconds on JavaScript pages)"))
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color:{C['blue']}; padding:6px 0;")
        lay.addWidget(self.status)

        self.list_hint = QLabel(
            _("<b>Found on the page</b> — tick the ones you want to track (you can pick more than one):")
            if not item else _("<b>Found on the page</b> — pick the one being tracked:")
        )
        lay.addWidget(self.list_hint)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.currentRowChanged.connect(self._on_pick)
        lay.addWidget(self.list, 1)

        g2 = QGridLayout()
        g2.setHorizontalSpacing(10)
        self.installed = QLineEdit(item.installed if item else "")
        self.installed.setPlaceholderText(_("Version currently installed on this PC (for date tracking: the date of the file you installed)"))
        self.btn_same = QPushButton(_("Selected version is installed"))
        self.btn_same.setToolTip(_("Click if this version is already installed on your PC"))
        self.btn_same.clicked.connect(self._mark_same)
        # Where the installed version comes from: manual / BIOS / installed program / Device Manager
        self.source = QComboBox()
        self.source.addItem(_("I'll enter it myself (or click “Installed ✓” after installing)"), ("manual", ""))
        if system_bios().get("version"):
            self.source.addItem(_("BIOS — read from this PC ({v})", v=system_bios()["version"]), ("bios", ""))
        for prog, ver in installed_programs().items():
            self.source.addItem(f"{prog} — {ver}", ("app", prog))
        self.source.setToolTip(_("If you pick one, the installed version is read from Windows on every check; after you install an update the card updates by itself."))
        self._source_touched = False
        self.source.activated.connect(lambda *_a: setattr(self, "_source_touched", True))
        self.source.currentIndexChanged.connect(self._on_source)
        if item and item.installed_auto:
            self._select_source("bios", "")
        elif item and item.installed_app:
            self._select_source("app", item.installed_app)
        self._devices_added = False
        self.manual_latest = QLineEdit(item.latest if item else "")
        self.manual_latest.setPlaceholderText(_("If the site blocks checks, you can type the latest version you see on the site here"))
        g2.addWidget(QLabel(_("Installed version")), 0, 0)
        g2.addWidget(self.installed, 0, 1)
        g2.addWidget(self.btn_same, 0, 2)
        g2.addWidget(QLabel(_("Read from Windows")), 1, 0)
        g2.addWidget(self.source, 1, 1, 1, 2)
        g2.addWidget(QLabel(_("Latest (manual)")), 2, 0)
        g2.addWidget(self.manual_latest, 2, 1, 1, 2)
        g2.setColumnStretch(1, 1)
        lay.addLayout(g2)
        self.lbl_manual = g2.itemAtPosition(2, 0).widget()

        bios = system_bios()
        self.bios_info = QLabel("")
        if bios.get("version"):
            self.bios_info.setText(
                f"<span style='color:{C['muted']}'>{_('This PC: {b} · BIOS version', b=bios.get('board', ''))} "
                f"<b style='color:{C['text']}'>{bios['version']}</b> ({fmt_date(bios.get('date', ''))})</span>"
            )
        lay.addWidget(self.bios_info)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(_("Save"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(_("Cancel"))
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primary")
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)

        self._on_kind()
        self.kind.currentIndexChanged.connect(self._on_kind)
        self._set_manual_visible(bool(item and item.state == "blocked"))

        st = getattr(parent, "store", None)
        self.worker = ProbeWorker(url, bool(st.settings.get("identity_fallback", True)) if st else True)
        self.worker.finished_probe.connect(self._on_probe)
        self.worker.start()

    # -- helpers
    def _kind(self) -> str:
        return self.kind.currentData() or "Diğer"

    def _set_kind(self, key: str):
        i = self.kind.findData(key)
        self.kind.setCurrentIndex(i if i >= 0 else self.kind.findData("Diğer"))

    def _set_manual_visible(self, v: bool):
        self.manual_latest.setVisible(v)
        self.lbl_manual.setVisible(v)

    def _select_source(self, kind: str, name: str) -> bool:
        for i in range(self.source.count()):
            if self.source.itemData(i) == (kind, name):
                self.source.setCurrentIndex(i)
                return True
        return False

    def _on_kind(self, *_a):
        is_bios = self._kind() == "BIOS" and bool(system_bios().get("version"))
        kind, _n = self.source.currentData()
        if is_bios and not self.item and not self._source_touched:
            self._select_source("bios", "")
        elif not is_bios and kind == "bios":
            self._select_source("manual", "")

    def _on_source(self, *_a):
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
        """Suggest the installed program/device matching the item (unless the user picked one)."""
        if self._source_touched or self._kind() == "BIOS":
            return
        title = self._title(c) or self.name.text()
        prog = suggest_program(title, "" if c.by_date else c.version)
        if prog and self._select_source("app", prog):
            return
        # firmware / BIOS are not drivers; Device Manager is only suggested for drivers and software
        if self._kind() in ("Sürücü", "Yazılım", "Diğer") and c.shape != "label":
            dev = suggest_device(title)
            if dev and self._select_source("device", dev):
                return
        self._select_source("manual", "")

    def _add_devices(self):
        if self._devices_added:
            return
        self._devices_added = True
        for dev, info in system_devices().items():
            self.source.addItem(
                _("Device Manager: {d} — {v} ({w})", d=dev, v=info.get("version", ""), w=fmt_date(info.get("date", ""))),
                ("device", dev),
            )
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
        """The name / installed fields belong to the selected (blue) row."""
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
        """If the user has not changed the name, use the selected item's heading."""
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
            if self._kind() == "Diğer":
                self._set_kind(guess_kind(self.url, res.page.title))
        if not res.candidates:
            msg = res.error or _("No version number found on the page.")
            extra = (
                _(" This site blocks automatic checks. You can still save the link: use “Open page” on the card to look yourself and type the version you see into “Latest (manual)”.")
                if res.blocked else _(" You can still save the link.")
            )
            self.status.setText((msg if msg.endswith(".") else msg + ".") + extra)
            self.status.setStyleSheet(f"color:{C['amber']}; padding:6px 0;")
            self._set_manual_visible(True)
            return
        self.status.setText(
            _("{n} item(s) found. The most likely one is at the top and ticked; if it is wrong, tick another one.", n=len(res.candidates))
            + ("" if self.item else _(" The name and installed version fields belong to the selected (blue) row; the other ticked rows are added with their own names."))
        )
        self.status.setStyleSheet(f"color:{C['green']}; padding:6px 0;")
        pre = 0
        for i, c in enumerate(res.candidates[:60]):
            ctx = self._title(c) if (c.extra.get("src") == "data" or c.by_date) else c.context_label()
            ctx = ctx or c.context_label()
            if c.by_date:
                head = f"{fmt_date(c.date)}   ·   {_('no version number, tracked by release date')}"
            else:
                head = c.version + (f"   ·   {fmt_date(c.date)}" if c.date else "")
            if c.link:
                head += f"   ·   {_('download link found')}"
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
            QMessageBox.information(self, _("Nothing selected"), _("Tick at least one item to track."))
            return
        if not self.name.text().strip():
            self.name.setText(self.url[:80])
        self.accept()

    @staticmethod
    def _norm_installed(text: str, c) -> str:
        """If the typed value is entirely a date, store it as ISO (so dates are compared with dates)."""
        text = text.strip()
        if text:
            ds = find_dates(text)
            if ds and (c is not None and c.by_date or (ds[0][0] == 0 and ds[0][1] == len(text))):
                return ds[0][2].isoformat()
        return text

    def extra_items(self) -> list[Item]:
        """Separate items for the other ticked rows."""
        main = self._main_candidate()
        out = []
        for c in self._checked():
            if c is main:
                continue
            it = Item(url=self.url, name=self._title(c) or self.name.text().strip(), kind=self._kind())
            prog = suggest_program(it.name, "" if c.by_date else c.version)
            if prog:
                it.installed_app = prog
            elif it.kind in ("Sürücü", "Yazılım", "Diğer") and c.shape != "label":
                it.installed_device = suggest_device(it.name)
            installed_info(it)
            it.anchor = anchor_from(c)
            it.latest, it.latest_date, it.link = c.version, c.date, c.link
            it.last_checked = datetime.now().isoformat(timespec="seconds")
            it.recompute_state()
            out.append(it)
        return out

    def apply_to(self, item: Item) -> Item:
        item.name = self.name.text().strip()
        item.kind = self._kind()
        kind, prog = self.source.currentData()
        item.installed_auto = kind == "bios"
        item.installed_app = prog if kind == "app" else ""
        item.installed_device = prog if kind == "device" else ""
        item.installed_dev_version = system_devices().get(prog, {}).get("version", "") if kind == "device" else ""
        c = self._main_candidate()
        if c is not None and c is not self._current() and not self.name.isModified():
            item.name = self._title(c) or item.name
        item.installed = self._norm_installed(self.installed.text(), c)
        item.installed_date = ""
        installed_info(item)  # if a source is selected, take the real version and date from it
        if c:
            item.anchor = anchor_from(c)
            item.latest, item.latest_date, item.link = c.version, c.date, c.link
            item.message = ""
            item.last_checked = datetime.now().isoformat(timespec="seconds")
            item.state = "new"
        elif self.manual_latest.text().strip():
            item.latest = self.manual_latest.text().strip()
            item.message = _("Version entered manually.")
            item.state = "new"
        elif self.result_probe and self.result_probe.blocked:
            item.state, item.message = "blocked", self.result_probe.error
        item.recompute_state()
        if item.installed_device and c is not None and c.by_date and c.link.lower().split("?")[0].endswith(".zip"):
            item.state = "new"  # decided after the package is read during the check, not from the date
        return item

    def done(self, r):
        if self.worker.isRunning():
            self.worker.finished_probe.disconnect()
            self.worker.wait(100)
        super().done(r)


# ---------------------------------------------------------------- card

class Card(QFrame):
    def __init__(self, win: "MainWindow", item: Item, checking: bool):
        super().__init__()
        self.win, self.item = win, item
        state = "checking" if checking else item.state
        label, fg, bg, _o = states().get(state, states()["new"])
        self.setObjectName("card")
        self.setStyleSheet(
            f"#card {{ background:{C['panel']}; border:1px solid {C['line']}; border-left:6px solid {fg}; border-radius:10px; }}"
            f"#card QLabel {{ background: transparent; }}"
        )
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 12, 14, 12)
        v.setSpacing(8)

        # header
        top = QHBoxLayout()
        name = QLabel(item.name or item.url)
        name.setStyleSheet("font-size:13pt; font-weight:600;")
        name.setWordWrap(True)
        name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        top.addWidget(kind_pill(item.kind))
        top.addWidget(name, 1)
        top.addWidget(pill(label, fg, bg))
        v.addLayout(top)

        # versions: version is compared with version, date with date
        row = QHBoxLayout()
        row.setSpacing(12)
        iv, idt = item.installed_pair()
        sv, sd = item.site_pair()
        date_word = (
            _("BIOS date") if item.installed_auto
            else _("install date") if item.installed_app
            else _("driver date") if item.installed_device
            else _("date")
        )
        source = (
            _("read from this PC") if item.installed_auto
            else _("read from Windows") if item.installed_app
            else _("read from Device Manager") if item.installed_device
            else (_("not set") if not (iv or idt) else _("entered manually"))
        )
        inst_sub = " · ".join(x for x in ((f"{date_word} {fmt_date(idt)}" if iv and idt else ""), source) if x)
        row.addWidget(self._vbox(_("INSTALLED VERSION") if iv or not idt else _("INSTALLED DATE"),
                                 iv or fmt_date(idt) or "—", inst_sub, C["text"]))
        arrow = QLabel("→")
        arrow.setStyleSheet(f"font-size:20pt; color:{fg if state == 'update' else C['muted']};")
        row.addWidget(arrow)
        latest_color = C["red"] if state == "update" else (C["green"] if state == "ok" else C["text"])
        if item.pkg_version:
            site_cap = _("DRIVER IN SITE PACKAGE")
            site_sub = _("driver date {d} · package released {p}", d=fmt_date(item.pkg_date), p=fmt_date(item.latest))
        elif sv:
            site_cap, site_sub = _("LATEST ON SITE"), (_("released: {d}", d=fmt_date(sd)) if sd else "")
        else:
            site_cap, site_sub = _("LATEST ON SITE"), _("no version number on site, release date")
        row.addWidget(self._vbox(site_cap, sv or fmt_date(sd) or "—", site_sub, latest_color))
        row.addStretch(1)
        v.addLayout(row)

        # what the decision was based on
        basis = ""
        if not checking:
            if item.compared == "version":
                basis = _("Version numbers were compared.")
            elif item.compared == "date":
                basis = _("No version number, so dates were compared: site {s}, installed item's {w} {i}.",
                          s=fmt_date(sd), w=date_word, i=fmt_date(idt))
            elif item.state == "nocompare":
                basis = (
                    _("Cannot compare: the site only has a date, and only the version number of the installed one is known. Use “Edit” to enter the installed file's date or choose a source that has a date.")
                    if sd and not sv else
                    _("Cannot compare: the site has a version number, but only the date of the installed one is known. Use “Edit” to enter the installed version.")
                )
        if basis:
            b = QLabel(basis)
            b.setWordWrap(True)
            b.setStyleSheet(f"color:{C['amber'] if item.state == 'nocompare' else C['muted']}; font-size:9pt;")
            v.addWidget(b)

        if item.message and not checking:
            m = QLabel(item.message)
            m.setWordWrap(True)
            m.setStyleSheet(f"color:{C['amber']};")
            v.addWidget(m)

        # footer
        bot = QHBoxLayout()
        meta = QLabel(
            f"<span style='color:{C['muted']}'>{_('Last check: {d}', d=fmt_date(item.last_checked) or _('never'))}"
            + (_(" · read with browser identity") if item.via == "chrome-kimlik" else "")
            + f" · {self._short(item.url)}</span>"
        )
        meta.setToolTip(item.url)
        meta.setWordWrap(True)
        meta.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        bot.addWidget(meta, 1)
        b_check = QPushButton(_("Check"))
        b_check.clicked.connect(lambda: win.check([item.id]))
        b_check.setEnabled(not win.busy)
        b_open = QPushButton(_("Open page"))
        b_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(item.url)))
        bot.addWidget(b_check)
        bot.addWidget(b_open)
        if item.link:
            b_dl = QPushButton(_("Download"))
            b_dl.setToolTip(item.link)
            if state == "update":
                b_dl.setObjectName("dl")
            b_dl.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(item.link)))
            bot.addWidget(b_dl)
        if state in ("update", "noinstalled", "nocompare") and item.latest and not (
            item.installed_auto or item.installed_app or item.installed_device
        ):
            b_inst = QPushButton(_("Installed ✓"))
            b_inst.setObjectName("good")
            b_inst.setToolTip(_("Mark the installed version as {v}", v=item.latest))
            b_inst.clicked.connect(lambda: win.mark_installed(item.id))
            bot.addWidget(b_inst)
        b_edit = QPushButton(_("Edit"))
        b_edit.clicked.connect(lambda: win.edit(item.id))
        b_edit.setEnabled(not win.busy)
        b_del = QPushButton(_("Delete"))
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
        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(1)
        a = QLabel(cap)
        a.setStyleSheet(f"color:{C['muted']}; font-size:8pt; font-weight:600; letter-spacing:1px;")
        b = QLabel(value)
        b.setStyleSheet(f"color:{color}; font-size:16pt; font-weight:700; font-family:'Cascadia Mono','Consolas',monospace;")
        b.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(a)
        lay.addWidget(b)
        if sub:
            c = QLabel(sub)
            c.setStyleSheet(f"color:{C['muted']}; font-size:8pt;")
            lay.addWidget(c)
        w.setMinimumWidth(190)
        return w


# ---------------------------------------------------------------- main window

class MainWindow(QMainWindow):
    def __init__(self, store: Store, autostart: bool = True):
        super().__init__()
        self.store = store
        self.busy = False
        self.checking: set[str] = set()
        self.worker: CheckWorker | None = None
        self.setWindowTitle(_("DriverWatch — BIOS, driver and firmware tracker"))
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
        # language
        head.addWidget(QLabel(_("Language")))
        self.lang_box = QComboBox()
        for code, label in LANGS.items():
            self.lang_box.addItem(label, code)
        self.lang_box.setCurrentIndex(self.lang_box.findData(lang()))
        self.lang_box.currentIndexChanged.connect(self._change_lang)
        head.addWidget(self.lang_box)
        v.addLayout(head)

        add = QHBoxLayout()
        self.url = QLineEdit()
        self.url.setPlaceholderText(_("Paste the link of a download/support page to track and press Enter"))
        self.url.returnPressed.connect(self.add)
        b_add = QPushButton(_("Add"))
        b_add.setObjectName("primary")
        b_add.clicked.connect(self.add)
        add.addWidget(self.url, 1)
        add.addWidget(b_add)
        v.addLayout(add)

        bar = QHBoxLayout()
        self.b_all = QPushButton(_("Check all"))
        self.b_all.setObjectName("primary")
        self.b_all.clicked.connect(lambda: self.check([i.id for i in self.store.items]))
        self.cb_start = QCheckBox(_("Check automatically when the app starts"))
        self.cb_start.setChecked(bool(self.store.settings.get("check_on_start", True)))
        self.cb_start.toggled.connect(self._toggle_start)
        self.progress = QLabel("")
        self.progress.setStyleSheet(f"color:{C['blue']};")
        b_imp = QPushButton(_("Import old list…"))
        b_imp.setToolTip(_("Adds the links from the old app's tracker_data.json file"))
        b_imp.clicked.connect(self.import_legacy)
        self.cb_ident = QCheckBox(_("Use a normal browser identity on sites that block"))
        self.cb_ident.setToolTip(_(
            "Some sites (e.g. MSI) reject headless Chrome. When this is on, Chrome presents itself as normal desktop "
            "Chrome on those sites. This may be against the site's rules; turn it off if you do not want it."
        ))
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

        foot = QLabel(f"<span style='color:{C['muted']}'>{_('Data: {path} · Version {v}', path=self.store.path, v=__version__)}</span>")
        foot.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        v.addWidget(foot)

        self.render()
        if autostart and self.store.items and self.cb_start.isChecked():
            QTimer.singleShot(400, lambda: self.check([i.id for i in self.store.items]))

    # -- drawing
    def render(self):
        while self.listl.count():
            w = self.listl.takeAt(0).widget()
            if w:
                w.deleteLater()
        st = states()
        items = sorted(self.store.items, key=lambda i: (st.get(i.state, st["new"])[3], i.name.lower()))
        if not items:
            e = QLabel(
                f"<div style='font-size:12pt'><b>{_('Nothing is being tracked yet.')}</b></div>"
                f"<div style='color:{C['muted']}; margin-top:6px'>"
                + _("Paste your motherboard's BIOS page, a graphics or chipset driver page, or a device's firmware page into the box above. The app finds the versions on the page and you pick the one to track. A link stays in the list until you delete it.")
                + "</div>"
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
            k = {"blocked": "error", "lost": "error", "nocompare": "error"}.get(i.state, i.state)
            counts[k] = counts.get(k, 0) + 1
        n_up = counts.get("update", 0)
        if n_up:
            self.summary.addWidget(pill(_("{n} update(s) available", n=n_up), C["red"], C["red_bg"]))
        if counts.get("ok"):
            self.summary.addWidget(pill(_("{n} up to date", n=counts["ok"]), C["green"], C["green_bg"]))
        if counts.get("error"):
            self.summary.addWidget(pill(_("{n} could not be checked", n=counts["error"]), C["amber"], C["amber_bg"]))
        rest = counts.get("noinstalled", 0) + counts.get("new", 0)
        if rest:
            self.summary.addWidget(pill(_("{n} waiting for info", n=rest), C["blue"], C["blue_bg"]))
        self.setWindowTitle((f"({n_up}) " if n_up else "") + _("DriverWatch — BIOS, driver and firmware tracker"))

    # -- actions
    def _change_lang(self, *_a):
        code = self.lang_box.currentData()
        if code == lang():
            return
        if self.busy:
            self.lang_box.blockSignals(True)
            self.lang_box.setCurrentIndex(self.lang_box.findData(lang()))
            self.lang_box.blockSignals(False)
            return
        self.store.settings["lang"] = code
        self.store.save()
        set_lang(code)
        # rebuild the window in the new language (no new check)
        new = MainWindow(self.store, autostart=False)
        new.setGeometry(self.geometry())
        new.show()
        QApplication.instance().setProperty("main_window", new)
        _windows.append(new)
        self.close()

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
                self, _("This page is already in the list"),
                _("You already track an item from this page. Do you want to add another file from the same page?"),
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
            self, _("Delete?"), _("Remove “{n}” from the tracking list?", n=item.name or item.url),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if r == QMessageBox.StandardButton.Yes:
            self.store.items.remove(item)
            self.store.save()
            self.render()

    def mark_installed(self, item_id: str):
        item = self.store.get(item_id)
        if item and item.latest:
            sv, sd = item.site_pair()
            item.installed, item.installed_date = (sv or sd), sd
            item.recompute_state()
            self.store.save()
            self.render()

    def import_legacy(self):
        path, _f = QFileDialog.getOpenFileName(self, _("Select the tracker_data.json file"), "", "JSON (*.json)")
        if not path:
            return
        try:
            n = self.store.import_legacy(Path(path))
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, _("Could not import"), str(e))
            return
        self.render()
        QMessageBox.information(self, _("Imported"), _("{n} link(s) added. Checking them now.", n=n))
        if n:
            self.check([i.id for i in self.store.items if i.state == "new"])

    def check(self, ids: list[str]):
        if self.busy or not ids:
            return
        self.busy = True
        self.checking = set(ids)
        self._total, self._done = len(ids), 0
        self.b_all.setEnabled(False)
        self.progress.setText(_("Checking… {d} / {t}", d=0, t=self._total))
        self.render()
        self.worker = CheckWorker(self.store, ids)
        self.worker.done_item.connect(self._on_done_item)
        self.worker.all_done.connect(self._on_all_done)
        self.worker.start()

    def _on_done_item(self, item_id: str):
        self.checking.discard(item_id)
        self._done += 1
        self.progress.setText(_("Checking… {d} / {t}", d=self._done, t=self._total))
        self.store.save()
        self.render()

    def _on_all_done(self):
        self.busy = False
        self.checking.clear()
        self.b_all.setEnabled(True)
        n_up = sum(1 for i in self.store.items if i.state == "update")
        self.progress.setText(
            _("Done · {time}", time=f"{datetime.now():%H:%M}")
            + (_(" · {n} update(s) available", n=n_up) if n_up else _(" · no new versions"))
        )
        self.store.save()
        self.render()
        if n_up:
            QApplication.alert(self)

    def closeEvent(self, e):
        if self.worker and self.worker.isRunning():
            self.worker.wait(3000)
        super().closeEvent(e)


_windows: list[MainWindow] = []  # keeps rebuilt windows alive


def resource(name: str) -> str:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return str(base / name)


def run(argv: list[str]) -> int:
    store = Store()
    set_lang(store.settings.get("lang", "en"))
    if "--import" in argv:
        i = argv.index("--import")
        n = store.import_legacy(Path(argv[i + 1]))
        print(f"{n} link(s) imported → {store.path}")
        return 0
    if "--selftest" in argv:
        # Diagnostics: read the given page (including Chrome) and write the result to a file (the exe has no console)
        i = argv.index("--selftest")
        url, out = argv[i + 1], Path(argv[i + 2])
        b = Browser()
        try:
            lines = []
            try:
                pg = b.fetch(url)
                lines.append(f"chrome ok, {len(pg.text)} chars")
            except Exception as e:  # noqa: BLE001
                lines.append(f"chrome ERROR: {e}")
            p = probe(url, b)
            lines.append(f"candidates: {len(p.candidates)} error: {p.error}")
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
    # With two windows open, one overwrites the other's saved list; allow a single instance
    from PyQt6.QtCore import QLockFile

    lock = QLockFile(str(store.path.parent / "driverwatch.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(
            None, _("DriverWatch is already open"),
            _("DriverWatch is already running. Use the window in the taskbar; with two windows open at once the saved list can be overwritten."),
        )
        return 0
    w = MainWindow(store)
    _windows.append(w)
    w.show()
    return app.exec()
