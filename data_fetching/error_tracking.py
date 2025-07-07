import os
import pandas as pd
import json

base_issn = input("Enter base ISSN (e.g. 0169-4332): ").strip()
data_dir = os.path.join("data_fetching", "data", base_issn)

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
failed_issns_path = os.path.join(data_dir, "failed_issns.txt")
empty_issns_path = os.path.join(data_dir, "empty_issns.txt")

failed_issns = open(failed_issns_path).read().splitlines() if os.path.exists(failed_issns_path) else []
empty_issns = open(empty_issns_path).read().splitlines() if os.path.exists(empty_issns_path) else []

total_competitors = 10  # assuming you always fetch top 10 competitors
num_issues = len(set(failed_issns + empty_issns))
error_percent_comp_articles = (num_issues / total_competitors) * 100 if total_competitors else 0

# === fetch_competitor_authors.py ===
df_competitors = pd.read_json(os.path.join(data_dir, "top_competitors.json"))
top_competitors = df_competitors.sort_values(by="total_score", ascending=False).head(10)
competitor_issns = top_competitors['issn'].dropna().unique()

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

    journal_name = df_competitors[df_competitors['issn'] == issn]['journal'].values[0] if issn in df_competitors['issn'].values else "Unknown"

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
        "total": total_competitors,
        "failed": num_issues,
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
