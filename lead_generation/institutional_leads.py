import os
import sys
import json
import pandas as pd
import numpy as np

from sklearn.preprocessing import MinMaxScaler

# ----------------------------
# Config: weights & parameters
# ----------------------------
WEIGHTS = {
    "oa_percentage": 0.30,           # openness fit
    "leadership_percentage": 0.25,   # authorship leadership footprint
    "publications": 0.10,            # research intensity (scaled)
    "mean_cites": 0.10,              # impact proxy (scaled)
    "journal_gap": 0.25              # whitespace: inverse of journal_publications
}

CLUSTER_BONUS = 0.05   # small bonus for clusters with above-median average score (within the region)

TOP_K_DEFAULT = 200    # how many leads to export

# ----------------------------
# Helpers
# ----------------------------
def safe_div(n, d):
    return float(n) / float(d) if d not in (0, None, np.nan) else 0.0

def canonical_inst(name):
    if pd.isna(name):
        return None
    return " ".join(str(name).lower().strip().split())

# ----------------------------
# Entry
# ----------------------------
if len(sys.argv) < 2:
    print("Usage: python generate_and_evaluate_leads.py <BASE_ISSN>")
    sys.exit(1)

base_issn = sys.argv[1].strip()
base_dir = os.path.join("data_fetching", "data", base_issn)

final_path   = os.path.join(base_dir, "final_database.json")
cluster_path = os.path.join(base_dir, "region_cluster.json")

if not os.path.exists(final_path):
    raise FileNotFoundError(f"Missing {final_path}")
if not os.path.exists(cluster_path):
    raise FileNotFoundError(f"Missing {cluster_path}")

df_final = pd.read_json(final_path, lines=True)
df_cluster = pd.read_json(cluster_path)

# Basic sanity: expected columns (we handle gracefully if some are missing)
expected_cols = [
    "doi","affiliation","country","oa_status","author_position","issn",
    "cites","referenced","region","journal_author"
]
missing_cols = [c for c in expected_cols if c not in df_final.columns]
if missing_cols:
    print(f"⚠️ Missing columns in final_database.json: {missing_cols} (script will skip features relying on them)")

# --------------------------------------------
# Build institution-level features (re-usable)
# --------------------------------------------
df_final["institution"] = df_final["affiliation"].apply(canonical_inst)
df_final = df_final[~df_final["institution"].isna()]

# 1) Core counts
df_inst = (
    df_final
    .groupby(["institution","country","region"], dropna=False)
    .agg(publications=("doi","nunique"))
    .reset_index()
)

# 2) OA share (exclude hybrid & closed as "OA")
if "oa_status" in df_final.columns:
    df_oa = df_final[~df_final["oa_status"].isin(["hybrid","closed"])]
    df_oa_counts = (
        df_oa.groupby(["institution","country"])
        .agg(oa_publications=("doi","nunique"))
        .reset_index()
    )
    df_inst = df_inst.merge(df_oa_counts, on=["institution","country"], how="left")
    df_inst["oa_publications"] = df_inst["oa_publications"].fillna(0)
    df_inst["oa_percentage"] = (df_inst["oa_publications"] / df_inst["publications"]).fillna(0).round(3)
    df_inst.drop(columns=["oa_publications"], inplace=True)
else:
    df_inst["oa_percentage"] = 0.0

# 3) Leadership percentage (first/last authorships)
if "author_position" in df_final.columns:
    df_total = (
        df_final.groupby(["institution","country"])
        .size().reset_index(name="total_authorships")
    )
    df_fl = df_final[df_final["author_position"].isin(["first","last"])]
    df_fl_counts = (
        df_fl.groupby(["institution","country"])
        .size().reset_index(name="leadership_authorships")
    )
    df_lead = df_total.merge(df_fl_counts, on=["institution","country"], how="left")
    df_lead["leadership_authorships"] = df_lead["leadership_authorships"].fillna(0)
    df_lead["leadership_percentage"] = (df_lead["leadership_authorships"] / df_lead["total_authorships"]).fillna(0).round(3)
    df_inst = df_inst.merge(df_lead[["institution","country","leadership_percentage"]], on=["institution","country"], how="left")
else:
    df_inst["leadership_percentage"] = 0.0

