import os
import requests
import pandas as pd
import time
from datetime import datetime
from tqdm import tqdm
import json
import sys

# === Config ===
api_url = "https://api.crossref.org/works"
email = "paulafmed@gmail.com"
today = datetime.today()

# === Load base ISSN ===
base_issn = sys.stdin.read().strip()
base_dir = os.path.join("data_fetching", "data", base_issn)

# === Read metadata to get date range ===
metadata_path = os.path.join(base_dir, f"metadata.json")
with open(metadata_path, "r") as f:
    metadata = json.load(f)

from_year = metadata["from_year"]
until_year = metadata["until_year"]
from_date = f"{from_year}-01-01"
until_date = f"{until_year}-12-31"

# === Read competitor ISSNs ===
competitor_path = os.path.join(base_dir, "top_competitors.json")
df_competitors = pd.read_json(competitor_path)

# === Error tracking lists ===
failed_issns = []
empty_issns = []

# === Fetching for a single ISSN ===
def fetch_articles_for_issn(issn):
    cursor = "*"
    articles = []
    total_results = None
    page_count = 0

    with tqdm(desc=f"📦 {issn}", unit="records", dynamic_ncols=True) as pbar:
        while True:
            params = {
                "filter": f"issn:{issn},from-pub-date:{from_date},until-pub-date:{until_date}",
                "rows": 1000,
                "cursor": cursor,
                "mailto": email
            }

            try:
                response = requests.get(api_url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
            except requests.exceptions.RequestException as e:
                print(f"\n❌ API request failed for {issn}: {e}")
                failed_issns.append(issn)
                break

            message = data.get("message", {})
            items = message.get("items", [])
            next_cursor = message.get("next-cursor")

            if total_results is None:
                total_results = message.get("total-results", 0)
                print(f"🔢 Estimated total results for {issn}: {total_results}\n")

            if not items:
                break

            for item in items:
                doi = item.get("DOI")
                pub_date_parts = item.get("published-print", item.get("published-online", {})).get("date-parts", [[None]])
                pub_date = "-".join(str(part) for part in pub_date_parts[0]) if pub_date_parts[0][0] else None
                issns = item.get("ISSN", [])
                article_type = item.get("type", None)

                articles.append({
                    "doi": doi,
                    "published_date": pub_date,
                    "issn": ", ".join(issns),
                    "type": article_type
                })

            pbar.update(len(items))
            page_count += 1

            if not next_cursor:
                break

            cursor = next_cursor
            time.sleep(1)

    if not articles:
        empty_issns.append(issn)

    return articles

# === Loop through competitors and save per journal ===
def fetch_articles_from_competitors(df_competitors):
    issns = [i for i in df_competitors["issn"].unique() if pd.notna(i) and i.strip().lower() != "unknown issn"]
    total = len(issns)

    for idx, issn in enumerate(issns, start=1):
        print(f"\n📘 [{idx}/{total}] Fetching articles for ISSN {issn}...")
        articles = fetch_articles_for_issn(issn.strip())

        # Create competitor folder
        competitor_dir = os.path.join("data_fetching", "data", issn)
        os.makedirs(competitor_dir, exist_ok=True)

        # Save articles
        output_path = os.path.join(competitor_dir, f"articles.json")
        pd.DataFrame(articles).to_json(output_path, orient="records", lines=True)
        print(f"💾 Saved {len(articles)} articles to: {output_path}")

        # Save metadata
        metadata_path = os.path.join(competitor_dir, f"metadata.json")
        metadata = {
            "issn": issn,
            "from_year": from_year,
            "until_year": until_year,
            "retrieved_on": today.strftime("%Y-%m-%d")
        }
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=4)
        print(f"🗃️ Saved metadata to {metadata_path}")

# === Main Execution ===
if __name__ == "__main__":
    fetch_articles_from_competitors(df_competitors)

    # Save error logs
    if failed_issns:
        with open(os.path.join(base_dir, "failed_issns.txt"), "w") as f:
            for issn in failed_issns:
                f.write(issn + "\n")

    if empty_issns:
        with open(os.path.join(base_dir, "empty_issns.txt"), "w") as f:
            for issn in empty_issns:
                f.write(issn + "\n")

    print(f"\n❌ Failed ISSNs: {len(failed_issns)}")
    print(f"📭 ISSNs with no articles: {len(empty_issns)}")
