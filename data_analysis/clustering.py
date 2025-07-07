import pandas as pd
import json
from sklearn.preprocessing import MinMaxScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
import os

# === Load final database ===
base_issn = input("Enter base ISSN (e.g. 0169-4332): ").strip()
base_dir = os.path.join("data_fetching", "data", base_issn)

final_db_path = os.path.join(base_dir, "final_database.json")
df_final = pd.read_json(final_db_path, lines=True)



# === Building the clustering dataframe ===


# Group by affiliation and country, count unique DOIs
df_institutions = df_final.groupby(['affiliation', 'country']).agg(
    publications=('doi', 'nunique')
).reset_index()

# Rename for clarity
df_institutions.rename(columns={'affiliation': 'institution'}, inplace=True)

# Categorizando os países em regiões de interesse

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

# Function to classify country into region
def classify_region(country_code):
    for region, countries in REGION_MAP.items():
        if country_code in countries:
            return region
    return "Other"

# Apply classification to df_authors
df_institutions['region'] = df_institutions['country'].apply(classify_region)

# Percentage of OA publications

df_oa = df_final[~df_final['oa_status'].isin(['hybrid', 'closed'])]

df_oa_counts = df_oa.groupby(['affiliation', 'country']).agg(
    oa_publications=('doi', 'nunique')
).reset_index()

df_institutions = df_institutions.merge(
    df_oa_counts,
    how='left',
    left_on=['institution', 'country'],
    right_on=['affiliation', 'country']
)

df_institutions['oa_publications'] = df_institutions['oa_publications'].fillna(0)

df_institutions['oa_percentage'] = (
    df_institutions['oa_publications'] / df_institutions['publications']
).round(3)

df_institutions.drop(columns=['affiliation'], inplace=True)
df_institutions.drop(columns=['oa_publications'], inplace=True)

# Percentage of contributions with authors as first and last

df_total = df_final.groupby(['affiliation', 'country']).size().reset_index(name='total_authorships')

df_fl = df_final[df_final['author_position'].isin(['first', 'last'])]
df_fl_counts = df_fl.groupby(['affiliation', 'country']).size().reset_index(name='leadership_authorships')

df_leadership = pd.merge(
    df_total,
    df_fl_counts,
    on=['affiliation', 'country'],
    how='left'
)

df_leadership['leadership_authorships'] = df_leadership['leadership_authorships'].fillna(0)

df_leadership['leadership_percentage'] = (
    df_leadership['leadership_authorships'] / df_leadership['total_authorships']
).round(3)

df_institutions = df_institutions.merge(
    df_leadership[['affiliation', 'country', 'leadership_percentage']],
    how='left',
    left_on=['institution', 'country'],
    right_on=['affiliation', 'country']
)

df_institutions.drop(columns=['affiliation'], inplace=True)

# Number of publications in the target journal

df_journal = df_final[df_final['issn'] == base_issn]

df_journal_counts = df_journal.groupby(['affiliation', 'country']).agg(
    journal_publications=('doi', 'nunique')
).reset_index()

df_institutions = df_institutions.merge(
    df_journal_counts,
    how='left',
    left_on=['institution', 'country'],
    right_on=['affiliation', 'country']
)

df_institutions['journal_publications'] = df_institutions['journal_publications'].fillna(0).astype(int)
df_institutions.drop(columns=['affiliation'], inplace=True)



# === Building the clustering dataframe ===


# Step 1: Define features
features = ['publications', 'oa_percentage', 'leadership_percentage', 'journal_publications']

# Step 2: Prepare empty list to collect region-clustered data
region_clusters = []

# Step 3: Loop through each region
for region_name, df_region in df_institutions.groupby('region'):
    df_region = df_region.copy()
    
    if len(df_region) < 3:
        df_region['region_cluster'] = 0
        df_region['region_cluster_k'] = 1
        region_clusters.append(df_region)
        continue

    # Step 3.1: MinMax scale within this region
    scaler = MinMaxScaler()
    df_region[features] = scaler.fit_transform(df_region[features])
    
    # Step 3.2: Auto-select best k using silhouette
    X = df_region[features]
    best_k = 2
    best_score = -1
    best_labels = None

    for k in range(2, min(11, len(df_region))):  # avoid k > number of rows
        kmeans = KMeans(n_clusters=k, random_state=42, n_init='auto')
        labels = kmeans.fit_predict(X)
        score = silhouette_score(X, labels)
        if score > best_score:
            best_k = k
            best_score = score
            best_labels = labels

    # Step 3.3: Assign best cluster labels
    df_region['region_cluster'] = best_labels
    df_region['region_cluster_k'] = best_k  # for reference
    
    # Step 3.4: Store
    region_clusters.append(df_region)

# Step 4: Combine all regions back into one dataframe
df_region_clustered = pd.concat(region_clusters, ignore_index=True)

# Save results
output_path = os.path.join(base_dir, "region_cluster.json")
df_region_clustered.to_json(output_path, orient="records", indent=2)

print(f"Clustered DataFrame saved to {output_path}")

df_region_clustered.info()