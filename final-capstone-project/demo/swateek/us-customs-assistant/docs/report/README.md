# Technical report

- `report.md`: the report (body about 11 pages on A4, plus roles and appendices; 14 pages printed). Edit this file.
- `report.html`, `report.pdf`: built from `report.md` (steps below). Committed so the report can be read without building it.
- `figures/`: generated PNGs; don't edit them by hand.
- `make_figures.py`: rebuilds the figures from `docs/results/` (official.json, week1_strategies.csv, retrieval_experiment.json). No API calls.
- `print.css`: the print style (copied from the reference app's report).

## Rebuild

```bash
cd backend
uv run --with matplotlib python ../docs/report/make_figures.py

cd ../docs/report
pandoc report.md -s --embed-resources --css print.css --resource-path=. -o report.html
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --no-pdf-header-footer \
  --print-to-pdf=report.pdf "file://$PWD/report.html"
```

Rebuild both after every change to `report.md`, its figures or the results they read, so they don't drift. When the official results change, run `uv run python -m eval.eval_report` first, then the figures, then update §9 and the headline line.
