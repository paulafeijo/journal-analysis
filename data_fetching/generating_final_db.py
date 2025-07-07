
import os
import pandas as pd

# === Input ===
issn = input("Enter base ISSN (e.g. 0169-4332): ").strip()
issn_dir = os.path.join("data_fetching", "data", issn)

# === Load required files ===
authors_path = os.path.join(issn_dir, "authors.json")
competitors_path = os.path.join(issn_dir, "competitors_citations.json")
citations_path = os.path.join(issn_dir, "citations.jsonl")
references_path = os.path.join(issn_dir, "references.jsonl")

df_authors = pd.read_json(authors_path, lines=True)
df_competitors = pd.read_json(competitors_path)
df_competitors = df_competitors.sort_values(by="total_score", ascending=False).head(10)
df_citations = pd.read_json(citations_path, lines=True)
df_references = pd.read_json(references_path, lines=True)

# === Load authors.json for each top competitor ISSN ===
df_competitors = df_competitors.sort_values(by="total_score", ascending=False).head(10)
competitor_issns = df_competitors['issn'].dropna().unique()

author_frames = []
print(f"\n🔍 Loading authors.json for top {len(competitor_issns)} competitor ISSNs...")

for comp_issn in competitor_issns:
    comp_dir = os.path.join("data_fetching", "data", comp_issn)
    comp_authors_path = os.path.join(comp_dir, "authors.json")

    if os.path.exists(comp_authors_path):
        df = pd.read_json(comp_authors_path, lines=True)
        df['source_issn'] = comp_issn  # Optional: tag source journal
        author_frames.append(df)
        print(f"✅ Loaded {len(df)} authors from {comp_issn}")
    else:
        print(f"⚠️ Missing: {comp_authors_path}")

# Combine competitor authors + base journal authors into one final frame
author_frames.append(df_authors.assign(source_issn=issn))  # base journal too

df_final = pd.concat(author_frames, ignore_index=True)
print(f"\n📚 Combined author records (base + competitors): {len(df_final)}")

print("📄 df_final columns:", df_final.columns.tolist())

# === Count how many times each article was cited (by competitors) ===
doi_cite_counts = df_citations['related_doi'].value_counts()
df_final['cites'] = df_final['doi'].map(doi_cite_counts).fillna(0).astype(int)

# === Count how many references each article made to competitors ===
doi_ref_counts = df_references['related_doi'].value_counts()
df_final['referenced'] = df_final['doi'].map(doi_ref_counts).fillna(0).astype(int)

print("\n✅ Added 'cites' and 'referenced' columns to df_final")

# === Add journal name to each article using plain ISSN match ===

# Track original row index
df_final = df_final.reset_index().rename(columns={'index': 'orig_index'})

# Clean up just in case
df_final['issn'] = df_final['issn'].astype(str).str.strip()
df_competitors['issn'] = df_competitors['issn'].astype(str).str.strip()

# Merge journal names from competitors
merged = df_final.merge(
    df_competitors[['issn', 'journal']],
    on='issn',
    how='left'
)

# No explode, so no need to re-group — just assign
df_final = merged

print("\n✅ Added journal names to df_final (no explode needed)")

# === Add 'journal_author' flag: has this author published in the base journal? ===

# Step 1: Identify author_ids who published in the base journal
authors_in_base_journal = df_final[df_final['issn'] == issn]['author_id'].unique()

# Step 2: Mark each author accordingly
df_final['journal_author'] = df_final['author_id'].isin(authors_in_base_journal).map({True: 'yes', False: 'no'})

print("\n✅ Added 'journal_author' column")
df_final['journal_author'].value_counts()

# === Save final database ===

output_path = os.path.join(issn_dir, f"final_database_{issn}.json")
df_final.to_json(output_path, orient="records", lines=True)
print(f"\n💾 Final database saved to: {output_path}")



