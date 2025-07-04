import os
import requests
import pandas as pd
import logging
import time
from tqdm import tqdm

# === Suppress noisy logs ===
logging.getLogger("requests").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)

# === Constants ===
HEADERS = {"User-Agent": "mailto:paulafmed@gmail.com"}
BASE_URL = "https://api.openalex.org/works/doi:"
RETRIES = 3
RETRY_DELAY = 2  # seconds

# === File paths ===
base_dir = os.path.join("data_fetching", "data")
failed_dois_path = os.path.join(base_dir, "failed_dois.txt")
author_data_path = os.path.join(base_dir, "authors_0169-4332_2020_2024.json")
retry_output_path = os.path.join(base_dir, "retried_authors.json")
still_failed_path = os.path.join(base_dir, "still_failed_dois.txt")

# === Load failed DOIs ===
with open(failed_dois_path, "r") as f:
    failed_dois = [line.strip() for line in f.readlines() if line.strip()]

# (Optional) Load previously saved author data
df_authors = pd.read_json(author_data_path, lines=True)

author_data = []
still_failed = []

for doi in tqdm(failed_dois, desc="🔁 Retrying failed DOIs"):
    url = f"{BASE_URL}{doi}"

    for attempt in range(RETRIES):
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            if response.status_code == 200:
                data = response.json()
                oa_status = data.get("open_access", {}).get("oa_status", "unknown")
                authorships = data.get("authorships", [])

                for author in authorships:
                    info = author.get("author", {})
                    institutions = author.get("institutions", [])
                    author_data.append({
                        "doi": doi,
                        "oa_status": oa_status,
                        "author_name": info.get("display_name"),
                        "author_position": author.get("author_position"),
                        "orcid": info.get("orcid"),
                        "affiliation": institutions[0].get("display_name") if institutions else None,
                        "country": institutions[0].get("country_code") if institutions else None,
                        "author_id": info.get("id")
                    })
                break  # success, no need to retry
            else:
                time.sleep(RETRY_DELAY)
        except Exception:
            time.sleep(RETRY_DELAY)
    else:
        still_failed.append(doi)

# === Save new author data ===
df_retry_authors = pd.DataFrame(author_data)
df_retry_authors.to_json(retry_output_path, orient="records", lines=True)

# === Save DOIs that still failed ===
with open(still_failed_path, "w") as f:
    for doi in still_failed:
        f.write(doi + "\n")

# === Report ===
print(f"\n✅ Retrieved {len(df_retry_authors)} authors from retry.")
print(f"❌ Still failed DOIs: {len(still_failed)}")
print(f"💾 Saved new data to {retry_output_path}")

# === Merge retry results into original authors dataset ===
df_original = pd.read_json(author_data_path, lines=True)
df_combined = pd.concat([df_original, df_retry_authors], ignore_index=True)

# Drop exact duplicates by DOI + author name (adjust if needed)
df_combined.drop_duplicates(subset=["doi", "author_name"], inplace=True)

# Save merged dataset
merged_path = os.path.join(base_dir, "authors_merged_0169-4332_2020_2024.json")
df_combined.to_json(merged_path, orient="records", lines=True)

print(f"🧩 Merged dataset saved to: {merged_path}")
print(f"📊 Final author count: {len(df_combined)}")

