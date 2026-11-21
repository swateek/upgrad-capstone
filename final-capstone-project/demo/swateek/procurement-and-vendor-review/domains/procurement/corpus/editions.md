# Edition decisions

Which edition of each instrument is indexed, and why. Checked against the live official pages on 12 November 2026. Hashes are in `manifest.lock.yaml`.

| Instrument | Indexed edition | Decision |
|---|---|---|
| Goods manual | Second Edition, 2024 (`Manual_Goods_2024.pdf`) | As in the brief. The DoE manuals list's `Goods.pdf` (row 4, 16 Aug 2024) is byte-identical (same sha256). The June 2022 goods manual and the 2017 manual are excluded. |
| Non-consultancy services manual | 2025 (`MfPoNCS2025.pdf`) | As in the brief. Listed on DoE manuals as 18 Aug 2025. |
| Consultancy manual | **Second Edition, 2025** (`CS2025.pdf`) | The brief said to take it from the live DoE list rather than guess a file name. DoE lists it as 18 Aug 2025. DGMA lists the same manual as 20 Jun 2025. The June 2022 "Consultancy & Other Services" manual is excluded as superseded. |
| Works manual | **Second Edition, 2025** (`Works_Manual_SE_2025.pdf`) | DoE lists it as 5 Jan 2026. DGMA lists the file as 23 Dec 2025. DGMA also hosts a *draft* second edition, which is excluded. The June 2022 works manual is excluded. |
| GFR 2017 | **Consolidated, updated up to 31 January 2026** (`GFRupdatedupto31012026.pdf`) | The brief's candidates were the 31 Jul 2024 DoE PDF, the 31 Jan 2025 compilation page, and the 31 Jan 2026 DGMA listing. DoE now hosts the 31 Jan 2026 consolidated file directly. It is the latest file that opens, so it is the one indexed. Only Chapter 6 and amended rules the eval set asks about are indexed. |
| DFPR 2024 | Booklet, in force 1 Apr 2024 | As in the brief. |
| GeM GTC | 4.0, Version 1.27, dated 1 Dec 2025 | As in the brief. The version line was verified on page 1 of the downloaded file. |
| GeM Incident Management | Doc no. GeM/Transition/IM/V14.10, applicable w.e.f. 9 Jun 2026 | Taken from the brief's link; the edition was read from pages 1–2. |
| PPP-MII order | Revised 19 Jul 2024 | As in the brief. |
| Model tender (consultancy) | No.F.13/1/2022-PPD, 8 Jun 2023 | Indexed **only** if the by-rule policy split is under 500 documents. Its main job is the bid-case template. |

## Index scope (decided 12 Nov 2026)

- **DoE manuals:** body chapters only. Annexures are excluded: the goods manual from PDF page 275, non-consultancy from 217, consultancy from 216, works from 240. They are forms, templates and FAQs, and including them would breach the 2,000-document cap (2,161 with them, 1,690 without).
- **GFR:** Chapter 6, Rules 142–206. The PDF has no heading for Rule 194, so it isn't indexed.
- **DFPR:** rules and annexures/appendices (the financial-power schedules) are both indexed.
- **Model tender (consultancy):** not indexed, because the policy split is above 500.

Counts per source: `docs/results/phase1-corpus-by_rule.md`.

## Screening snapshot

The GeM delist PDF has five "As on" sections: 31-Jan-2024, 11-Mar-2024, 08-May-2024, 22-May-2024, and 03-Sep-2024. They turned out to be **successive versions of one list**: each newer version is contained in the older ones, and the list shrinks over time. The PDF has 830 rows in total, and the latest version has 130 rows across 9 suppliers. Only the latest version decides present/not present (snapshot date 2024-09-03). Older versions are kept as history. The file was downloaded on 12 Nov 2026, and GeM's disclaimer (page 1) is stored with the snapshot. Built by `pipelines/build_screening.py`.

## Not yet in the manifest

- **Goods and non-consultancy model tender documents.** Only needed if the policy split is under 500. Take them from the DoE circulars area on the day they are needed. Don't guess URLs.
- **DoE office memoranda** (doe.gov.in/orders-circulars/459). Add one only if it changes debarment, mandatory GeM use, or a rule already in the eval set.
- **CPPP debarment hand export** and **OpenSanctions World Bank CSV.** Optional. Each needs its export date and source page recorded.
- **An MSME purchase-preference PDF.** Until one is hashed in, the eval set asks no MSE purchase-preference questions.
