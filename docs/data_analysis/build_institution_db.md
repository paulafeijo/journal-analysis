# Data Analysis – Clustering

## Location

`data_analysis/clustering.py`

## Overview

This script reads a journal-specific publications database (JSON file), aggregates institution-level metrics, and assigns per-region K-Means clusters to institutions based on publication volume and leadership/Openness indicators. It writes the clustered dataset to JSON for downstream analysis/visualization.

## Input

- Interactive prompt: `Enter base ISSN (e.g. 0169-4332)`:
- File on disk: `data_fetching/data/<ISSN>/final_database.json`. Format: JSON Lines (`lines=True`), one record per authorship.

### Expected columns in final_database.json
- `doi` — string DOI
- `affiliation` — institution name
- `country` — ISO-3166 alpha-2 country code (e.g., US, CN)
- `oa_status` — open-access status (values like `gold`, `green`, `bronze`, `hybrid`, `closed`, etc.)
- `author_position` — e.g., `first`, `middle`, `last`
- `issn` — journal ISSN string (e.g., `0169-4332`)

If any of these columns are missing, the script will raise errors during grouping/filters.

## Output

- File: `data_fetching/data/<ISSN>/region_cluster.json` Format: pretty-printed JSON array (`orient="records"`, `indent=2`)
- Console: a `DataFrame.info()` summary of the final table


## Metrics

Given `df_final = read_json(final_database.json, lines=True)`:

1. **Publications per institution**
 
    Group by (`affiliation`, `country`) and count unique DOIs: `publications = nunique(doi)`

2. **Region assignment**

    Each row is mapped to a region using a country-code map:
    - China (CN): `CN`
    - Korea & India: `KR`, `IN`
    - High-Income Research Countries: `US`, `JP`, `DE`, `FR`, `GB`, `IT`, `ES`, `CA`, `AU`, `CH`, `NL`, `BE`, `SE`, `SG`, `AT`, `FI`, `DK`, `IE`, `NO`, `IL`
    - Emerging/Transition Countries: `RU`, `PL`, `CZ`, `BR`, `MX`, `IR`, `TR`, `RO`, `SK`, `VN`, `TH`, `AR`, `PK`, `HU`, `PT`, `SA`, `QA`, `AE`, `MY`, `HK`, `CL`, `EG`, `ZA`, `GR`, `BG`, `ID`, `UA`, `KZ`, `RS`, `SI`, `CO`, `DZ`, `PE`, `VE`, `UY`, `EE`, `PH`, `JO`, `NZ`, `LU`, `HR`, `LV`, `LT`, `MO`, `OM`, `IQ`, `IS`, `BD`, `ET`, `TN`, `LK`, `LB`, `KW`, `CM`, `MT`, `FJ`, `PR`
    - Other: any country code not listed above

3. **Open-access percentage** (`oa_percentage`)
    - Consider OA when `oa_status` is not `hybrid` or `closed`.
    - For each (`affiliation`, `country`): o`a_percentage = (# OA publications) / (publications)` (rounded to 3 decimals)

4. **Leadership percentage** (`leadership_percentage`)
    - Leadership authorships are rows with `author_position ∈ {first, last}`.
    - For each (`affiliation`, `country`): `leadership_percentage = (# first/last authorships) / (# all authorships for that pair)` (rounded to 3 decimals)

5. **Publications in the target journal** (`journal_publications`)
    - Filter `issn == <base_issn>` and count unique DOIs per (`affiliation`, `country`).

The working table is then renamed so `affiliation -> institution` and merged to contain:


| column                | meaning                                     |
|:-----                 |:---                                         |
|`institution`	        | institution name                            |
|`country`                |	ISO-2 code                                |
|`region`	                | region bucket from the map                  |
|`publications`           | unique DOIs across all journals             |
|`oa_percentage`          | share of OA outputs (non-hybrid, non-closed)|
|`leadership_percentage`  | share of first/last authorships             |
|`journal_publications`   | unique DOIs in the input ISSN               |


## Clustering method (per region)

Clustering is performed within each region separately, using four features:

```
features = [
  publications,
  oa_percentage,
  leadership_percentage,
  journal_publications
]
```

For each region:
1. **Edge case**: if the region has < 3 rows, assign:
    - `region_cluster = 0` for all rows
    - `region_cluster_k = 1`
2. **Scaling**: `MinMaxScaler` is fit within the region, scaling each feature to `[0, 1]`.
3. **Model selection**: Choose the number of clusters k that maximizes silhouette score:
    - `k ∈ {2, 3, …, min(10, n_rows-1)}` (implemented as `range(2, min(11, len(df_region))))`
    - `KMeans(n_clusters=k, random_state=42, n_init='auto')`
    - Track the best `k`, best labels, and best score.
4. **Assignment**:
    - `region_cluster` — the chosen K-Means label for each row
    - `region_cluster_k` — the selected k for that region

Finally, all regions are concatenated and written to `region_cluster.json`.

**Determinism**: `random_state=42` ensures repeatable K-Means initialization given identical data.


### Cluster output

Each JSON record contains at least:
- `institution` (str)
- `country` (str, ISO-2)
- `region` (str; one of the buckets above)
- `publications` (int)
- `oa_percentage` (float, 0–1)
- `leadership_percentage` (float, 0–1)
- `journal_publications` (int)
- `region_cluster` (int; cluster ID within region)
- `region_cluster_k` (int; number of clusters used for that region)

## Usage notes & assumptions
- **OA definition**: everything except `hybrid` or `closed` counts as OA. If you track finer OA types, ensure they’re encoded accordingly.
- **Uniqueness**: publication counts use unique DOIs to avoid double-counting multi-authored papers.
- **Leadership**: treats first/last positions as leadership; adjust if your field uses different conventions.
- **Country codes**: must be consistent ISO-2 codes; otherwise the region map will label them as `Other`.
- **Regions are mutually exclusive** by design; update the map if you need different geography.

### Customization tips
- **Change regional buckets**: edit `REGION_MAP` to fit your analysis.
- **Add features**: e.g., citations, collaboration breadth; add to features and compute columns upstream.
- Cap `k` differently: modify the `range(2, min(11, len(df_region)))`.
- **Global clustering**: if you want clusters across all regions, remove the per-region grouping and scale on the full table (note: interpretability vs. size effects).
