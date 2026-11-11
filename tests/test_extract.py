import unittest

from driverwatch.extract import anchor_from, extract_candidates, is_newer, pick_tracked, same_version

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