# 4) Publications in base journal (whitespace target)
df_journal = df_final[df_final["issn"].astype(str).str.contains(base_issn, na=False)]
df_j_counts = (
    df_journal.groupby(["institution","country"])
    .agg(journal_publications=("doi","nunique"))
    .reset_index()
)
df_inst = df_inst.merge(df_j_counts, on=["institution","country"], how="left")
df_inst["journal_publications"] = df_inst["journal_publications"].fillna(0).astype(int)

# 5) Impact proxy: mean cites per DOI (optional)
if "cites" in df_final.columns:
    df_cites = (
        df_final.groupby(["institution","country"])
        .agg(mean_cites=("cites","mean"))
        .reset_index()
    )
    df_inst = df_inst.merge(df_cites, on=["institution","country"], how="left")
    df_inst["mean_cites"] = df_inst["mean_cites"].fillna(0.0)
else:
    df_inst["mean_cites"] = 0.0

# 6) Merge region clusters for later small boost
df_inst = df_inst.merge(
    df_cluster[["institution","country","region","region_cluster","region_cluster_k"]],
    on=["institution","country","region"],
    how="left"
)

# --------------------------------------------
# Region-local scaling + score construction
# --------------------------------------------
def score_region_block(df_block):
    # Features to scale (if constant, MinMax gives 0; handle degenerate cases)
    scalers = {}
    scaled_cols = {}

    def minmax(col):
        vals = df_block[col].astype(float).to_numpy()
        vmin, vmax = np.nanmin(vals), np.nanmax(vals)
        if np.isnan(vmin) or np.isnan(vmax) or vmin == vmax:
            return np.zeros_like(vals)
        return (vals - vmin) / (vmax - vmin)

    df_block = df_block.copy()
    df_block["publications_s"]       = minmax("publications")
    df_block["mean_cites_s"]        = minmax("mean_cites")
    df_block["journal_publications_s"] = minmax("journal_publications")

    # "Whitespace" = inverse of journal presence
    df_block["journal_gap"] = 1.0 - df_block["journal_publications_s"]

    # Compose score
    score = (
        WEIGHTS["oa_percentage"]         * df_block["oa_percentage"].fillna(0) +
        WEIGHTS["leadership_percentage"] * df_block["leadership_percentage"].fillna(0) +
        WEIGHTS["publications"]          * df_block["publications_s"].fillna(0) +
        WEIGHTS["mean_cites"]            * df_block["mean_cites_s"].fillna(0) +
        WEIGHTS["journal_gap"]           * df_block["journal_gap"].fillna(0)
    )

    df_block["lead_score_raw"] = score

    # Cluster bonus: reward clusters that (within the region) have above-median raw score
    if "region_cluster" in df_block.columns and df_block["region_cluster"].notna().any():
        cluster_means = (
            df_block.groupby("region_cluster")["lead_score_raw"].mean().rename("cluster_mean")
        ).to_dict()
        df_block["cluster_mean"] = df_block["region_cluster"].map(cluster_means)
        median_cluster_mean = np.nanmedian(list(cluster_means.values())) if cluster_means else 0
        df_block["cluster_bonus"] = np.where(
            df_block["cluster_mean"] >= median_cluster_mean, CLUSTER_BONUS, 0.0
        )
    else:
        df_block["cluster_bonus"] = 0.0

    df_block["lead_score"] = (df_block["lead_score_raw"] + df_block["cluster_bonus"]).round(4)
    return df_block

leads = (
    df_inst
    .groupby("region", group_keys=False)
    .apply(score_region_block)
    .reset_index(drop=True)
)

# Rank and export
leads.sort_values(["region","lead_score"], ascending=[True, False], inplace=True)

# Helpful flags
leads["is_existing_in_base_journal"] = leads["journal_publications"] > 0
leads["rank_in_region"] = leads.groupby("region")["lead_score"].rank(ascending=False, method="first").astype(int)

# Export files
out_csv = os.path.join(base_dir, "institution_leads.csv")
out_json = os.path.join(base_dir, "institution_leads.json")
leads.to_csv(out_csv, index=False)
leads.to_json(out_json, orient="records", indent=2)
print(f"✅ Leads exported:\n - {out_csv}\n - {out_json}")

# --------------------------------------------
# Quality checks (quick offline evaluation)
# --------------------------------------------

def precision_at_k(df, k=50, positive_col="is_existing_in_base_journal"):
    topk = df.nlargest(k, "lead_score")
    if len(topk) == 0:
        return np.nan
    return float(topk[positive_col].sum()) / float(len(topk))

