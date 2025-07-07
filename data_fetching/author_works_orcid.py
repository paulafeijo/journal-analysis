import os
import json
import asyncio
import aiohttp
import pandas as pd
from tqdm import tqdm
from aiohttp import ClientError
from more_itertools import chunked

# === Configuration ===
HEADERS = {"User-Agent": "mailto:paulafmed@gmail.com"}
ORCID_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "mailto:paulafmed@gmail.com"
}
CONCURRENT_REQUESTS = 3
OPENALEX_BASE = "https://api.openalex.org/works"
ORCID_API_BASE = "https://pub.orcid.org/v3.0"
BATCH_SIZE = 100

# === Prompt for ISSN and load metadata ===
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

# === ORCID Fetch ===
async def fetch_author_works_orcid(session, author, semaphore, max_retries=3):
    orcid_id = author.get("orcid")
    if not orcid_id:
        return None

    url = f"{ORCID_API_BASE}/{orcid_id}/works"

    for attempt in range(max_retries):
        try:
            async with semaphore:
                async with session.get(url, headers=ORCID_HEADERS, timeout=30) as response:
                    if response.status != 200:
                        raise ClientError(f"HTTP {response.status}")
                    data = await response.json()
            break
        except Exception:
            await asyncio.sleep(2 ** attempt)
            if attempt == max_retries - 1:
                return None

    works = data.get("group", [])
    if not works:
        return []

    records = []
    for work_group in works:
        for summary in work_group.get("work-summary", []):
            pub_year_data = summary.get("publication-date", {}).get("year", {})
            pub_year = int(pub_year_data.get("value", 0)) if pub_year_data else None
            if not pub_year or pub_year < from_year or pub_year > until_year:
                continue

            external_ids = summary.get("external-ids", {}).get("external-id", [])
            doi = None
            for ext in external_ids:
                if ext.get("external-id-type", "").lower() == "doi":
                    doi = ext.get("external-id-value")
                    break

            records.append({
                "doi": doi,
                "published_date": f"{pub_year}-01-01",
                "issn": None,
                "journal": summary.get("journal-title", {}).get("value"),
                "oa_status": None,
                "type": summary.get("type"),
                "author_name": author["author_name"],
                "author_position": None,
                "orcid": orcid_id,
                "affiliation": author["affiliation"],
                "country": author["country"],
                "author_id": author["author_id"]
            })

    return records

# === OpenAlex Fallback ===
async def fetch_author_works_openalex(session, author, semaphore, max_retries=3):
    author_id = author.get("author_id")
    if not author_id or "openalex.org/A" not in author_id:
        failed_authors.append(author)
        return []

    author_id_short = author_id.split("/")[-1]
    url_template = f"{OPENALEX_BASE}?filter=author.id:{author_id_short}&per-page=100&cursor={{cursor}}"

    all_works = []
    cursor = "*"

    for attempt in range(max_retries):
        try:
            async with semaphore:
                while cursor:
                    url = url_template.format(cursor=cursor)
                    async with session.get(url, headers=HEADERS, timeout=30) as response:
                        if response.status != 200:
                            raise ClientError(f"HTTP {response.status}")
                        data = await response.json()
                        all_works.extend(data.get("results", []))
                        cursor = data.get("meta", {}).get("next_cursor")
                break
        except Exception:
            await asyncio.sleep(2 ** attempt)
            if attempt == max_retries - 1:
                failed_authors.append(author)
                return []

    if not all_works:
        no_work_authors.append(author)
        return []

    records = []
    for work in all_works:
        pub_date = work.get("publication_date")
        if not pub_date:
            continue
        pub_year = int(pub_date.split("-")[0])
        if pub_year < from_year or pub_year > until_year:
            continue

        for auth in work.get("authorships", []):
            if auth.get("author", {}).get("id") == author_id:
                primary_location = work.get("primary_location") or {}
                source_info = primary_location.get("source") or {}
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

# === Main ===
async def main():
    print(f"🔍 Fetching publications ({from_year}–{until_year}) — ORCID first, OpenAlex fallback...")

    connector = aiohttp.TCPConnector(limit_per_host=CONCURRENT_REQUESTS)
    timeout = aiohttp.ClientTimeout(total=60)

    all_records = []
    fallback_authors = []

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)

        # === ORCID Fetch in Batches with tqdm ===
        orcid_authors = [a for a in authors if a.get("orcid")]
        print(f"🪪 ORCID authors: {len(orcid_authors)}")

        for chunk in tqdm(list(chunked(orcid_authors, BATCH_SIZE)), desc="🔁 ORCID batches"):
            tasks_orcid = [fetch_author_works_orcid(session, a, semaphore) for a in chunk]
            results_orcid = await asyncio.gather(*tasks_orcid)

            for a, r in zip(chunk, results_orcid):
                if r is None:
                    fallback_authors.append(a)
                elif not r:
                    no_work_authors.append(a)
                else:
                    all_records.extend(r)

        # === Add non-ORCID authors to OpenAlex fallback ===
        non_orcid_authors = [a for a in authors if not a.get("orcid")]
        fallback_authors.extend(non_orcid_authors)

        print(f"🔄 Falling back to OpenAlex for {len(fallback_authors)} authors...")

        for chunk in tqdm(list(chunked(fallback_authors, BATCH_SIZE)), desc="🔁 OpenAlex batches"):
            tasks_openalex = [fetch_author_works_openalex(session, a, semaphore) for a in chunk]
            results_openalex = await asyncio.gather(*tasks_openalex)
            for r in results_openalex:
                all_records.extend(r)

    # === Save results ===
    df_publications = pd.DataFrame(all_records)
    df_publications.to_json(output_path, orient="records", lines=True)
    print(f"\n💾 Saved author publications to {output_path}")

    pd.DataFrame(failed_authors).to_json(failed_path, orient="records", lines=True)
    print(f"❌ Failed authors: {len(failed_authors)} — saved to {failed_path}")

    pd.DataFrame(no_work_authors).to_json(no_works_path, orient="records", lines=True)
    print(f"📭 Authors with no works: {len(no_work_authors)} — saved to {no_works_path}")

    print(f"📄 Total records fetched: {len(df_publications)}")

# === Run ===
if __name__ == "__main__":
    asyncio.run(main())
