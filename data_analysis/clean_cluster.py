#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clean + cluster institutions with robust preprocessing.

Key improvements:
- Drop garbage rows (e.g., country == "None")
- Remove features with excessive missingness
- Add missingness flags (has_<col>)
- Smarter imputation (regional median when possible; special rules for growth_rate, months_since_last_pub)
- Winsorize extreme values; log1p-transform skewed features; scale
- Optional per-region clustering
- Produce interpretable cluster profiles + summary metrics

Usage examples:
  python clean_cluster.py --input data.csv --id-col institution --name-col institution --country-col country --region-col region --k 3
  python clean_cluster.py --input data.jsonl --per-region --algo kmeans --k-range 2 6

Outputs (by default in the input's directory unless --out-dir provided):
  - cleaned_dataset.csv
  - global_clusters.json
  - cluster_profiles.json
  - preprocessing_report.json
"""
import argparse
import json
import math
import os
import sys
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans, MiniBatchKMeans
from sklearn.metrics import silhouette_score

# Optional: If hdbscan is available, we can use it.
try:
    import hdbscan  # type: ignore
    HDBSCAN_AVAILABLE = True
except Exception:
    HDBSCAN_AVAILABLE = False


def read_table(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.csv',):
        return pd.read_csv(path)
    elif ext in ('.json',):
        return pd.read_json(path, lines=False)
    elif ext in ('.jsonl', '.ndjson'):
        return pd.read_json(path, lines=True)
    elif ext in ('.parquet',):
        return pd.read_parquet(path)
    else:
        raise ValueError(f"Unsupported file extension: {ext}. Use CSV/JSON/JSONL/Parquet.")


def winsorize_series(s: pd.Series, lower_q: float = 0.01, upper_q: float = 0.99) -> pd.Series:
    if s.dropna().empty:
        return s
    lo = s.quantile(lower_q)
    hi = s.quantile(upper_q)
    return s.clip(lo, hi)


def choose_numeric_features(df: pd.DataFrame, exclude: List[str]) -> List[str]:
    numeric = df.select_dtypes(include=[np.number]).columns.tolist()
    return [c for c in numeric if c not in exclude]


def add_missing_flags(df: pd.DataFrame, cols: List[str]) -> Tuple[pd.DataFrame, List[str]]:
    flags = []
    for c in cols:
        if df[c].isna().any():
            flag = f"has_{c}"
            df[flag] = (~df[c].isna()).astype(int)
            flags.append(flag)
    return df, flags


def impute_with_regional_median(
    df: pd.DataFrame,
    feature_cols: List[str],
    region_col: Optional[str],
    country_col: Optional[str]
) -> pd.DataFrame:
    # Create helper medians
    reg_medians = {}
    ctry_medians = {}
    glob_medians = df[feature_cols].median(numeric_only=True)

    if region_col and region_col in df.columns:
        reg_medians = df.groupby(region_col)[feature_cols].median(numeric_only=True)

    if country_col and country_col in df.columns:
        ctry_medians = df.groupby(country_col)[feature_cols].median(numeric_only=True)

    def impute_row(row):
        for c in feature_cols:
            if pd.isna(row[c]):
                val = None
                # Prefer country median, then region, then global
                if country_col and country_col in row and pd.notna(row[country_col]) and row[country_col] in ctry_medians.index:
                    val = ctry_medians.loc[row[country_col], c]
                if (val is None or pd.isna(val)) and region_col and region_col in row and pd.notna(row[region_col]) and row[region_col] in reg_medians.index:
                    val = reg_medians.loc[row[region_col], c]
                if val is None or pd.isna(val):
                    val = glob_medians[c]
                row[c] = val
        return row

    df[feature_cols] = df.apply(impute_row, axis=1)[feature_cols]
    return df


def special_imputations(df: pd.DataFrame, months_col: Optional[str], growth_col: Optional[str]) -> pd.DataFrame:
    # months_since_last_pub: if null, set to a conservative "long time" value (e.g., 60 months)
    if months_col and months_col in df.columns:
        df[months_col] = df[months_col].fillna(60)

    # growth_rate: if null, fill with 0 only if both publications and journal_publications are 0 or null.
    if growth_col and growth_col in df.columns:
        pubs_cols = [c for c in df.columns if c.lower() in ("publications", "journal_publications", "total_publications")]
        has_signal = df[pubs_cols].fillna(0).sum(axis=1) > 0 if pubs_cols else pd.Series(True, index=df.index)
        # If there's signal, defer to regional/global median in next step (leave NaN here).
        df.loc[~has_signal & df[growth_col].isna(), growth_col] = 0.0
    return df


def make_cluster_profiles(df_with_labels: pd.DataFrame, feature_cols: List[str], label_col: str, id_col: Optional[str], name_col: Optional[str]) -> dict:
    out = {
        "n_rows": int(df_with_labels.shape[0]),
        "n_features": int(len(feature_cols)),
        "clusters": {}
    }
    for k, sub in df_with_labels.groupby(label_col):
        prof = {
            "size": int(sub.shape[0]),
            "feature_medians": sub[feature_cols].median(numeric_only=True).to_dict(),
            "feature_means": sub[feature_cols].mean(numeric_only=True).to_dict(),
            "feature_p90": sub[feature_cols].quantile(0.90, numeric_only=True).to_dict(),
            "example_ids": sub[id_col].dropna().astype(str).head(5).tolist() if id_col and id_col in sub.columns else [],
            "example_names": sub[name_col].dropna().astype(str).head(5).tolist() if name_col and name_col in sub.columns else [],
        }
        out["clusters"][int(k)] = prof
    return out


def auto_log_transform(df: pd.DataFrame, cols: List[str]) -> Tuple[pd.DataFrame, List[str]]:
    transformed = []
    for c in cols:
        s = df[c]
        # Apply log1p if positively skewed and values are non-negative
        if s.min() >= 0 and s.skew(skipna=True) > 1.0 and s.max() > 1.0:
            df[c] = np.log1p(s)
            transformed.append(c)
    return df, transformed


def cluster_block(
    df: pd.DataFrame,
    feature_cols: List[str],
    algo: str,
    k: int,
    k_range: Optional[Tuple[int, int]] = None,
    random_state: int = 42,
) -> Tuple[pd.DataFrame, dict]:
    X = df[feature_cols].values

    chosen_k = k
    model = None
    sil = None

    if algo.lower() == "hdbscan":
        if not HDBSCAN_AVAILABLE:
            raise RuntimeError("hdbscan not installed. Try: pip install hdbscan")
        model = hdbscan.HDBSCAN(min_cluster_size=15, min_samples=5)
        labels = model.fit_predict(X)
        df["_cluster"] = labels
        # Silhouette only valid if >= 2 clusters and no -1 noise; compute cautiously
        if len(set(labels)) >= 2 and (np.array(labels) >= 0).any():
            mask = labels >= 0
            sil = float(silhouette_score(X[mask], labels[mask]))
    else:
        # KMeans (default)
        if k_range is not None and k_range[0] < k_range[1]:
            best_s = -1
            best_k = None
            for kk in range(k_range[0], k_range[1] + 1):
                km = MiniBatchKMeans(n_clusters=kk, random_state=random_state, n_init="auto")
                labels = km.fit_predict(X)
                # avoid degenerate silhouette with 1 cluster
                if len(set(labels)) > 1:
                    try:
                        s = silhouette_score(X, labels)
                    except Exception:
                        s = -1
                else:
                    s = -1
                if s > best_s:
                    best_s = s
                    best_k = kk
            chosen_k = best_k if best_k is not None else k
        model = MiniBatchKMeans(n_clusters=chosen_k, random_state=random_state, n_init="auto")
        labels = model.fit_predict(X)
        df["_cluster"] = labels
        if len(set(labels)) > 1:
            try:
                sil = float(silhouette_score(X, labels))
            except Exception:
                sil = None

    report = {
        "algo": algo,
        "k": int(chosen_k) if chosen_k else None,
        "silhouette": sil,
        "n_clusters_found": int(len(set(df["_cluster"]))),
    }
    return df, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to input table (CSV/JSON/JSONL/Parquet).")
    parser.add_argument("--out-dir", default=None, help="Directory for outputs (default: alongside input).")
    parser.add_argument("--id-col", default=None, help="ID column (optional).")
    parser.add_argument("--name-col", default=None, help="Institution/name column (optional).")
    parser.add_argument("--country-col", default="country", help="Country column name.")
    parser.add_argument("--region-col", default="region", help="Region column name.")
    parser.add_argument("--months-col", default="months_since_last_pub", help="Column with months since last publication.")
    parser.add_argument("--growth-col", default="growth_rate", help="Growth rate column.")
    parser.add_argument("--drop-country-none", action="store_true", help='Drop rows where country == "None" or null.')
    parser.add_argument("--drop-empty-rows", action="store_true", help="Drop rows with all-zero/all-null feature vectors.")
    parser.add_argument("--feature-cols", nargs="*", default=None, help="Explicit feature columns. If omitted, auto-detect numeric columns.")
    parser.add_argument("--exclude-cols", nargs="*", default=[], help="Columns to exclude from features.")
    parser.add_argument("--missing-thresh", type=float, default=0.7, help="Drop features with missingness > threshold (0-1).")
    parser.add_argument("--algo", choices=["kmeans", "hdbscan"], default="kmeans")
    parser.add_argument("--k", type=int, default=3, help="K for kmeans when not using --k-range.")
    parser.add_argument("--k-range", nargs=2, type=int, default=None, help="If provided, search K in [lo, hi] and pick best silhouette.")
    parser.add_argument("--per-region", action="store_true", help="Cluster independently per region.")
    parser.add_argument("--random-state", type=int, default=42)
    args = parser.parse_args()

    df = read_table(args.input)

    out_dir = args.out_dir or os.path.dirname(os.path.abspath(args.input)) or "."
    os.makedirs(out_dir, exist_ok=True)

    # Basic cleaning: drop country == "None"
    if args.drop_country_none and args.country_col in df.columns:
        before = len(df)
        df = df[~df[args.country_col].isin([None, np.nan, "None", "", "nan"])].copy()
        print(f"Dropped {before - len(df)} rows with country None/NaN.")

    # Identify feature columns
    meta_exclude = set([c for c in [args.id_col, args.name_col, args.country_col, args.region_col] if c]) | set(args.exclude_cols)
    if args.feature_cols:
        feature_cols = [c for c in args.feature_cols if c in df.columns]
    else:
        feature_cols = choose_numeric_features(df, exclude=list(meta_exclude))

    if not feature_cols:
        raise RuntimeError("No feature columns detected. Provide --feature-cols or check your data.")

    # Special imputations for key columns (do NOT finalize yet; we keep NaNs for regional median later where applicable)
    df = special_imputations(df, months_col=args.months_col, growth_col=args.growth_col)

    # Drop features over missingness threshold
    miss_frac = df[feature_cols].isna().mean()
    keep_cols = [c for c in feature_cols if miss_frac.get(c, 0.0) <= args.missing_thresh]
    dropped_feats = sorted(set(feature_cols) - set(keep_cols))
    if dropped_feats:
        print(f"Dropping {len(dropped_feats)} features with high missingness: {dropped_feats}")
    feature_cols = keep_cols

    # Add missingness flags
    df, flag_cols = add_missing_flags(df, feature_cols)

    # Impute remaining NaNs with country/region/global medians
    df = impute_with_regional_median(df, feature_cols, region_col=args.region_col, country_col=args.country_col)

    # Remove rows where all features are zero/NaN (after imputation zeros may remain for true zeros)
    if args.drop_empty_rows:
        mask_nonzero = (df[feature_cols].fillna(0).abs().sum(axis=1) > 0)
        before = len(df)
        df = df[mask_nonzero].copy()
        print(f"Dropped {before - len(df)} rows with all-zero feature vectors.")

    # Winsorize and log1p-transform skewed features
    for c in feature_cols:
        df[c] = winsorize_series(df[c], 0.01, 0.99)
    df, log_transformed = auto_log_transform(df, feature_cols)

    # Scale
    scaler = StandardScaler()
    df_scaled = df.copy()
    df_scaled[feature_cols] = scaler.fit_transform(df_scaled[feature_cols])

    # Clustering (global or per-region)
    reports = {}
    if args.per_region and args.region_col in df_scaled.columns:
        labels = np.empty(len(df_scaled), dtype=object)
        for reg, idx in df_scaled.groupby(args.region_col).groups.items():
            sub = df_scaled.loc[idx, feature_cols]
            if sub.shape[0] < 2:
                labels[idx] = -1  # not enough points
                continue
            # choose k if requested, otherwise use provided k
            k_rng = tuple(args.k_range) if args.k_range else None
            sub_df = df_scaled.loc[idx, :].copy()
            sub_df, rep = cluster_block(sub_df, feature_cols, args.algo, k=args.k, k_range=k_rng, random_state=args.random_state)
            labels[idx] = sub_df["_cluster"].values
            reports[str(reg)] = rep
        df_scaled["_cluster"] = labels
        sil_global = None
        valid = [i for i, lab in enumerate(df_scaled["_cluster"].values) if lab != -1]
        if len(set(df_scaled["_cluster"].values[valid])) > 1:
            try:
                sil_global = float(silhouette_score(df_scaled.loc[valid, feature_cols].values, df_scaled["_cluster"].values[valid].astype(int)))
            except Exception:
                sil_global = None
        reports["_global_silhouette"] = sil_global
    else:
        k_rng = tuple(args.k_range) if args.k_range else None
        df_scaled, rep = cluster_block(df_scaled, feature_cols, args.algo, k=args.k, k_range=k_rng, random_state=args.random_state)
        reports["global"] = rep

    # Build outputs
    cleaned_path = os.path.join(out_dir, "cleaned_dataset.csv")
    df.to_csv(cleaned_path, index=False)

    # clusters output (keep meta + label)
    meta_cols = [c for c in [args.id_col, args.name_col, args.country_col, args.region_col] if c and c in df_scaled.columns]
    out_cols = meta_cols + feature_cols + flag_cols + ["_cluster"]
    clusters_df = df_scaled[out_cols].copy()
    clusters_json_path = os.path.join(out_dir, "global_clusters.json")
    clusters_df.to_json(clusters_json_path, orient="records", lines=False)

    # profiles
    profiles = make_cluster_profiles(clusters_df, feature_cols + flag_cols, "_cluster", args.id_col, args.name_col)
    profiles_json_path = os.path.join(out_dir, "cluster_profiles.json")
    with open(profiles_json_path, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2, ensure_ascii=False)

    # preprocessing report
    prep = {
        "dropped_features_high_missing": dropped_feats,
        "log_transformed_features": log_transformed,
        "feature_cols_used": feature_cols,
        "flags_added": flag_cols,
        "reports": reports,
    }
    prep_json_path = os.path.join(out_dir, "preprocessing_report.json")
    with open(prep_json_path, "w", encoding="utf-8") as f:
        json.dump(prep, f, indent=2, ensure_ascii=False)

    print(f"\nSaved:\n- {cleaned_path}\n- {clusters_json_path}\n- {profiles_json_path}\n- {prep_json_path}")
    print("\nDone.")

if __name__ == "__main__":
    main()
