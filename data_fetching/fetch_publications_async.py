import os
import json
import asyncio
import aiohttp
import pandas as pd
from tqdm.asyncio import tqdm_asyncio
from aiohttp import ClientError
import logging

# === Logging setup ===
logging.basicConfig(filename="fetch_warnings.log", level=logging.WARNING)

# === Configuration ===
HEADERS = {"User-Agent": "mailto:paulafmed@gmail.com"}
CONCURRENT_REQUESTS = 10
BASE_URL = "https://api.openalex.org/works"

# === Load metadata ===
issn = input("Enter ISSN (e.g. 0169-4332): ").strip()
data_dir = os.path.join("data_fetching", "data", issn)
os.makedirs(data_dir, exist_ok=True)

with open(os.path.join(data_dir, "metadata.json"), "r") as f:
    metadata = json.load(f)

from_year = metadata["from_year"]
until_year = metadata["until_year"]

input_path = os.path.join(data_dir, "authors.json")
output_path = os.path.join(data_dir, "author_publications.json")
failed_path = os.path.join(data_dir, "authors_failed.json")
no_works_path = os.path.join(data_dir, "authors_no_works.json")

df_authors = pd.read_json(input_path, lines=True)
authors = (
    df_authors.drop_duplicates(subset=["author_id"])
              .dropna(subset=["author_id"])
              [["author_id", "author_name", "orcid", "affiliation", "country"]]
              .to_dict(orient="records")
)

# === Globals ===
failed_authors = []
no_work_authors = []

# === Async Fetch Function ===
async def fetch_author_works(session, author, semaphore, max_retries=3):
    author_id = author.get("author_id")
    if not author_id or "openalex.org/A" not in author_id:
        failed_authors.append(author)
        return []

    author_id_short = author_id.split("/")[-1]
    url_template = f"{BASE_URL}?filter=author.id:{author_id_short}&per-page=100&cursor={{cursor}}"

    all_works = []
    cursor = "*"

    for attempt in range(max_retries):
        try:
            async with semaphore:
                while cursor:
                    url = url_template.format(cursor=cursor)
                    async with session.get(url, timeout=30) as response:
                        if response.status != 200:
                            raise ClientError(f"HTTP {response.status}")
                        data = await response.json()
                        all_works.extend(data.get("results", []))
                        cursor = data.get("meta", {}).get("next_cursor")

                break  # success, exit retry loop

        except Exception as e:
            await asyncio.sleep(2 ** attempt)  # backoff
            if attempt == max_retries - 1:
                failed_authors.append(author)
                return []

    if not all_works:
        no_work_authors.append(author)
        return []

    records = []
    for work in all_works:
        try:
            pub_date = work.get("publication_date")
            if not pub_date:
                continue

            pub_year = int(pub_date.split("-")[0])
            if pub_year < from_year or pub_year > until_year:
                continue

            for auth in work.get("authorships", []):
                if auth.get("author", {}).get("id") == author["author_id"]:
                    primary_location = work.get("primary_location") or {}
                    source_info = primary_location.get("source", {}) or {}

                    issns = source_info.get("issn", [])
                    issn_value = ", ".join(issns) if isinstance(issns, list) else issns

                    records.append({
                        "doi": work.get("doi"),
                        "published_date": pub_date,
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

        except Exception as e:
            logging.warning(f"Skipped malformed work for author {author['author_id']}: {e}")
            continue

    return records

# === Main async function ===
async def main():
    print(f"🔍 Fetching publications for each author ({from_year}–{until_year})...")

    connector = aiohttp.TCPConnector(limit_per_host=CONCURRENT_REQUESTS)
    timeout = aiohttp.ClientTimeout(total=None)

    async with aiohttp.ClientSession(headers=HEADERS, connector=connector, timeout=timeout) as session:
        semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
        tasks = [fetch_author_works(session, author, semaphore) for author in authors]
        all_results = await tqdm_asyncio.gather(*tasks)

    # Flatten list of results
    all_records = [record for sublist in all_results for record in sublist]

    df_publications = pd.DataFrame(all_records)
    df_publications.to_json(output_path, orient="records", lines=True)
    print(f"\n💾 Saved author publications to {output_path}")

    pd.DataFrame(failed_authors).to_json(failed_path, orient="records", lines=True)
    print(f"❌ Failed authors: {len(failed_authors)} — saved to {failed_path}")

    pd.DataFrame(no_work_authors).to_json(no_works_path, orient="records", lines=True)
    print(f"📭 Authors with no works: {len(no_work_authors)} — saved to {no_works_path}")

    print(f"📄 Total records fetched: {len(df_publications)}")

# === Run it ===
if __name__ == "__main__":
    asyncio.run(main())
