# Technical reports

One report per provider. Each folder has the same layout:

| Folder | Runs on | Results it reads |
|---|---|---|
| `siliconflow/` | SiliconFlow (`PROVIDER=siliconflow`): runs 1–5, the content check | `docs/results/siliconflow/` |
| `upgrad/` | The course endpoints, group 031–045 (`PROVIDER=upgrad`): two runs, chunking on bge, safety, preflight | `docs/results/upgrad/` (plus the SiliconFlow files it compares against) |

In each folder:

- `report.md`: the report, body plus appendices when printed on A4 (SiliconFlow: 12 pages of body; upgrad: about 15). Edit this file.
- `report.html`, `report.pdf`: built from `report.md` (steps below).
- `figures/`: generated PNGs. Don't edit them by hand.
- `make_figures.py`: rebuilds the figures from the saved results. No API calls. `upgrad/make_figures.py` reuses the styling and helpers of `siliconflow/make_figures.py` without changing that file or its figures.
- `siliconflow/outline.md`: the section plan and page budgets the SiliconFlow report was written to.

`print.css` here is the print style for both PDFs. **The submitted report is `upgrad/report.pdf`.**

## Rebuild the figures

```bash
cd backend
uv run --with matplotlib python ../docs/report/siliconflow/make_figures.py
uv run --with matplotlib python ../docs/report/upgrad/make_figures.py
```

## Export to PDF

You need pandoc and a Chromium browser. No LaTeX is required. Run in `docs/report/siliconflow` or `docs/report/upgrad`:

```bash
pandoc report.md -s --embed-resources --css ../print.css --resource-path=. -o report.html
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --no-pdf-header-footer \
  --print-to-pdf=report.pdf "file://$PWD/report.html"
```

`report.html` (self-contained, figures embedded) and `report.pdf` are committed so the team can read the reports without building them. Rebuild both after every change to a `report.md` or its figures, so they don't drift from the source.

When SiliconFlow numbers change, update `docs/results/siliconflow/eval-report.md` first, then rebuild the figures and update §9 and the headline line of `siliconflow/report.md`.
