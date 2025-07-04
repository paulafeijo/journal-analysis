import os
import requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# === Config ===
HEADERS = {"User-Agent": "mailto:paulafmed@gmail.com"}
MAX_WORKERS = 10
BASE_URL = "https://api.openalex.org/works"

# === File Paths ===
base_dir = os.path.join("data_fetching", "data")
input_path = os.path.join(base_dir, "authors_merged_0169-4332_2020_2024.json")
output_path = os.path.join(base_dir, "author_publications_0169-4332_2020_2024.json")

# === Region Mapping ===
REGION_MAP = {
    "China (CN)": ["CN"],
    "Korea & India": ["KR", "IN"],
    "High-Income Research Countries": [
        "US", "JP", "DE", "FR", "GB", "IT", "ES", "CA", "AU", "CH", "NL", "BE", "SE", "SG",
        "AT", "FI", "DK", "IE", "NO", "IL"
    ],
    "Emerging/Transition Countries": [
        "RU", "PL", "CZ", "BR", "MX", "IR", "TR", "RO", "SK", "VN", "TH", "AR", "PK", "HU",
        "PT", "SA", "QA", "AE", "MY", "HK", "CL", "EG", "ZA", "GR", "BG", "ID", "UA", "KZ",
        "RS", "SI", "CO", "DZ", "PE", "VE", "UY", "EE", "PH", "JO", "NZ", "LU", "HR", "LV",
        "LT", "MO", "OM", "IQ", "IS", "BD", "ET", "TN", "LK", "LB", "KW", "CM", "MT", "FJ", "PR"
    ],
    "Other": []  # Fallback
}

def classify_region(country_code):
    for region, countries in REGION_MAP.items():
        if country_code in countries:
            return region
    return "Other"

# === Requests session ===
session = requests.Session()
session.headers.update(HEADERS)

# === Tracking issues ===
failed_authors = []
no_work_authors = []

def get_works_for_author(author):
    author_id = author["author_id"]
    if not author_id:
        failed_authors.append(author)
        return []

    author_id_short = author_id.split("/")[-1]
    url = f"{BASE_URL}?filter=author.id:{author_id_short}&per-page=100"

    try:
        response = session.get(url, timeout=30)
        if response.status_code != 200:
            failed_authors.append(author)
            return []

        works = response.json().get("results", [])
        if not works:
            no_work_authors.append(author)

        records = []
        for work in works:
            for auth in work.get("authorships", []):
                if auth.get("author", {}).get("id") == author_id:
                    source_info = work.get("primary_location", {}).get("source", {})
                    issns = source_info.get("issn", [])
                    if isinstance(issns, list):
                        issn_value = ", ".join(issns)
                    elif isinstance(issns, str):
                        issn_value = issns
                    else:
                        issn_value = None

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

    except Exception:
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

# === Main Execution ===
if __name__ == "__main__":
    print("📥 Loading merged author data...")
    df_authors = pd.read_json(input_path, lines=True)

    print("🔍 Fetching publications for each author...")
    df_publications = build_author_publications(df_authors)

    # Add region classification
    df_publications["region"] = df_publications["country"].apply(classify_region)

    # Save final dataset (overwrite original output)
    df_publications.to_json(output_path, orient="records", lines=True)

    # Save logs
    pd.DataFrame(failed_authors).to_json(os.path.join(base_dir, "authors_failed.json"), orient="records", lines=True)
    pd.DataFrame(no_work_authors).to_json(os.path.join(base_dir, "authors_no_works.json"), orient="records", lines=True)

    # Summary
    print("\n✅ Completed fetching publications.")
    print(f"📊 Total records: {len(df_publications)}")
    print(f"❌ Failed authors: {len(failed_authors)}")
    print(f"📭 Authors with no works: {len(no_work_authors)}")
    print(f"💾 Data saved to: {output_path}")
