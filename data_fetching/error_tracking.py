import os
import pandas as pd
import json
import sys


base_issn = sys.stdin.read().strip()
data_dir = os.path.join("data_fetching", "data", base_issn)
final_database_path = os.path.join(data_dir, "final_database.json")
try:
    df_final = pd.read_json(final_database_path, lines=True)
    journals_df = df_final[['issn', 'journal']].drop_duplicates()
except Exception as e:
    print(f"Warning: Could not load journals from final_database.json: {e}")
    journals_df = pd.DataFrame()

df_competitors = pd.read_json(os.path.join(data_dir, "top_competitors.json"))
top_competitors = df_competitors.sort_values(by="total_score", ascending=False).head(10)
competitor_issns = top_competitors['issn'].dropna().unique()

# === fetch_articles.py ===
base_articles_path = os.path.join(data_dir, "articles.json")
df_articles = pd.read_json(base_articles_path, lines=True)
num_articles_fetched = len(df_articles)

# === fetch_authors.py ===
failed_dois_path = os.path.join(data_dir, "failed_dois.txt")
if os.path.exists(failed_dois_path):
    with open(failed_dois_path, "r") as f:
        failed_dois = f.read().splitlines()
else:
    failed_dois = []

num_failed_authors = len(failed_dois)
num_total_dois = len(df_articles)
error_percent_authors = (num_failed_authors / num_total_dois) * 100 if num_total_dois else 0

# === fetch_competitor_articles.py ===
# Compute how many competitor articles were successfully fetched in total
comp_articles_total = 0
comp_articles_missing = 0

for issn in competitor_issns:
    comp_dir = os.path.join("data_fetching", "data", issn)
    articles_path = os.path.join(comp_dir, "articles.json")
    
    if os.path.exists(articles_path):
        df = pd.read_json(articles_path, lines=True)
        comp_articles_total += len(df)
    else:
        comp_articles_missing += 1  # or log missing ISSN if needed

error_percent_comp_articles = 0
if comp_articles_total + comp_articles_missing > 0:
    error_percent_comp_articles = (comp_articles_missing / (comp_articles_total + comp_articles_missing)) * 100


# === fetch_competitor_authors.py ===
def get_journal_name_from_journals_df(issn, df_journals, df_top_competitors):
    if not df_journals.empty and 'issn' in df_journals.columns and 'journal' in df_journals.columns:
        match = df_journals[df_journals['issn'] == issn]
        if not match.empty:
            journal = match.iloc[0]['journal']
            return journal if pd.notna(journal) else "Unknown"

    
    # fallback: check top_competitors.json
    if 'issn' in df_top_competitors.columns and 'journal' in df_top_competitors.columns:
        match = df_top_competitors[df_top_competitors['issn'] == issn]
        if not match.empty:
            return match.iloc[0]['journal']

    return "Unknown"

comp_author_rows = []
for issn in competitor_issns:
    comp_dir = os.path.join("data_fetching", "data", issn)
    articles_path = os.path.join(comp_dir, "articles.json")
    failed_authors_path = os.path.join(comp_dir, "failed_dois.json")

    if os.path.exists(articles_path):
        total_comp_dois = len(pd.read_json(articles_path, lines=True))
    else:
        total_comp_dois = 0

    if os.path.exists(failed_authors_path):
        with open(failed_authors_path) as f:
            failed_comp_dois = json.load(f)
    else:
        failed_comp_dois = []

    num_failed_comp_authors = len(failed_comp_dois)
    error_percent = (num_failed_comp_authors / total_comp_dois) * 100 if total_comp_dois else 100

    journal_name = get_journal_name_from_journals_df(issn, journals_df, df_competitors)
    
    comp_author_rows.append({
        "object": journal_name,
        "issn": issn,
        "total": total_comp_dois,
        "failed": num_failed_comp_authors,
        "error_percent": round(error_percent, 2)
    })

# === Compute competitor average error ===
if comp_author_rows:
    total_sum = sum(row["total"] for row in comp_author_rows)
    failed_sum = sum(row["failed"] for row in comp_author_rows)
    avg_error = (failed_sum / total_sum) * 100 if total_sum else 0
else:
    avg_error = 0

# === Assemble final table ===
rows = [
    {
        "object": "base issn",
        "issn": base_issn, 
        "total": num_total_dois,
        "failed": num_failed_authors,
        "error_percent": round(error_percent_authors, 2)
    },
    {
        "object": "competitor articles",
        "issn": "all below", 
        "total": comp_articles_total + comp_articles_missing,
        "failed": comp_articles_missing,
        "error_percent": round(error_percent_comp_articles, 2)
    },
    {
        "object": "competitor average",
        "issn": "all below", 
        "total": total_sum,
        "failed": failed_sum,
        "error_percent": round(avg_error, 2)
    }
] + comp_author_rows

df_report = pd.DataFrame(rows)

# === Save to JSON and print ===
report_path = os.path.join(data_dir, f"error_report.json")
df_report.to_json(report_path, orient="records", indent=4)
print(f"\n📄 Error report saved to: {report_path}\n")
print(df_report.to_string(index=False))
