import os
import json
import requests
import pandas as pd
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

# === CONFIGURATION ===
MAX_WORKERS = 10
session = requests.Session()

# === Input ===
base_issn = sys.stdin.read().strip()

# === File paths ===
base_dir = os.path.join("data_fetching", "data")
issn_dir = os.path.join(base_dir, base_issn)
input_path = os.path.join(issn_dir, "articles.json")

citations_output_path = os.path.join(issn_dir, "citations.json")
references_output_path = os.path.join(issn_dir, "references.json")

# === Load articles ===
if not os.path.exists(input_path):
    print(f"❌ File not found: {input_path}")
    exit(1)

df_articles = pd.read_json(input_path, lines=True)
dois = df_articles['doi'].dropna().unique()
print(f"🔢 {len(dois)} DOIs to process\n")

# === FUNCTIONS ===
def fetch_links(doi, mode='citations'):
    assert mode in ['citations', 'references']
    url = f"https://opencitations.net/index/api/v2/{mode}/doi:{doi}"
    try:
        response = session.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            key = 'citing' if mode == 'citations' else 'cited'
            return [{
                'source_doi': doi,
                'related_doi': item.get(key)
            } for item in data if item.get(key)]
    except requests.RequestException:
        return []
    return []

def batch_fetch_links(dois, mode='citations'):
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_links, doi, mode): doi for doi in dois}
        for future in tqdm(as_completed(futures), total=len(futures), desc=f"📦 Fetching {mode}", unit="doi"):
            res = future.result()
            if res:
                results.extend(res)
    df = pd.DataFrame(results)
    df['related_doi'] = df['related_doi'].str.extract(r'doi:([^ ]+)', expand=False).fillna(df['related_doi'])
    return df

# === Run Fetching ===
print("\n🔍 Fetching citations...")
df_citations = batch_fetch_links(dois, mode='citations')
print(f"✅ Fetched {len(df_citations)} citation links")

print("\n🔍 Fetching references...")
df_references = batch_fetch_links(dois, mode='references')
print(f"✅ Fetched {len(df_references)} reference links")

# === Save to disk ===
df_citations.to_json(citations_output_path, orient="records", indent=2)
print(f"\n💾 Saved citations to {citations_output_path}")

df_references.to_json(references_output_path, orient="records", indent=2)
print(f"💾 Saved references to {references_output_path}")
