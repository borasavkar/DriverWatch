# DriverWatch

A small Windows app that watches vendor download and support pages for new **BIOS, driver and firmware** releases. You add the link of a vendor page, the app finds the version numbers on it, and you pick the one to track. On every check it finds the latest version at that spot and compares it with the one installed on your PC.

The interface is in English by default; Turkish can be selected from the **Language** menu.

*Türkçe açıklama aşağıda.*

![DriverWatch](docs/screenshot.png)

## Features

- **Links stay until you delete them.** The list is saved in `%APPDATA%\DriverWatch\items.json`.
- **You choose the right version.** When a page lists several versions (e.g. chipset and RAID drivers on an AMD page), all of them are shown with their context: `AMD Chipset Drivers › Revision Number › 8.09.28.1124 · 2026-10-21`. The chosen one is tracked by its position on the page, so it is found again when the number changes. Beta versions are listed below stable ones and are not mixed with them.
- **Clear status.** Every item is a card with the installed version on the left, the latest version on the site and its release date on the right, and a coloured badge:
  - 🔴 **NEW VERSION AVAILABLE**
  - 🟢 **UP TO DATE**
  - 🟡 **SITE BLOCKS CHECKS / COULD NOT CHECK / VERSION NOT FOUND / CANNOT COMPARE**
  - 🔵 **INSTALLED VERSION NOT SET**
- **Coloured kind tags and tabs:** BIOS, Driver, Firmware, Software and Other each have their own colour, and tabs above the list show one kind at a time with its item count and how many have updates.
- **Version is compared with version, date with date.** If both sides have a version number, versions decide. If one side has no version number (e.g. ASUS pages that only show “Version -” and a date), dates are compared. If there is no matching pair, the card says it cannot compare instead of guessing. Each card states what the decision was based on.
- **Several files from one page.** Tick as many items as you like in the add dialog; each becomes its own card.
- **Hidden download links.** When a “Download” button is not a real link, the file address is looked up in the page data and in the data requests the page itself makes.
- **Pages that wait for an operating system.** If a page asks you to select an operating system before listing files (e.g. ROG support pages), the option matching this PC (e.g. Windows 11 64-bit) is selected automatically.
- **Installed version read from Windows.** In the add dialog, “Read from Windows” offers:
  - the BIOS version of this PC (MSI's `7E16v1D4` on the site and `1.D4` in Windows count as the same version),
  - entries from Windows' installed apps list (e.g. *AMD Chipset Software — 8.09.28.1124*, with its install date),
  - **Device Manager** drivers (e.g. *ROG STRIX XG27ACSR — 1.0.0.0, 2026-03-17*).

  A matching entry is suggested automatically. The installed version is read again on every check, so the card updates by itself after you install an update. Firmware of monitors or controllers is not visible in Windows; use the **Installed ✓** button for those.
- **The driver inside the package is checked.** A site's date is the package release date, and vendors sometimes republish the same driver (ASUS's 2026-07-13 package contains the same 1.0.0.0 driver dated 2026-03-17). For date-tracked drivers linked to Device Manager, if the download is a small .zip (up to 30 MB), the app downloads it once per release date and reads only the driver version from its .inf file. Nothing from the package is extracted or run.
- **Check on start** (can be turned off) and **import** of the old app's `tracker_data.json`.

## Limitations

- Some vendors (e.g. MSI) reject headless Chrome. With **“Use a normal browser identity on sites that block”** turned on (default), the page is opened once more on those sites only, with Chrome presenting itself as normal desktop Chrome; the card then says “read with browser identity”. This may be against the site's rules and may stop working if the site changes its protection; turn the option off if you do not want it. When it is off, or the site still blocks, the card shows **SITE BLOCKS CHECKS** and the version can be entered under “Edit → Latest (manual)”.
- Google Chrome must be installed for pages that are rendered with JavaScript (it runs in a hidden window).
- Only one DriverWatch window can be open at a time, so two windows cannot overwrite each other's list.

## Running from source

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

Build a single-file `.exe` with `build.bat` (output: `dist\DriverWatch.exe`).

Tests: `.venv\Scripts\python -m unittest discover -s tests -t .`

## License

[MIT](LICENSE) © 2026 Bora Şavkar

---

## Türkçe

BIOS, sürücü ve firmware indirme sayfalarını takip eden küçük bir Windows uygulaması. Üreticinin sayfasının linkini eklersiniz, program sayfadaki sürüm numaralarını bulur, siz takip edileni seçersiniz. Her kontrolde aynı yerdeki en yeni sürümü bulur ve bilgisayarınızda yüklü olanla karşılaştırır. Arayüz varsayılan olarak İngilizcedir; **Language / Dil** menüsünden Türkçe seçilebilir.

- **Linkler siz silene kadar kalır** (`%APPDATA%\DriverWatch\items.json`).
- **Takip edilecek sürümü siz seçersiniz;** sayfadaki bütün sürümler bağlamıyla listelenir, beta sürümler kararlıların altında durur.
- **Renkli durum etiketleri:** YENİ SÜRÜM VAR, GÜNCEL, SİTE ENGELLİYOR / KONTROL EDİLEMEDİ / KARŞILAŞTIRILAMADI, YÜKLÜ SÜRÜM GİRİLMEDİ. BIOS, Sürücü, Firmware, Yazılım ve Diğer türlerinin her birinin kendi rengi vardır; listenin üstündeki sekmeler tek bir türü, kayıt sayısını ve kaçında güncelleme olduğunu gösterir.
- **Sürüm sürümle, tarih tarihle karşılaştırılır.** İki tarafta da sürüm numarası varsa sürümlere bakılır; bir tarafta yoksa tarihlere bakılır; uygun çift yoksa program tahmin etmez, “KARŞILAŞTIRILAMADI” der. Kartta kararın neye göre verildiği yazar.
- **Aynı sayfadan birden fazla dosya** eklenebilir; **gizli indirme linkleri** sayfanın verisinden bulunur; işletim sistemi seçilmeden liste göstermeyen sayfalarda bu bilgisayarın sistemi kendiliğinden seçilir.
- **Yüklü sürüm Windows'tan okunur:** BIOS, Windows'un yüklü uygulamalar listesi (kurulum tarihiyle) ve Aygıt Yöneticisi sürücüleri. Uygun kayıt kendiliğinden önerilir.
- **Paketteki sürücüye bakılır:** Tarihle takip edilen, Aygıt Yöneticisi'ne bağlı sürücülerde, indirme linki küçük bir .zip ise (en çok 30 MB) paket bir kez indirilir ve yalnızca içindeki .inf dosyasından sürücü sürümü okunur. Paketten hiçbir dosya açılmaz ya da çalıştırılmaz.
- **Sınırlar:** MSI gibi siteler görünmez Chrome'u reddediyor; “Engelleyen sitelerde normal tarayıcı kimliği kullan” seçeneği açıkken bu sitelerde Chrome normal masaüstü Chrome olarak tanıtılır. Bu sitenin kurallarına aykırı olabilir; istemezseniz kapatın. JavaScript'li sayfalar için Google Chrome kurulu olmalıdır.
- **Lisans:** MIT (bkz. [LICENSE](LICENSE)).