print("\n=== QUICK QUALITY CHECKS ===")
# 1) Correlation with research intensity (should be positive)
corr_pub = np.corrcoef(leads["lead_score"], leads["publications"])[0,1]
print(f"Correlation(lead_score, publications): {corr_pub:.3f}")

# 2) Precision@K using 'already published in base journal' as a weak proxy for 'fit'
for k in [25, 50, 100, 200]:
    p_at_k = precision_at_k(leads, k)
    print(f"Precision@{k} (already in base journal): {p_at_k:.3f}")

# 3) If year column exists, do a *temporal* backtest:
#    - Build scores using data <= (max_year - 1)
#    - Measure how many institutions publish in base_journal in max_year among top leads from (t-1)
if "year" in df_final.columns:
    print("\nTemporal backtest (t → t+1):")
    max_year = int(df_final["year"].dropna().max())
    split_year = max_year - 1

    # Train slice ≤ split_year
    train = df_final[df_final["year"] <= split_year].copy()
    if len(train) > 0:
        # Recompute institution table on train slice (reuse logic minimally)
        train["institution"] = train["affiliation"].apply(canonical_inst)
        train = train[~train["institution"].isna()]

        train_inst = train.groupby(["institution","country","region"]).agg(
            publications=("doi","nunique")
        ).reset_index()

        if "oa_status" in train.columns:
            train_oa = train[~train["oa_status"].isin(["hybrid","closed"])]
            t_oa_counts = train_oa.groupby(["institution","country"]).agg(oa_publications=("doi","nunique")).reset_index()
            train_inst = train_inst.merge(t_oa_counts, on=["institution","country"], how="left")
            train_inst["oa_percentage"] = (train_inst["oa_publications"] / train_inst["publications"]).fillna(0)
            train_inst.drop(columns=["oa_publications"], inplace=True)
        else:
            train_inst["oa_percentage"] = 0.0

        if "author_position" in train.columns:
            t_tot = train.groupby(["institution","country"]).size().reset_index(name="total_authorships")
            t_fl  = train[train["author_position"].isin(["first","last"])].groupby(["institution","country"]).size().reset_index(name="leadership_authorships")
            t_lead = t_tot.merge(t_fl, on=["institution","country"], how="left").fillna({"leadership_authorships":0})
            t_lead["leadership_percentage"] = (t_lead["leadership_authorships"] / t_lead["total_authorships"]).fillna(0)
            train_inst = train_inst.merge(t_lead[["institution","country","leadership_percentage"]], on=["institution","country"], how="left")
        else:
            train_inst["leadership_percentage"] = 0.0

        if "cites" in train.columns:
            t_cites = train.groupby(["institution","country"]).agg(mean_cites=("cites","mean")).reset_index()
            train_inst = train_inst.merge(t_cites, on=["institution","country"], how="left")
            train_inst["mean_cites"] = train_inst["mean_cites"].fillna(0.0)
        else:
            train_inst["mean_cites"] = 0.0

        # Merge clusters (static)
        train_inst = train_inst.merge(
            df_cluster[["institution","country","region","region_cluster","region_cluster_k"]],
            on=["institution","country","region"],
            how="left"
        )

        # Score (region-wise)
        train_scored = (
            train_inst
            .groupby("region", group_keys=False)
            .apply(lambda df: score_region_block(df))
            .reset_index(drop=True)
        )
        train_scored = train_scored.sort_values(["region","lead_score"], ascending=[True, False])

        # Target in t+1: who actually published in base journal in max_year?
        test_year = max_year
        test = df_final[(df_final["year"] == test_year) & (df_final["issn"].astype(str).str.contains(base_issn, na=False))].copy()
        inst_published_next = set(test["affiliation"].apply(canonical_inst).dropna().unique())

        # Precision@K on future conversion
        for k in [25, 50, 100, 200]:
            topk = train_scored.nlargest(k, "lead_score")
            converted = topk["institution"].isin(inst_published_next).mean() if len(topk) else np.nan
            print(f"Temporal Precision@{k} (published in base journal in {test_year}): {converted:.3f}")
    else:
        print("Not enough data before split_year; skipping temporal backtest.")
else:
    print("\n(no 'year' column found; skipping temporal backtest)")
