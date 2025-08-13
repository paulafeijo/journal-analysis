# Data Fetching – Error Tracking Report

## error_tracking.py

Step 8 of `main_script.py`.

## Location

`data_fetching/error_tracking.py`

## Overview
Builds a compact error report covering:

1. base‑journal author fetch failures;
2. competitor article coverage;
3. competitor author fetch failure rates (plus a weighted average across competitors).

Results are saved to `error_report.json` and also printed as a readable table. It optionally pulls journal names from the final database (fallback: `top_competitors.json`) for friendlier rows.

## Inputs

### Required
- **Base ISSN** (string) — provided via **STDIN** from ``main_script.py`. Used to locate the folder `data_fetching/data/<BASE_ISSN>`.

## Files under the base ISSN folder
`data_fetching/data/<BASE_ISSN>/`
- `articles.json` (JSON Lines) — base journal articles; used to count total DOIs.
- `failed_dois.txt` — from the base author fetch; one DOI per line. If absent, treated as empty.
- `top_competitors.json` — ranked venues; top 10 ISSNs are used.
- `final_database.json` (optional) — to map ISSN→journal name for prettier report rows; if missing or unreadable, the script warns and proceeds.

## Files under each competitor folder
`data_fetching/data/<COMPETITOR_ISSN>/`
- `articles.json` — to count total competitor DOIs.
- `failed_dois.json` — competitor author‑fetch failures (JSON array).

## Outputs

### Report file
`data_fetching/data/<BASE_ISSN>/error_report.json` — array of rows with:
- `object` — “base issn”, “competitor articles”, “competitor average”, or a journal name.
- `issn` — ISSN or “all below”.
- `total`— items considered (DOIs).
- `failed` — failures counted.
- `error_percent` — percentage (rounded to 2 decimals).

Saved and then echoed to console as a formatted table.

### Console output
- Save confirmation:`📄 Error report saved to: data_fetching/data/<BASE_ISSN>/error_report.json`.
- Pretty table with columns `object | issn | total | failed | error_percent`.

## Usage

### Measurements
- Base author fetch error% = `len(failed_dois.txt) / len(base articles.json) × 100`.
- Competitor articles coverage error% = `missing_article_files / (sum competitor articles + missing files) × 100`.
- Per‑competitor author error% = `if total_comp_dois > 0 then len(failed_dois.json)/total_comp_dois × 100 else 100`.
- Competitor average error% (weighted) = `(Σ failed across competitors / Σ total across competitors) × 100`.

### Flow
- Loads context: base folder; optionally reads `final_database.json` to derive an ISSN→journal mapping (warns if missing).
- Picks competitors: reads `top_competitors.json`, keeps Top 10 ISSNs.
- Base metrics: counts base DOIs, reads `failed_dois.txt`, computes base author error%.
- Competitor article coverage: sums competitor `articles.json` sizes; counts missing files; computes coverage error%.
- Competitor author metrics: per ISSN, reads totals & `failed_dois.json`; computes error% and attach a journal name (from final DB or from `top_competitors.json`, else `Unknown`).
- Average competitor error (weighted) and assemble rows: adds summary rows (“base issn”, “competitor articles”, “competitor average”) then each competitor row.
- Saves & prints: writes `error_report.json`; prints save path and a formatted table.

### Dependencies
- Python packages: `pandas`.
- Standard library: `os`, `sys`, `json`.