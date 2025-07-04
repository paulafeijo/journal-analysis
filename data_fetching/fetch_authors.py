# data_fetching/fetch_authors.py

import os
import requests
import pandas as pd
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# === Configuration ===
HEADERS = {"User-Agent": "mailto:paulafmed@gmail.com"}  # <-- Use your actual email
BASE_URL = "https://api.openalex.org/works/doi:"
MAX_WORKERS = 10
RETRIES = 3
RETRY_DELAY = 2  # seconds
failed_dois = []

# === Load Article Data ===
input_path = os.path.join("data_fetching", "data", "articles_0169-4332_2020_2024.json")
output_dir = os.path.join("data_fetching", "data")
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, "authors_0169-4332_2020_2024.json")

df_articles = pd.read_json(input_path, lines=True)

# === Fetching Logic ===
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
                    authors.append({
                        "doi": doi,
                        "published_date": row['published_date'],
                        "issn": row['issn'],
                        "oa_status": oa_status,
                        "type": row['type'],
                        "author_name": info.get("display_name"),
                        "author_position": author.get("author_position"),
                        "orcid": info.get("orcid"),
                        "affiliation": institutions[0].get("display_name") if institutions else None,
                        "country": institutions[0].get("country_code") if institutions else None,
                        "author_id": info.get("id")
                    })
                return authors
            else:
                time.sleep(RETRY_DELAY)
        except Exception:
            time.sleep(RETRY_DELAY)
    failed_dois.append(doi)
    return []

def fetch_all_authors(df_articles):
    all_author_data = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(fetch_author_data, row) for _, row in df_articles.iterrows()]
        for future in tqdm(as_completed(futures), total=len(futures), desc="Fetching author data"):
            all_author_data.extend(future.result())
    return pd.DataFrame(all_author_data)

# === Run Script ===
if __name__ == "__main__":
    print("📥 Loading article data...")
    df_authors = fetch_all_authors(df_articles)
    print(f"❌ Failed DOIs after retries: {len(failed_dois)}")

    df_authors.info()
    df_authors.to_json(output_path, orient="records", lines=True)
    print(f"💾 Author data saved to: {output_path}")


# Save failed DOIs to a file for retry
failed_path = os.path.join(output_dir, "failed_dois.txt")
with open(failed_path, "w") as f:
    for doi in failed_dois:
        f.write(doi + "\n")

print(f"📝 Saved failed DOIs to {failed_path}")
