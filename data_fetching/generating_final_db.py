import os
import json
import pandas as pd
import requests
import sys
from tqdm import tqdm
import time

# === Input ===
base_issn = sys.stdin.read().strip()
issn_dir = os.path.join("data_fetching", "data", base_issn)

# === Load required files ===
authors_path = os.path.join(issn_dir, "authors.json")
competitors_path = os.path.join(issn_dir, "top_competitors.json")
citations_path = os.path.join(issn_dir, "citations.json")
references_path = os.path.join(issn_dir, "references.json")

df_authors = pd.read_json(authors_path, lines=True)
df_top_competitors = pd.read_json(competitors_path)
df_top_competitors = df_top_competitors.sort_values(by="total_score", ascending=False).head(10)
df_citations = pd.read_json(citations_path)
df_references = pd.read_json(references_path)

# === Load authors.json for each top competitor ISSN into df_competitors ===
competitor_issns = df_top_competitors['issn'].dropna().unique()
competitor_frames = []

print(f"\n🔍 Loading authors.json for top {len(competitor_issns)} competitor ISSNs...")

for comp_issn in competitor_issns:
    comp_dir = os.path.join("data_fetching", "data", comp_issn)
    comp_authors_path = os.path.join(comp_dir, "authors.json")

    if os.path.exists(comp_authors_path):
        df = pd.read_json(comp_authors_path, lines=True)
        df['source_issn'] = comp_issn
        competitor_frames.append(df)
        print(f"✅ Loaded {len(df)} authors from {comp_issn}")
    else:
        print(f"⚠️ Missing: {comp_authors_path}")

# === Debug: check journal field completeness
for i, df in enumerate(competitor_frames):
    if 'journal' in df.columns:
        nulls = df['journal'].isnull().sum()
        print(f"📊 Frame {i}: {nulls} null journal values (out of {len(df)})")
    else:
        print(f"📊 Frame {i}: no 'journal' column")


# Combine competitor articles
df_competitors = pd.concat(competitor_frames, ignore_index=True)

# Combine base + competitors into df_final
df_final = pd.concat([df_competitors, df_authors], ignore_index=True)
print(f"\n📚 Combined author records (base + competitors): {len(df_final)}")

# === Region classification ===
REGION_MAP = {
    "Europe (OpenAPC strong)": [
        "DE","GB","FR","IT","ES","NL","SE","FI","NO","DK","AT","BE","CH","IE",
        "PL","CZ","PT","GR","HU","SI","SK","EE","LV","LT","RO","BG","HR","LU","IS"
    ],
    "US & Canada": ["US","CA"],
    "China": ["CN"],  # Optionally add "HK","MO"
    "Latin America": [
        "BR","MX","AR","CL","CO","PE","UY","VE","CR","EC","PA","BO","PY",
        "SV","GT","HN","NI","DO","PR"
    ],
    "Asia-Pacific (ex-China)": ["JP","KR","IN","SG","AU","NZ","TW","TH","VN","MY","ID","PH"],
    "Middle East & Africa": [
        "IL","SA","AE","QA","KW","OM","EG","ZA","MA","TN","KE","NG","GH","ET"
    ],
    "Other": []
}


def classify_region(country_code):
    for region, countries in REGION_MAP.items():
        if country_code in countries:
            return region
    return "Other"

# Add region column
df_final['region'] = df_final['country'].fillna("NA").apply(classify_region)
print("🌍 Added 'region' column based on country codes")

# === Add citation and reference counts ===
doi_cite_counts = df_citations['related_doi'].value_counts()
df_final['cites'] = df_final['doi'].map(doi_cite_counts).fillna(0).astype(int)

doi_ref_counts = df_references['related_doi'].value_counts()
df_final['referenced'] = df_final['doi'].map(doi_ref_counts).fillna(0).astype(int)

print("\n✅ Added 'cites' and 'referenced' columns to df_final")

# === Add 'journal_author' flag ===

df_final['issn'] = df_final['issn'].astype(str).str.strip().str.split(',')
df_final = df_final.explode('issn')
df_final['issn'] = df_final['issn'].str.strip()  # Keep ISSNs as they are, with hyphens

authors_in_base_journal = df_final[df_final['issn'] == base_issn]['author_id'].unique()
df_final['journal_author'] = df_final['author_id'].isin(authors_in_base_journal).map({True: 'yes', False: 'no'})


print("\n✅ Added 'journal_author' column")
print(df_final['journal_author'].value_counts())


# === Resolve journal names for all unique ISSNs
unique_issns = df_final['issn'].dropna().unique()

CROSSREF_JOURNAL_API = "https://api.crossref.org/journals/"

def resolve_journal_name_from_issn(issn):
    try:
        response = requests.get(CROSSREF_JOURNAL_API + issn, timeout=8)
        if response.status_code == 200:
            msg = response.json().get("message", {})
            return msg.get("title")
        else:
            print(f"⚠️ ISSN {issn} returned status {response.status_code}")
    except requests.RequestException as e:
        print(f"❌ Request error for ISSN {issn}: {e}")
    return None

issn_to_journal = {}
print("\n🔍 Resolving journal names from ISSNs...")
for issn in tqdm(unique_issns):
    journal_name = resolve_journal_name_from_issn(issn)
    if journal_name:
        issn_to_journal[issn] = journal_name
    time.sleep(0.1)

df_final['journal'] = df_final['issn'].map(issn_to_journal)
df_final['journal'] = df_final['journal'].where(pd.notnull(df_final['journal']), None)

# === Final check: journal field
missing_journal_rows = df_final['journal'].isnull().sum()
print(f"\n❌ Final null 'journal' entries: {missing_journal_rows}")

# === Save final database ===
output_path = os.path.join(issn_dir, f"final_database.json")
df_final.to_json(output_path, orient="records", lines=True)
print(f"\n💾 Final database saved to: {output_path}")
