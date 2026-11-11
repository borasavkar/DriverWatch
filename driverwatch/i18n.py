"""Interface language. English is the default; Turkish is optional.

Source strings are English. `_()` returns the Turkish translation when Turkish is selected,
otherwise the English text. Placeholders use str.format: _("{n} updates", n=3).
"""
from __future__ import annotations

LANGS = {"en": "English", "tr": "Türkçe"}
_lang = "en"


def set_lang(code: str) -> None:
    global _lang
    _lang = code if code in LANGS else "en"


def lang() -> str:
    return _lang


def _(text: str, **kw) -> str:
    s = TR.get(text, text) if _lang == "tr" else text
    return s.format(**kw) if kw else s


# Kinds are stored with their Turkish keys in items.json (kept for compatibility); these are display names.
KIND_LABELS_EN = {"BIOS": "BIOS", "Sürücü": "Driver", "Firmware": "Firmware", "Yazılım": "Software", "Diğer": "Other"}


def kind_label(key: str) -> str:
    return key if _lang == "tr" else KIND_LABELS_EN.get(key, key)


TR: dict[str, str] = {
    # window / toolbar
    "DriverWatch — BIOS, driver and firmware tracker": "DriverWatch — BIOS, sürücü ve firmware takibi",
    "Paste the link of a download/support page to track and press Enter":
        "Takip etmek istediğiniz indirme/destek sayfasının linkini yapıştırın ve Enter'a basın",
    "Add": "Ekle",
    "Check all": "Hepsini kontrol et",
    "Check automatically when the app starts": "Program açılınca otomatik kontrol et",
    "Import old list…": "Eski listeyi içe aktar…",
    "Adds the links from the old app's tracker_data.json file":
        "Eski uygulamanın tracker_data.json dosyasındaki linkleri ekler",
    "Use a normal browser identity on sites that block": "Engelleyen sitelerde normal tarayıcı kimliği kullan",
    "Some sites (e.g. MSI) reject headless Chrome. When this is on, Chrome presents itself as normal desktop "
    "Chrome on those sites. This may be against the site's rules; turn it off if you do not want it.":
        "Bazı siteler (ör. MSI) görünmez Chrome'u reddediyor. Açıkken bu sitelerde Chrome kendini normal "
        "masaüstü Chrome olarak tanıtır. Site kurallarına aykırı olabilir; istemezseniz kapatın.",
    "Language": "Dil",
    "Data: {path} · Version {v}": "Kayıtlar: {path} · Sürüm {v}",
    "Nothing is being tracked yet.": "Henüz takip edilen bir şey yok.",
    "Paste your motherboard's BIOS page, a graphics or chipset driver page, or a device's firmware page into the "
    "box above. The app finds the versions on the page and you pick the one to track. A link stays in the list "
    "until you delete it.":
        "Anakartınızın BIOS sayfasını, ekran kartı ya da chipset sürücü sayfasını veya bir cihazın firmware "
        "sayfasını yukarıdaki kutuya yapıştırın. Program sayfadaki sürümleri bulur, siz takip edileni seçersiniz. "
        "Link siz silene kadar listede kalır.",
    "{n} update(s) available": "{n} güncelleme var",
    "{n} up to date": "{n} güncel",
    "{n} could not be checked": "{n} kontrol edilemedi",
    "{n} waiting for info": "{n} bilgi bekliyor",
    "Checking… {d} / {t}": "Kontrol ediliyor… {d} / {t}",
    "Done · {time}": "Bitti · {time}",
    " · {n} update(s) available": " · {n} güncelleme var",
    " · no new versions": " · yeni sürüm yok",
    # states
    "NEW VERSION AVAILABLE": "YENİ SÜRÜM VAR",
    "VERSION NOT FOUND": "SÜRÜM BULUNAMADI",
    "SITE BLOCKS CHECKS": "SİTE ENGELLİYOR",
    "COULD NOT CHECK": "KONTROL EDİLEMEDİ",
    "INSTALLED VERSION NOT SET": "YÜKLÜ SÜRÜM GİRİLMEDİ",
    "NOT CHECKED YET": "HENÜZ KONTROL EDİLMEDİ",
    "UP TO DATE": "GÜNCEL",
    "CHECKING…": "KONTROL EDİLİYOR…",
    "CANNOT COMPARE": "KARŞILAŞTIRILAMADI",
    # card
    "INSTALLED VERSION": "YÜKLÜ SÜRÜM",
    "INSTALLED DATE": "YÜKLÜ OLANIN TARİHİ",
    "LATEST ON SITE": "SİTEDEKİ EN YENİ",
    "DRIVER IN SITE PACKAGE": "SİTEDEKİ PAKETİN SÜRÜCÜSÜ",
    "BIOS date": "BIOS tarihi",
    "install date": "kurulum tarihi",
    "driver date": "sürücü tarihi",
    "date": "tarih",
    "read from this PC": "bilgisayardan okundu",
    "read from Windows": "Windows'tan okundu",
    "read from Device Manager": "Aygıt Yöneticisi'nden okundu",
    "not set": "girilmedi",
    "entered manually": "elle girildi",
    "released: {d}": "yayın: {d}",
    "no version number on site, release date": "sitede sürüm numarası yok, yayın tarihi",
    "driver date {d} · package released {p}": "sürücü tarihi {d} · paket yayını {p}",
    "Version numbers were compared.": "Sürüm numaraları karşılaştırıldı.",
    "No version number, so dates were compared: site {s}, installed item's {w} {i}.":
        "Sürüm numarası olmadığı için tarihler karşılaştırıldı: sitedeki {s}, yüklü olanın {w} {i}.",
    "Cannot compare: the site only has a date, and only the version number of the installed one is known. "
    "Use “Edit” to enter the installed file's date or choose a source that has a date.":
        "Karşılaştırılamadı: sitede yalnızca tarih var, yüklü olanın ise yalnızca sürüm numarası biliniyor. "
        "“Düzenle”den yüklü dosyanın tarihini yazın ya da tarih bilgisi olan bir kaynak seçin.",
    "Cannot compare: the site has a version number, but only the date of the installed one is known. "
    "Use “Edit” to enter the installed version.":
        "Karşılaştırılamadı: sitede sürüm numarası var, yüklü olanın ise yalnızca tarihi biliniyor. "
        "“Düzenle”den yüklü sürümü yazın.",
    "Last check: {d}": "Son kontrol: {d}",
    "never": "hiç",
    " · read with browser identity": " · tarayıcı kimliğiyle okundu",
    "Check": "Kontrol et",
    "Open page": "Sayfayı aç",
    "Download": "İndir",
    "Installed ✓": "Yükledim ✓",
    "Mark the installed version as {v}": "Yüklü sürümü {v} olarak işaretle",
    "Edit": "Düzenle",
    "Delete": "Sil",
    # dialogs
    "Edit item": "Kaydı düzenle",
    "Track a new item": "Yeni takip ekle",
    "Page:": "Sayfa:",
    "Name": "Ad",
    "Kind": "Tür",
    "e.g. MSI X670E BIOS, AMD chipset driver…": "Ör. MSI X670E BIOS, AMD Chipset sürücüsü…",
    "Reading the page and looking for version numbers… (can take up to 20 seconds on JavaScript pages)":
        "Sayfa okunuyor, sürüm numaraları aranıyor… (JavaScript'li sayfalarda 20 saniyeyi bulabilir)",
    "<b>Found on the page</b> — tick the ones you want to track (you can pick more than one):":
        "<b>Sayfada bulunanlar</b> — takip etmek istediklerinizi işaretleyin (birden fazla seçebilirsiniz):",
    "<b>Found on the page</b> — pick the one being tracked:": "<b>Sayfada bulunanlar</b> — takip edileni seçin:",
    "Version currently installed on this PC (for date tracking: the date of the file you installed)":
        "Bilgisayarınızda şu an yüklü olan sürüm (tarihle takipte: yüklediğiniz dosyanın tarihi)",
    "Selected version is installed": "Seçili sürüm yüklü",
    "Click if this version is already installed on your PC": "Bilgisayarınızda bu sürüm zaten kuruluysa tıklayın",
    "I'll enter it myself (or click “Installed ✓” after installing)":
        "Elle gireceğim (ya da kurunca “Yükledim ✓” derim)",
    "BIOS — read from this PC ({v})": "BIOS — bilgisayardan oku ({v})",
    "Device Manager: {d} — {v} ({w})": "Aygıt Yöneticisi: {d} — {v} ({w})",
    "If you pick one, the installed version is read from Windows on every check; after you install an update "
    "the card updates by itself.":
        "Seçerseniz yüklü sürüm her kontrolde Windows'tan okunur; kurulum yapınca kart kendiliğinden güncellenir.",
    "If the site blocks checks, you can type the latest version you see on the site here":
        "Site engelliyorsa sitede gördüğünüz en yeni sürümü buraya yazabilirsiniz",
    "Installed version": "Yüklü sürüm",
    "Read from Windows": "Windows'tan oku",
    "Latest (manual)": "En yeni (elle)",
    "This PC: {b} · BIOS version": "Bu bilgisayar: {b} · BIOS sürümü",
    "Save": "Kaydet",
    "Cancel": "Vazgeç",
    "No version number found on the page.": "Sayfada sürüm numarası bulunamadı.",
    " This site blocks automatic checks. You can still save the link: use “Open page” on the card to look "
    "yourself and type the version you see into “Latest (manual)”.":
        " Bu site otomatik kontrolü engelliyor. Linki yine de kaydedebilirsiniz: kart üzerindeki "
        "“Sayfayı aç” ile kendiniz bakar, gördüğünüz sürümü “En yeni (elle)” alanına yazarsınız.",
    " You can still save the link.": " Linki yine de kaydedebilirsiniz.",
    "{n} item(s) found. The most likely one is at the top and ticked; if it is wrong, tick another one.":
        "{n} kalem bulundu. En olası olan en üstte ve işaretli; doğru değilse başkasını işaretleyin.",
    " The name and installed version fields belong to the selected (blue) row; the other ticked rows are added "
    "with their own names.":
        " Ad ve yüklü sürüm alanları listede seçili (mavi) satır içindir; işaretlediğiniz diğerleri kendi "
        "adlarıyla eklenir.",
    "no version number, tracked by release date": "sürüm numarası yok, yayın tarihiyle takip edilir",
    "download link found": "indirme linki bulundu",
    "Nothing selected": "Seçim yok",
    "Tick at least one item to track.": "Takip etmek istediğiniz en az bir kalemi işaretleyin.",
    "Version entered manually.": "Sürüm elle girildi.",
    "This page is already in the list": "Bu sayfa zaten listede",
    "You already track an item from this page. Do you want to add another file from the same page?":
        "Bu sayfadan takip ettiğiniz bir kalem var. Aynı sayfadaki başka bir dosyayı da eklemek ister misiniz?",
    "Delete?": "Silinsin mi?",
    "Remove “{n}” from the tracking list?": "“{n}” takip listesinden silinsin mi?",
    "Select the tracker_data.json file": "tracker_data.json dosyasını seçin",
    "Could not import": "İçe aktarılamadı",
    "Imported": "İçe aktarıldı",
    "{n} link(s) added. Checking them now.": "{n} link eklendi. Şimdi kontrol ediliyor.",
    "DriverWatch is already open": "DriverWatch zaten açık",
    "DriverWatch is already running. Use the window in the taskbar; with two windows open at once the saved list "
    "can be overwritten.":
        "DriverWatch zaten çalışıyor. Görev çubuğundaki pencereyi kullanın; iki pencere aynı anda açıkken "
        "kayıtlar birbirinin üzerine yazılabilir.",
    "Unexpected error: {e}": "Beklenmeyen hata: {e}",
    # core / fetch messages
    "Could not connect: {e}": "Bağlantı kurulamadı: {e}",
    "The site refused the request (HTTP {c})": "Site isteği reddetti (HTTP {c})",
    "The page could not be opened (HTTP {c})": "Sayfa açılamadı (HTTP {c})",
    "Chrome could not be started. Is Google Chrome installed? ({e})":
        "Chrome başlatılamadı. Google Chrome kurulu mu? ({e})",
    "The page timed out": "Sayfa zaman aşımına uğradı",
    "The site does not allow automatic checks": "Site otomatik kontrole izin vermiyor",
    "No version number found on the page": "Sayfada sürüm numarası bulunamadı",
    "The site does not allow automatic checks. Look with “Open page” and type the version you see into "
    "“Edit” → “Latest (manual)”.":
        "Site otomatik kontrole izin vermiyor. “Sayfayı aç” ile bakıp gördüğünüz sürümü "
        "“Düzenle” → “En yeni (elle)” alanına yazabilirsiniz.",
    "The tracked version was not found on the page; the page may have changed. Pick it again under “Edit”.":
        "Takip edilen sürüm sayfada bulunamadı; sayfa değişmiş olabilir. Düzenle'den yeniden seçin.",
}
