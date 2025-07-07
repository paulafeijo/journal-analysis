import pandas as pd
import os
import requests
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIG ---
MAX_WORKERS = 10
OPENALEX_API = "https://api.openalex.org/works/https://doi.org/"
CROSSREF_API = "https://api.crossref.org/works/"
issn = input("Enter ISSN (e.g. 0169-4332): ").strip()

# --- File Paths ---
issn_dir = os.path.join("data_fetching", "data", issn)
citations_path = os.path.join(issn_dir, "citations.jsonl")
references_path = os.path.join(issn_dir, "references.jsonl")

# --- Load citation and reference links ---
df_citations = pd.read_json(citations_path, lines=True)
df_references = pd.read_json(references_path, lines=True)

# --- Collect unique DOIs to resolve ---
unique_dois = pd.concat([df_citations['related_doi'], df_references['related_doi']]).dropna().unique()

# --- Resolve DOIs to journal names ---
CROSSREF_API = "https://api.crossref.org/works/"

def get_journal_for_doi(doi):
    # Try Crossref first
    try:
        r = requests.get(CROSSREF_API + doi, timeout=8)
        if r.status_code == 200:
            msg = r.json().get("message", {})
            titles = msg.get("container-title", [])
            issns = msg.get("ISSN", [])
            if titles:
                return {
                    'doi': doi,
                    'journal': titles[0],
                    'issn': issns[0] if issns else None
                }
    except requests.RequestException:
        pass

    # Fallback to OpenAlex
    try:
        r = requests.get(OPENALEX_API + doi, timeout=10)
        if r.status_code == 200:
            data = r.json()
            venue = data.get('host_venue', {})
            journal = venue.get('display_name')
            issn = venue.get('issn_l') or None
            if journal:
                return {
                    'doi': doi,
                    'journal': journal,
                    'issn': issn
                }
    except requests.RequestException:
        pass

    return {'doi': doi, 'journal': None, 'issn': None}


journal_map = []
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = {executor.submit(get_journal_for_doi, doi): doi for doi in unique_dois}
    for future in tqdm(as_completed(futures), total=len(futures), desc="📚 Resolving DOIs to journals"):
        result = future.result()
        if result:
            journal_map.append(result)

df_journal_map = pd.DataFrame(journal_map).dropna()

# --- Merge journal names into references and citations ---
df_citations = df_citations.merge(df_journal_map, left_on='related_doi', right_on='doi', how='left')
df_references = df_references.merge(df_journal_map, left_on='related_doi', right_on='doi', how='left')

# --- Count frequency ---
cit_count = df_citations.groupby(['journal', 'issn']).size().reset_index(name='citations')
ref_count = df_references.groupby(['journal', 'issn']).size().reset_index(name='references')

# --- Merge and score ---
df_combined = pd.merge(ref_count, cit_count, on=['journal', 'issn'], how='outer').fillna(0)
df_combined['total_score'] = df_combined['citations'] + df_combined['references']
df_combined = df_combined.sort_values(by='total_score', ascending=False)

# --- Top 10 Competitor Journals (excluding base journal) ---
df_filtered = df_combined[df_combined['issn'] != issn]
top_10 = df_filtered.head(10)

print("\n🏆 Top 10 Competitor Journals (excluding base journal):\n")
print(top_10.to_string(index=False))

# --- Save full competitor ranking to file ---
output_path = os.path.join(issn_dir, "competitors_citations.json")
df_combined.to_json(output_path, orient="records", indent=2)
print(f"\n💾 Saved full ranked competitor journal list to {output_path}")

# --- Save top 10 to file ---
top_path = os.path.join(issn_dir, "top_competitors.json")
top_10.to_json(top_path, orient="records", indent=2)
print(f"💾 Saved top 10 competitors to {top_path}")