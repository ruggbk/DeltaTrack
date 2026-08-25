# DeltaTrack Notebooks

Financial classifier and analysis tools for DeltaTrack bill data.

## Files

| File | Purpose |
|---|---|
| `classify_bill.py` | Rule-based classifier — imported by all notebooks and scripts |
| `02_financial_report.ipynb` | Financial summary report for a single bill |
| `03_classifier_stress_test.ipynb` | Interactive classifier validation across multiple bills |
| `stress_test_analysis.py` | Script: parses all 7 reference bills, reports unknowns and FP risks |
| `stress_test_detail.py` | Script: shows full text of unknown nodes per bill type |
| `classifier_notes.md` | Design rationale: pattern decisions and intentionally-unknown categories |

## Running the scripts

From the `DeltaTrack/` directory:

```bash
uv run python financial_classifier/stress_test_analysis.py
uv run python financial_classifier/stress_test_detail.py approp        # or: reconciliation, authorization, all
```

Scripts require bill XML files downloaded to `bills/` (gitignored). Download with:

```bash
uv run python fetch_bills.py download 118 hr 4366
```

## Dependencies

The scripts use only stdlib and the project's core dependencies — no extra install needed.

The Jupyter notebooks use `pandas`. It is not in the project's `uv` env (it's analysis-only, not part of the library). Install it in your local environment:

```bash
pip install pandas   # or: uv pip install pandas
```
