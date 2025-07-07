# === Load authors and check ORCID coverage ===
import pandas as pd
import os

issn = input("Enter ISSN (e.g. 0169-4332): ").strip()

data_dir = os.path.join("data_fetching", "data", issn)
input_path = os.path.join(data_dir, "authors.json")

df_authors = pd.read_json(input_path, lines=True)

# Count total unique authors and those with ORCID
total_authors = df_authors["author_id"].nunique()
num_with_orcid = df_authors["orcid"].dropna().nunique()

print(f"🧾 Total authors: {total_authors}")
print(f"🪪 Authors with ORCID: {num_with_orcid} ({num_with_orcid / total_authors:.1%})")
