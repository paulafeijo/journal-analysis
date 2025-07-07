import os
import requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import json
import time

# === Configuration ===
HEADERS = {"User-Agent": "mailto:paulafmed@gmail.com"}
MAX_WORKERS = 5
BASE_URL = "https://api.openalex.org/works"

# === File paths and load data ===
issn = input("Enter ISSN (e.g. 0169-4332): ").strip()
data_dir = os.path.join("data_fetching", "data", issn)
os.makedirs(data_dir, exist_ok=True)

metadata_path = os.path.join(data_dir, f"metadata.json")
with open(metadata_path, "r") as f:
    metadata = json.load(f)

from_year = metadata["from_year"]
until_year = metadata["until_year"]

input_path = os.path.join(data_dir, f"authors.json")
output_path = os.path.join(data_dir, f"author_publications.json")
failed_path = os.path.join(data_dir, f"authors_failed.json")
no_works_path = os.path.join(data_dir, f"authors_no_works.json")

df_authors = pd.read_json(input_path, lines=True)

# === Requests session ===
session = requests.Session()
session.headers.update(HEADERS)

# === Tracking issues ===
failed_authors = []
no_work_authors = []

# === Helper ===
def is_valid_author_id(author_id):
    return isinstance(author_id, str) and "openalex.org/A" in author_id

# === Fetching logic ===
def get_works_for_author(author, max_retries=3):
    author_id = author["author_id"]
    if not is_valid_author_id(author_id):
        failed_authors.append(author)
        return []

    author_id_short = author_id.split("/")[-1]
    base_url = f"{BASE_URL}?filter=author.id:{author_id_short}&per-page=100&cursor=*"
    works = []

    for attempt in range(max_retries):
        try:
            cursor = "*"
            while cursor:
                url = f"{BASE_URL}?filter=author.id:{author_id_short}&per-page=100&cursor={cursor}"
                response = session.get(url, timeout=30)
                if response.status_code != 200:
                    print(f"[HTTP {response.status_code}] Author {author_id_short}")
                    time.sleep(2 ** attempt)
                    break  # Fail and retry whole author

                data = response.json()
                results = data.get("results", [])
                works.extend(results)
                cursor = data.get("meta", {}).get("next_cursor")

                if not cursor:
                    break  # Finished all pages

            if not works:
                no_work_authors.append(author)
                return []

            records = []
            for work in works:
                pub_date = work.get("publication_date")
                if not pub_date:
                    continue

                pub_year = int(pub_date.split("-")[0])
                if pub_year < from_year or pub_year > until_year:
                    continue

                for auth in work.get("authorships", []):
                    if auth.get("author", {}).get("id") == author_id:
                        source_info = work.get("primary_location", {}).get("source", {})
                        issns = source_info.get("issn", [])
                        issn_value = ", ".join(issns) if isinstance(issns, list) else issns

                        records.append({
                            "doi": work.get("doi"),
                            "published_date": work.get("publication_date"),
                            "issn": issn_value,
                            "journal": source_info.get("display_name"),
                            "oa_status": work.get("open_access", {}).get("oa_status", "unknown"),
                            "type": work.get("type"),
                            "author_name": author["author_name"],
                            "author_position": auth.get("author_position"),
                            "orcid": author["orcid"],
                            "affiliation": author["affiliation"],
                            "country": author["country"],
                            "author_id": author["author_id"]
                        })
                        break
            return records

        except Exception as e:
            print(f"[ERROR] Author {author_id_short} failed with exception: {e}")
            time.sleep(2 ** attempt)

    failed_authors.append(author)
    return []

def build_author_publications(df_authors):
    unique_authors = (
        df_authors.drop_duplicates(subset=["author_id"])
                  .dropna(subset=["author_id"])
                  [["author_id", "author_name", "orcid", "affiliation", "country"]]
                  .to_dict(orient="records")
    )

    all_records = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(get_works_for_author, author) for author in unique_authors]
        for future in tqdm(as_completed(futures), total=len(futures), desc="Fetching author publications"):
            all_records.extend(future.result())

    return pd.DataFrame(all_records)

# === Run Script ===
if __name__ == "__main__":

    print(f"🔍 Fetching publications for each author ({from_year}–{until_year})...")
   
    df_publications = build_author_publications(df_authors)
    
    print(f"📄 Total publication records fetched: {len(df_publications)}")
    print(f"❌ Failed authors after retries: {len(failed_authors)}")
    print(f"📭 Authors with no works: {len(no_work_authors)}")

    df_publications.info()

    # Save publications
    df_publications.to_json(output_path, orient="records", lines=True)
    print(f"\n💾 Saved author publications to {output_path}")

    # Save logs
    pd.DataFrame(failed_authors).to_json(failed_path, orient="records", lines=True)
    print(f"\n💾 Saved failed authors to {failed_path}")

    pd.DataFrame(no_work_authors).to_json(no_works_path, orient="records", lines=True)
    print(f"\n💾 Saved authors with no works to {no_works_path}")
