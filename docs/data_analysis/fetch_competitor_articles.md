# Data Fetching – Fetch Competitor Articles

## fetch_articles.py

Step 5 of `main_script.py`.

## Location

`data_fetching/fetch_competitor_articles.py`

## Overview
Fetches articles (DOI, published date, and article type) for each **competitor journal ISSN** over the same rolling **last full 5 calendar years up to last year** as the base journal.
The script uses the Crossref API with cursor-based pagination to gather article metadata and stores:
- **JSON Lines** with article records per competitor journal: `data_fetching/data/<ISSN>/articles.json`
- **Metadata** about the fetch: `data_fetching/data/<ISSN>/metadata.json`

It also keeps track of:
- Failed ISSNs (API request errors)
- Empty ISSNs (no articles found in date range)

## Inputs

### Required
- **ISSN** (string) — provided via **STDIN** from ``main_script.py`.

   The script reads the ISSN like:
   
   `base_issn = sys.stdin.read().strip()`

- **Dates** – Reads `data_fetching/data/<BASE_ISSN>/metadata.json` for:
  - `from_year`
  - `until_year`
  
  These are used to construct the date range:
  ```
  from_date = <from_year>-01-01
  until_date = <until_year>-12-31
  ```

- **Competitor ISSNs** –  Reads `data_fetching/data/<BASE_ISSN>/top_competitors.json` to get competitor ISSNs (excluding `unknown issn`).


### Crossref API
- Endpoint: `https://api.crossref.org/works`
- Query params include:
  - `filter=issn:<ISSN>,from-pub-date:<YYYY-MM-DD>,until-pub-date:<YYYY-MM-DD>`
  - `rows=1000`
  - `cursor=*` (then uses `next-cursor`)
  - `mailto=<your email>` (used for Crossref polite pool)


## Outputs

### Files (per competitor ISSN)
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


- **Error logs (stored under base ISSN folder)**
  - `failed_issns.txt` — ISSNs where API requests failed
  - `empty_issns.txt` — ISSNs with no articles found

### Console output
- For each competitor ISSN:
 
  - `📘 [idx/total] Fetching articles for ISSN <ISSN>...`
  - Progress bar labeled `📦 <ISSN>` showing articles fetched so far
  - `🔢 Estimated total results for <ISSN>: <N>` (printed on first page)
  - `💾 Saved <count> articles to: ...`
  - `🗃️ Saved metadata to ...`

- At the end:
  - `❌ Failed ISSNs: <count>`
  - `📭 ISSNs with no articles: <count>`

## Usage

### Parameters & Configuration
- `rows = 1000` per page
- `email` (used as `mailto` param) is set in the script; update to your own
- Sleep of 1 second between pages to respect API limits

### Error Handling & Retries
- Network/API errors are caught and the ISSN is added to `failed_issns`
- Empty responses result in the ISSN being added to `empty_issns`

### Data Shaping Details
- Publication date: pulls `published-print` if available, else `published-online` → `date-parts`
- Joins available parts with `-` and zero‑pads (e.g., `2022-03` or `2022-03-07`)
- If no date parts, `published_date` is `null`
- ISSNs: if multiple, combined as a comma‑separated string

### Dependencies
- `requests`, `pandas`, `tqdm`
= Standard library: `time`, `datetime`, `json`, `os`, `sys`
