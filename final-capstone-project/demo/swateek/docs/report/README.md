# Technical report

- `report.md`: the report (12 pages of body plus appendices when printed on A4). Edit this file.
- `report.html`, `report.pdf`: built from `report.md` (steps below).
- `outline.md`: the section plan and page budgets it was written to.
- `figures/`: generated PNGs. Don't edit them by hand.
- `make_figures.py`: rebuilds the figures from `docs/results/*.json`. No API calls.
- `print.css`: the print style for the PDF.

## Rebuild the figures

```bash
cd backend
uv run --with matplotlib python ../docs/report/make_figures.py
```

## Export to PDF

You need pandoc and a Chromium browser. No LaTeX is required.

```bash
cd docs/report
pandoc report.md -s --embed-resources --css print.css --resource-path=. -o report.html
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --no-pdf-header-footer \
  --print-to-pdf=report.pdf "file://$PWD/report.html"
```

`report.html` (self-contained, figures embedded) and `report.pdf` are committed so the team can read the report without building it. Rebuild both after every change to `report.md` or the figures, so they don't drift from the source.

When the numbers change (for example after the course-endpoint re-run), update `docs/results/eval-report.md` first. Then rebuild the figures and update the tables in §9 and the headline line at the top of the report.
