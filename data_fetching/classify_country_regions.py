# data_fetching/classify_country_regions.py

import os
import pandas as pd

# === File Paths ===
base_dir = os.path.join("data_fetching", "data")
input_path = os.path.join(base_dir, "author_publications_0169-4332_2020_2024.json")
output_path = input_path

# === Region Mapping ===
REGION_MAP = {
    "China (CN)": ["CN"],
    "Korea & India": ["KR", "IN"],
    "High-Income Research Countries": [
        "US", "JP", "DE", "FR", "GB", "IT", "ES", "CA", "AU", "CH", "NL", "BE", "SE", "SG",
        "AT", "FI", "DK", "IE", "NO", "IL"
    ],
    "Emerging/Transition Countries": [
        "RU", "PL", "CZ", "BR", "MX", "IR", "TR", "RO", "SK", "VN", "TH", "AR", "PK", "HU",
        "PT", "SA", "QA", "AE", "MY", "HK", "CL", "EG", "ZA", "GR", "BG", "ID", "UA", "KZ",
        "RS", "SI", "CO", "DZ", "PE", "VE", "UY", "EE", "PH", "JO", "NZ", "LU", "HR", "LV",
        "LT", "MO", "OM", "IQ", "IS", "BD", "ET", "TN", "LK", "LB", "KW", "CM", "MT", "FJ", "PR"
    ],
    "Other": []  # Fallback
}

def classify_region(country_code):
    for region, countries in REGION_MAP.items():
        if country_code in countries:
            return region
    return "Other"

# === Load Data ===
df = pd.read_json(input_path, lines=True)

# === Classify Regions ===
df['region'] = df['country'].apply(classify_region)

# === Save Output ===
df.to_json(output_path, orient="records", lines=True)

print(f"✅ Region classification complete. File saved to: {output_path}")
print(df['region'].value_counts())
