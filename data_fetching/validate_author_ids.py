import os
import json
import pandas as pd

# === Input ===
issn = input("Enter ISSN (e.g. 2673-6187): ").strip()
data_dir = os.path.join("data_fetching", "data", issn)

input_path = os.path.join(data_dir, "authors.json")
valid_path = os.path.join(data_dir, "authors_valid.json")
invalid_path = os.path.join(data_dir, "authors_invalid.json")

# === Load and validate ===
df = pd.read_json(input_path, lines=True)

# Ensure column exists
if "author_id" not in df.columns:
    raise ValueError("Missing 'author_id' column in input.")

# Define valid OpenAlex author ID format
def is_valid_author_id(author_id):
    return isinstance(author_id, str) and author_id.startswith("https://openalex.org/A")

df_valid = df[df["author_id"].apply(is_valid_author_id)].copy()
df_invalid = df[~df["author_id"].apply(is_valid_author_id)].copy()

# === Save results ===
df_valid.to_json(valid_path, orient="records", lines=True)
df_invalid.to_json(invalid_path, orient="records", lines=True)

# === Report ===
print(f"✅ Valid authors saved to: {valid_path} ({len(df_valid)})")
print(f"❌ Invalid authors saved to: {invalid_path} ({len(df_invalid)})")
print(f"📊 Original count: {len(df)}")
