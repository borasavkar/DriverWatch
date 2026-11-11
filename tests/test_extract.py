import unittest

from driverwatch.extract import anchor_from, extract_candidates, is_newer, pick_tracked, same_version, title_for
from driverwatch.fetch import find_files

AMD = """Windows 11 - 64-Bit Edition
Driver
AMD Chipset Drivers
Revision Number
{chip}
File Size
79 MB
Release Date
{chipdate}
Download *
AMD Chipset Drivers
Driver Details
Package Includes:
AMD RAID Installer (SATA, NVMe RAID)
Revision Number
8.03.24.733
File Size
115 MB
Release Date
2026-04-16
Download *
AMD RAID Installer (SATA, NVMe RAID)
Driver Details
AMD RAID Driver (SATA, NVMe RAID)
Revision Number
9.3.3.00291
File Size
4.9 MB
Release Date
2026-04-16
Download *
"""

RAZER = """Razer Wolverine V3 Pro Firmware Updater | RZ06-0520
Updated: 14-Aug-2026 | Answer ID: 14630
Applicable models:
RZ06-0520
Firmware updater {v}
https://rzr.to/b556gr | March 12, 2026
Release notes
Copyright © 2026 Razer Inc. All rights reserved.
"""

MSI = """BIOS
AMI BIOS
Version
{a}
Release Date
2026-09-07
File Size
16.12 MB
Download
AMI BIOS
Version
{b}
Release Date
2026-06-02
File Size
16.10 MB
Download
"""


ASUS = """Lütfen İşletim Sistemi Seçin
Windows 11 64-bit
Driver Package
ASUS_XG27ACSR_WHQL_Driver
Sürüm -
53.68 KB
{d}
SHA-256 :A5688A0D10D6FB52FDAA3F187A99531522FA32CC0B09CF4D94147B4D7855B19F
İNDİR
Software and Utility
ASUS_DisplayWidget_Center
Sürüm -
0 KB
2025/01/09
SHA-256 :46AB2782D53827B57BCA94785EC15C9C576898BEA226E4D738634D10BF77C6CD
İNDİR
"""


class DateTrackingTests(unittest.TestCase):
    FILES = ["https://dlcdnets.asus.com/pub/ASUS/LCD%20Monitors/XG27ACSR/ASUS_XG27ACSR_WHQL_Driver.zip"]

    def test_asus_items_without_version_are_tracked_by_date(self):
        c = extract_candidates(ASUS.format(d="2026/07/13"), [], self.FILES)
        by_title = {title_for(x): x for x in c}
        drv = by_title["ASUS_XG27ACSR_WHQL_Driver"]
        self.assertTrue(drv.by_date)
        self.assertEqual(drv.version, "2026-07-13")
        self.assertEqual(drv.link, self.FILES[0])
        self.assertIn("ASUS_DisplayWidget_Center", by_title)
        # yeni dosya yayınlanınca aynı kalem bulunur, diğerine karışmaz
        picked, _ = pick_tracked(extract_candidates(ASUS.format(d="2026/12/02"), [], self.FILES), anchor_from(drv))
        self.assertEqual(picked.version, "2026-12-02")
        self.assertTrue(is_newer("2026-12-02", "2026-07-13"))

    def test_hidden_file_paths_resolve_to_download_host(self):
        raw = ('<a href="https://dlcdnets.asus.com/pub/ASUS/nb/x.pdf">x</a>'
               '"/pub/ASUS/LCD Monitors/XG27ACSR/ASUS_XG27ACSR_WHQL_Driver.zip"'
               '"https://dlcdnwebimgs.asus.com/gain/abc"')
        self.assertEqual(find_files(raw, "https://www.asus.com/tr/x/"), self.FILES)


ROG = """ROG Strix XG27ACS Gen2 (XG27ACSR) | 27 - 31.5 inç | Gaming Monitörler | ROG
BIOS & Firmware
Firmware
ASUS_XG27ACSR_MCM102
Sürüm {v}
10.1 MB 2026/07/30
SHA-256 :D3B9E151BA522065891ECD806B8FCA37B1C205188FB63A5777234390BF555CB7
Optimize sleep wake-up function and ELMB effect.
DOWNLOAD
Disclaimer
USB 3.0, 3.1, 3.2 ve/veya Type-C'nin gerçek aktarım hızı, ana bilgisayarın işlem hızı, dosya özellikleri ve diğer etkenlere bağlıdır.
"""


