import os
import pandas as pd

# === File paths and load data ===
issn = input("Enter ISSN (e.g. 0169-4332): ").strip()
data_dir = os.path.join("data_fetching", "data", issn)
os.makedirs(data_dir, exist_ok=True)

input_path = os.path.join(data_dir, f"author_publications.json")
output_path = os.path.join(data_dir, f"competitors.json")

# === Load data ===
df = pd.read_json(input_path, lines=True)

# === Clean and prepare ===
df["journal"] = df["journal"].fillna("Unknown Journal")
df["issn"] = df["issn"].fillna("Unknown ISSN")

# === Split ISSNs first ===
df["issn"] = df["issn"].str.split(', ')
df = df.explode("issn").reset_index(drop=True)
df["issn"] = df["issn"].str.strip()

# === Remove the input ISSN ===
df = df[df["issn"] != issn]

# === Count publications per journal+issn ===
df_competitors = (
    df.groupby(["journal", "issn"])
      .size()
      .reset_index(name="publication_count")
      .sort_values("publication_count", ascending=False)
      .head(10)
)

# === Save result ===
df_competitors.to_json(output_path, orient="records", lines=True)

# === Print result ===
print("\n🏆 Top 10 Competitor Journals (Exploded ISSNs):")
print(df_competitors.to_string(index=False))
print(f"\n💾 Saved to: {output_path}")