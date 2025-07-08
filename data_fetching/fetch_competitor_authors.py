import os
import requests
import pandas as pd
import json
import time
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
import sys

# === Constants ===
HEADERS = {"User-Agent": "mailto:paulafmed@gmail.com"}
BASE_URL = "https://api.openalex.org/works/doi:"
MAX_WORKERS = 30
RETRIES = 3
RETRY_DELAY = 2  # seconds

# === Prompt for base ISSN ===
base_issn = sys.stdin.read().strip()
base_dir = os.path.join("data_fetching", "data", base_issn)
competitors_path = os.path.join(base_dir, "top_competitors.json")

# === Read competitor ISSNs ===
df_competitors = pd.read_json(competitors_path)
competitor_issns = df_competitors["issn"].dropna().unique()

# === Author Fetch Function with Retries ===
def fetch_author_data(row):
    doi = row['doi']
    url = f"{BASE_URL}{doi}"
    for attempt in range(RETRIES):
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            if response.status_code == 200:
                data = response.json()
                oa_status = data.get("open_access", {}).get("oa_status", "unknown")
                authorships = data.get("authorships", [])
                authors = []

                for author in authorships:
                    info = author.get("author", {})
                    institutions = author.get("institutions", [])
                    country = institutions[0].get("country_code") if institutions else None
                    authors.append({
                        "doi": doi,
                        "published_date": row.get('published_date'),
                        "issn": row.get('issn'),
                        "oa_status": oa_status,
                        "type": row.get('type'),
                        "author_name": info.get("display_name"),
                        "author_position": author.get("author_position"),
                        "orcid": info.get("orcid"),
                        "affiliation": institutions[0].get("display_name") if institutions else None,
                        "country": country,
                        "author_id": info.get("id")
                    })

                return authors
            else:
                time.sleep(RETRY_DELAY)
        except Exception:
            time.sleep(RETRY_DELAY)
    return []  # Failed after retries

# === Fetch authors from article list ===
def fetch_all_authors(df_articles):
    rows = df_articles.to_dict(orient="records")
    all_author_data = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for result in tqdm(executor.map(fetch_author_data, rows), total=len(rows), desc="Fetching author data (fast)"):
            all_author_data.extend(result)

    return pd.DataFrame(all_author_data)

# === Process each competitor ISSN ===
for i, issn in enumerate(competitor_issns, 1):
    print(f"\n[{i}/{len(competitor_issns)}] 🔍  Fetching author information for ISSN {issn}...")
    competitor_dir = os.path.join("data_fetching", "data", issn)
    articles_path = os.path.join(competitor_dir, "articles.json")
    authors_path = os.path.join(competitor_dir, "authors.json")
    failed_dois_path = os.path.join(competitor_dir, "failed_dois.json")

    if not os.path.exists(articles_path):
        print(f"⚠️ Skipping {issn}: Articles file not found.")
        continue

    df_articles = pd.read_json(articles_path, lines=True)
    df_authors = fetch_all_authors(df_articles)

    # ✅ Defensive check
    if df_authors.empty or 'doi' not in df_authors.columns:
        print(f"⚠️ Skipping {issn}: No valid author data or missing 'doi' column")
        continue

    fetched_dois = set(df_authors['doi'].unique())
    expected_dois = set(df_articles['doi'].unique())
    failed_dois = list(expected_dois - fetched_dois)

    print(f"📊 Fetched authors for {len(fetched_dois)} articles")
    print(f"❌ Failed DOIs: {len(failed_dois)}")

    df_authors.to_json(authors_path, orient="records", lines=True)
    print(f"💾 Saved author data to {authors_path}")

    with open(failed_dois_path, "w") as f:
        json.dump(failed_dois, f)
    print(f"📝 Saved failed DOIs to: {failed_dois_path}")
