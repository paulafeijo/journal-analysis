# Data Fetching – Fetch Articles

## fetch_articles.py

Step 1 of `main_script.py`.

## Location

`data_fetching/fetch_articles.py`

## Overview
Fetches articles (DOI, published date, and article type) and stores metadata (issn, from year, until year, and retrived on) from the Crossref API for the **base journal ISSN** over the **last full 5 calendar years up to last year** (rolling window).  

The script paginates using Crossref’s cursor API and saves:
- **JSON Lines** with article records: `data_fetching/data/<ISSN>/articles.json`
- **Metadata** about the fetch: `data_fetching/data/<ISSN>/metadata.json`

## Inputs

### Required
- **ISSN** (string) — provided via **STDIN** from ``main_script.py`.

> The script reads the ISSN like:  
> `base_issn = sys.stdin.read().strip()`

### Date window (computed)
- `today = datetime.today()`
- `last_year = today.year - 1`
- `from_year = last_year - 4`  
- Fetches from `from_year-01-01` to `last_year-12-31`

### Crossref API
- Endpoint: `https://api.crossref.org/works`
- Query params include:
  - `filter=issn:<ISSN>,from-pub-date:<YYYY-MM-DD>,until-pub-date:<YYYY-MM-DD>`
  - `rows=1000`
  - `cursor=*` (then uses `next-cursor`)
  - `mailto=<your email>` (used for Crossref polite pool)


## Outputs

### Files
- **Articles (JSON Lines)**: `data_fetching/data/<ISSN>/articles.json`  
  Each line is a JSON object with keys:
  - `doi` — string
  - `published_date` — `YYYY`, `YYYY-MM`, or `YYYY-MM-DD` (zero‑padded where parts exist; may be `null` if date missing)
  - `issn` — comma‑separated string of ISSNs
  - `type` — Crossref work type (e.g., `journal-article`)

- **Metadata (JSON)**: `data_fetching/data/<ISSN>/metadata.json`  
  Keys:
  - `issn` — input ISSN
  - `from_year` — start year
  - `until_year` — end year (last year)
  - `retrieved_on` — `YYYY-MM-DD`

### Console output
- Progress bar via `tqdm` (initialized from `message.total-results`)
- Summary counts (records and pages)
- `pandas.DataFrame.info()` for a quick schema glance

## Usage

### Parameters & Configuration
- `rows = 1000` per page
- `email` (used as `mailto` param) is set in the script; update to your own
- Uses cursor-based pagination until `next-cursor` is absent

### Error Handling & Retries
- Wraps requests in `try/except` for RequestException
- On failure, prints the error and waits 5 seconds before retrying the request loop

### Data Shaping Details
- Publication date: pulls `published-print` if available, else `published-online` → `date-parts`
- Joins available parts with `-` and zero‑pads (e.g., `2022-03` or `2022-03-07`)
- If no date parts, `published_date` is `null`
- ISSNs: if multiple, combined as a comma‑separated string

### Dependencies
- `requests`, `pandas`, `tqdm`
= Standard library: `time`, `datetime`, `json`, `os`, `sys`