import requests
import pandas as pd
import time
from datetime import datetime
from tqdm import tqdm

# Configuration
issn = input("Enter ISSN (e.g. 0169-4332): ").strip()
rows = 1000
api_url = "https://api.crossref.org/works"
email = "paulafmed@gmail.com"
today = datetime.today()
last_year = today.year - 1
from_year = last_year - 4

from_date = f"{from_year}-01-01"
until_date = f"{last_year}-12-31"

def fetch_articles():
    cursor = "*"
    articles = []
    total_results = None
    page_count = 0

    print(f"🔍 Fetching DOIs for ISSN {issn} from {from_date} to {until_date}...\n")

    with tqdm(desc="📦 Articles downloaded", unit="records", dynamic_ncols=True) as pbar:
        while True:
            params = {
                "filter": f"issn:{issn},from-pub-date:{from_date},until-pub-date:{until_date}",
                "rows": rows,
                "cursor": cursor,
                "mailto": email
            }

            try:
                response = requests.get(api_url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
            except requests.exceptions.RequestException as e:
                print(f"\n❌ API request failed: {e}")
                time.sleep(5)
                continue

            message = data.get("message", {})
            items = message.get("items", [])
            next_cursor = message.get("next-cursor")

            if total_results is None:
                total_results = message.get("total-results", 0)
                print(f"🔢 Estimated total results: {total_results}\n")

            if not items:
                print("✅ No more items to fetch.")
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
                print("✅ No next cursor found, ending pagination.")
                break

            cursor = next_cursor
            time.sleep(1)

    print(f"\n📄 Fetched {len(articles)} articles in {page_count} pages.")
    return articles

if __name__ == "__main__":
    articles_data = fetch_articles()
    df_articles = pd.DataFrame(articles_data)
    df_articles.info()
import os

# Define output directory and file path
output_dir = os.path.join("data_fetching", "data")
os.makedirs(output_dir, exist_ok=True)

output_path = os.path.join(output_dir, f"articles_{issn}_{from_year}_{last_year}.json")

# Save DataFrame to JSON
df_articles.to_json(output_path, orient="records", lines=True)

print(f"\n💾 Saved data to {output_path}")

