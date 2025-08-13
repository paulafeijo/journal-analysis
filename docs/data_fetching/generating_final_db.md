# Data Fetching – Generate Final Database

## generating_final_db.py

Step 7 of `main_script.py`.

## Location

`data_fetching/generating_final_db.py`

## Overview
Combines the **base journal’s author data with the top competitors’ author data, enriches records with region buckets, per‑DOI citation/reference counts, a journal‑author flag (whether an author also publishes in the base journal), and resolved journal names from ISSNs. Finally, it writes a newline‑delimited JSON file final_database.json under the base ISSN’s folder. 

## Inputs

### Required
- **Base ISSN** (string) — provided via **STDIN** from ``main_script.py`.
- **Files from base ISSN folder**
  - `authors.json` (JSON Lines) — base journal authors dataset (from `fetch_authors.py`)
  - `top_competitors.json` — competitor ranking (from `top_competitors_citations.py`).
  - `citations.json`, `references.json` — DOI‑to‑DOI link tables (from `references_citations.py`). 

- **Files from each competitor folder**
  - `authors.json` (JSON Lines) — competitor authors dataset (from `fetch_competitor_authors.py`); loaded for each of the Top‑10 ISSNs; missing files are reported.


## Outputs

### Final dataset:
`data_fetching/data/<ISSN>/authors.json`

Each record originates from either the base journal or a Top‑10 competitor and is row‑per‑author. The script appends/enriches the following fields:
- `region` — derived from a fixed `REGION_MAP` using the author’s `country` code (e.g., “China (CN)”, “Korea & India”, “High‑Income Research Countries”, “Emerging/Transition Countries”, “Other”).
- `cites` — count of times this DOI appears as a cited item in `citations.json`.
- `referenced` — count of times this DOI appears as a reference in `references.json`.
- `journal_author` — `'yes'/'no'` flag: whether the `author_id` also appears among authors of articles whose `issn` matches the base ISSN. (The script explodes multi‑ISSN strings before checking.)
- `journal` — human‑readable journal title resolved from the record’s issn. Missing titles remain `null`. 

Additionally, the final file contains all columns coming from the input author records (e.g., `doi`, `published_date`, `issn`, `oa_status`, `type`, `author_name`, `author_position`, `orcid`, `affiliation`, `country`, `author_id`). (These originate from the previously saved authors datasets for base and competitors.)

### Console output
- Loading summaries for competitors’ author files and quick null checks for the journal column per frame.
- Total combined author rows (base + competitors).
- Messages confirming addition of `region`, `cites`, `referenced`, and `journal_author`.
- Progress for resolving journal names from ISSNs and a count of final missing journal titles.
- Final save path for the database. 

## Usage

### External APIs used during enrichment
Crossref Journals API — resolves journal titles from ISSNs: https://api.crossref.org/journals/<ISSN> (8s timeout; simple error messages on failure).

### Data shaping
- Loads base inputs (`authors.json`, `top_competitors.json`, `citations.json`, `references.json`); keep Top‑10 competitors by `total_score`.
- Loads competitors’ authors for each Top‑10 ISSN (adds `source_issn`, warns if missing).
- Concatenates competitors + base into `df_final`.
- Adds region via `REGION_MAP` and `classify_region()`. 
- Attaches counts: `cites` and `referenced` using value counts from citation/reference link files.
- Marks `journal_author` by checking if an author also appears in rows whose issn equals the base ISSN (after exploding the ISSN list).
- Resolves journal titles from ISSNs using the Crossref Journals API; map into the dataset.
- Writes `final_database.json` (newline‑delimited) to the base ISSN folder.

### Dependencies
- Python packages: `requests`, `pandas`, `tqdm`.
- Standard library: `os`, `sys`, `time`, `json`.