class LabeledVersionTests(unittest.TestCase):
    def test_rog_firmware_label_version_and_no_prose_numbers(self):
        files = ["https://dlcdnets.asus.com/pub/ASUS/LCD%20Monitors/XG27ACSR/ASUS_XG27ACSR_MCM102.zip"]
        c = extract_candidates(ROG.format(v="MCM102"), [], files)
        self.assertEqual(c[0].version, "MCM102")
        self.assertEqual(c[0].date, "2026-07-30")
        self.assertEqual(c[0].link, files[0])
        versions = [x.version for x in c]
        for junk in ("3.0", "3.1", "3.2", "31.5"):
            self.assertNotIn(junk, versions)
        picked, _ = pick_tracked(extract_candidates(ROG.format(v="MCM103")), anchor_from(c[0]))
        self.assertEqual(picked.version, "MCM103")
        self.assertTrue(is_newer("MCM103", "MCM102"))


MSI_BETA = """AMI BIOS
{beta}(Beta version)
Release Date
2026-03-04
Download
AMI BIOS
{stable}
Release Date
2026-09-09
Download
"""


class BetaTests(unittest.TestCase):
    def test_stable_first_and_tracked_separately_from_beta(self):
        c = extract_candidates(MSI_BETA.format(beta="7E16v1CB", stable="7E16v1D4"))
        self.assertEqual(c[0].version, "7E16v1D4")
        picked, _ = pick_tracked(extract_candidates(MSI_BETA.format(beta="7E16v1D51", stable="7E16v1D5")), anchor_from(c[0]))
        self.assertEqual(picked.version, "7E16v1D5")


class PackageCompareTests(unittest.TestCase):
    def test_repackaged_same_driver_is_up_to_date(self):
        from driverwatch.core import Item

        it = Item(url="x", installed="2026-03-17", latest="2026-07-13", installed_device="ROG STRIX XG27ACSR",
                  installed_dev_version="1.0.0.0", pkg_version="1.0.0.0", pkg_date="2026-03-17",
                  anchor={"shape": "date"})
        it.recompute_state()
        self.assertEqual(it.state, "ok")
        it.pkg_version, it.pkg_date = "1.0.1.0", "2026-07-01"
        it.recompute_state()
        self.assertEqual(it.state, "update")


class ExtractTests(unittest.TestCase):
    def test_amd_finds_chipset_first_and_skips_file_size(self):
        c = extract_candidates(AMD.format(chip="8.09.28.1124", chipdate="2026-10-21"))
        self.assertEqual(c[0].version, "8.09.28.1124")
        self.assertEqual(c[0].date, "2026-10-21")
        self.assertNotIn("4.9", [x.version for x in c])

    def test_amd_tracks_chipset_not_raid_after_update(self):
        c = extract_candidates(AMD.format(chip="8.09.28.1124", chipdate="2026-10-21"))
        anchor = anchor_from(c[0])
        c2 = extract_candidates(AMD.format(chip="8.10.02.210", chipdate="2026-12-01"))
        picked, _ = pick_tracked(c2, anchor)
        self.assertEqual(picked.version, "8.10.02.210")
        self.assertEqual(picked.date, "2026-12-01")

    def test_razer(self):
        c = extract_candidates(RAZER.format(v="v2.04.00_r1"))
        self.assertEqual(c[0].version, "v2.04.00_r1")
        self.assertEqual(c[0].date, "2026-03-12")
        self.assertEqual(c[0].link, "https://rzr.to/b556gr")
        anchor = anchor_from(c[0])
        picked, _ = pick_tracked(extract_candidates(RAZER.format(v="v2.05.01_r2")), anchor)
        self.assertEqual(picked.version, "v2.05.01_r2")

    def test_msi_list_picks_highest(self):
        c = extract_candidates(MSI.format(a="7E16v1D4", b="7E16v1D3"))
        anchor = anchor_from([x for x in c if x.version == "7E16v1D3"][0])
        picked, _ = pick_tracked(extract_candidates(MSI.format(a="7E16v1D5", b="7E16v1D4")), anchor)
        self.assertEqual(picked.version, "7E16v1D5")

    def test_compare(self):
        self.assertTrue(same_version("1.D4", "7E16v1D4"))
        self.assertTrue(is_newer("7E16v1D5", "1.D4"))
        self.assertFalse(is_newer("7E16v1D4", "1.D4"))
        self.assertTrue(is_newer("8.09.28.1124", "8.02.18.557"))
        self.assertFalse(is_newer("8.02.18.557", "8.09.28.1124"))
        self.assertTrue(is_newer("v2.04.00_r2", "v2.04.00_r1"))
        self.assertFalse(same_version("1.4", "11.4"))


if __name__ == "__main__":
    unittest.main()
