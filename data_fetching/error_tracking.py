import os
import pandas as pd
import json

base_issn = input("Enter base ISSN (e.g. 0169-4332): ").strip()
data_dir = "data"

report = {}

# === fetch_articles.py ===
base_articles_path = os.path.join(data_dir, base_issn, "articles.json")
df_articles = pd.read_json(base_articles_path, lines=True)
num_articles_fetched = len(df_articles)

report["fetch_articles"] = {"articles_fetched": num_articles_fetched}

# === fetch_authors.py ===
failed_dois_path = os.path.join(data_dir, base_issn, "failed_dois.txt")
if os.path.exists(failed_dois_path):
    with open(failed_dois_path, "r") as f:
        failed_dois = f.read().splitlines()
else:
    failed_dois = []

num_failed_authors = len(failed_dois)
num_total_dois = len(df_articles)
error_percent_authors = (num_failed_authors / num_total_dois) * 100 if num_total_dois else 0

report["fetch_authors"] = {
    "total_dois": num_total_dois,
    "failed_dois": num_failed_authors,
    "error_percent": round(error_percent_authors, 2)
}

# === fetch_competitor_articles.py ===
failed_issns_path = os.path.join(data_dir, base_issn, "failed_issns.txt")
empty_issns_path = os.path.join(data_dir, base_issn, "empty_issns.txt")

failed_issns = open(failed_issns_path).read().splitlines() if os.path.exists(failed_issns_path) else []
empty_issns = open(empty_issns_path).read().splitlines() if os.path.exists(empty_issns_path) else []

total_competitors = 10  # assuming you always fetch top 10 competitors
num_issues = len(set(failed_issns + empty_issns))
error_percent_comp_articles = (num_issues / total_competitors) * 100

report["fetch_competitor_articles"] = {
    "total_competitor_issns": total_competitors,
    "failed_or_empty_issns": num_issues,
    "error_percent": round(error_percent_comp_articles, 2)
}

# === fetch_competitor_authors.py ===
df_competitors = pd.read_json(os.path.join(data_dir, base_issn, "competitors_citations.json"))
top_competitors = df_competitors.sort_values(by="total_score", ascending=False).head(10)
competitor_issns = top_competitors['issn'].dropna().unique()

comp_authors_report = {}
for issn in competitor_issns:
    comp_dir = os.path.join(data_dir, issn)
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
    error_percent = (num_failed_comp_authors / total_comp_dois) * 100 if total_comp_dois else 0

    comp_authors_report[issn] = {
        "total_dois": total_comp_dois,
        "failed_dois": num_failed_comp_authors,
        "error_percent": round(error_percent, 2)
    }

report["fetch_competitor_authors"] = comp_authors_report

# === Save report to JSON ===
report_path = os.path.join(data_dir, base_issn, f"error_report.json")
with open(report_path, "w") as f:
    json.dump(report, f, indent=4)

print(f"\n📄 Error report saved to: {report_path}")
