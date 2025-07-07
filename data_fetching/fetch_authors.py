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

# === File paths and load data ===
issn = input("Enter ISSN (e.g. 0169-4332): ").strip()
data_dir = os.path.join("data_fetching", "data", issn)
os.makedirs(data_dir, exist_ok=True)

input_path = os.path.join(data_dir, f"articles.json")
output_path = os.path.join(data_dir, f"authors.json")
failed_path = os.path.join(data_dir, f"failed_dois.txt")

df_articles = pd.read_json(input_path, lines=True)

# === Fetching logic ===
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


# === Run Script ===
if __name__ == "__main__":
    print(f"🔍 Fetching author information for ISSN {issn}...\n")

    df_authors = fetch_all_authors(df_articles)

    print(f"\n📄 Fetched author data for {len(df_articles)} articles.")
    print(f"❌ Failed DOIs after retries: {len(failed_dois)}\n")

    df_authors["region"] = df_authors["country"].apply(classify_region)
    df_authors.info()

    # Save authors
    df_authors.to_json(output_path, orient="records", lines=True)
    print(f"\n💾 Saved author data to {output_path}")

    # Save failed DOIs
    with open(failed_path, "w") as f:
        for doi in failed_dois:
            f.write(doi + "\n")
    print(f"📝 Saved failed DOIs to {failed_path}")