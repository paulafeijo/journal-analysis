#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clean_cluster_compat.py

Purpose
-------
Produce a drop-in replacement for your previous `global_clusters.json` so you can
swap the Tableau datasource without schema breaks.

Behavior
--------
- Preserves ALL original input columns exactly as-is.
- Adds ONE new column named `cluster` (not `_cluster`).
- Does NOT include auxiliary columns like has_* flags in the final JSON.
- Applies robust cleaning + preprocessing internally to improve clustering quality.

Key Improvements
----------------
- Drops garbage rows where country == "None" (default) unless you pass --keep-country-none.
- Drops features with excessive missingness (configurable threshold).
- Imputes remaining missing values using country median → region median → global median.
- Special handling:
    * months_since_last_pub: null → 60
    * growth_rate: null → 0 only when publication signals are absent, else median-imputed
- Winsorizes extremes, log1p-transforms skewed non-negative features, and scales before clustering.
- Global KMeans by default with optional K search. HDBSCAN available if installed.

Outputs
-------
- global_clusters.json  (same columns as input + `cluster`)
- cluster_profiles.json (summary, optional but useful for QA)

Usage Examples
--------------
python clean_cluster_compat.py --input path/to/your_data.jsonl --k 3
python clean_cluster_compat.py --input path/to/your_data.csv --k-range 2 6
python clean_cluster_compat.py --input your.parquet --algo hdbscan
"""

import argparse
import json
import os
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import MiniBatchKMeans
from sklearn.metrics import silhouette_score

# Optional: HDBSCAN for density-based clustering
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


def auto_log_transform(df: pd.DataFrame, cols: List[str]) -> List[str]:
    transformed = []
    for c in cols:
        s = df[c]
        # Log1p if non-negative and positively skewed
        if s.min() >= 0 and s.max() > 1.0 and s.skew(skipna=True) > 1.0:
            df[c] = np.log1p(s)
            transformed.append(c)
    return transformed


def choose_numeric_features(df: pd.DataFrame, exclude: List[str]) -> List[str]:
    numeric = df.select_dtypes(include=[np.number]).columns.tolist()
    return [c for c in numeric if c not in exclude]


def impute_with_group_median(
    df: pd.DataFrame,
    feature_cols: List[str],
    region_col: Optional[str],
    country_col: Optional[str]
) -> None:
    glob_medians = df[feature_cols].median(numeric_only=True)

    reg_medians = None
    if region_col and region_col in df.columns:
        reg_medians = df.groupby(region_col)[feature_cols].median(numeric_only=True)

    ctry_medians = None
    if country_col and country_col in df.columns:
        ctry_medians = df.groupby(country_col)[feature_cols].median(numeric_only=True)

    def impute_row(row):
        for c in feature_cols:
            if pd.isna(row[c]):
                val = None
                if ctry_medians is not None and pd.notna(row.get(country_col, np.nan)) and row[country_col] in (ctry_medians.index if hasattr(ctry_medians, 'index') else []):
                    val = ctry_medians.loc[row[country_col], c]
                if (val is None or pd.isna(val)) and reg_medians is not None and pd.notna(row.get(region_col, np.nan)) and row[region_col] in (reg_medians.index if hasattr(reg_medians, 'index') else []):
                    val = reg_medians.loc[row[region_col], c]
                if val is None or pd.isna(val):
                    val = glob_medians[c]
                row[c] = val
        return row

    df[feature_cols] = df.apply(impute_row, axis=1)[feature_cols]


def cluster_kmeans(X: np.ndarray, k: int, k_range: Optional[Tuple[int, int]], random_state: int = 42) -> Tuple[np.ndarray, dict]:
    chosen_k = k
    if k_range is not None and k_range[0] < k_range[1]:
        best_s = -1
        best_k = None
        for kk in range(k_range[0], k_range[1] + 1):
            km = MiniBatchKMeans(n_clusters=kk, random_state=random_state, n_init="auto")
            labels = km.fit_predict(X)
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

    km = MiniBatchKMeans(n_clusters=chosen_k, random_state=random_state, n_init="auto")
    labels = km.fit_predict(X)
    rep = {
        "algo": "kmeans",
        "k": int(chosen_k),
        "n_clusters_found": int(len(set(labels))),
    }
    if len(set(labels)) > 1:
        try:
            rep["silhouette"] = float(silhouette_score(X, labels))
        except Exception:
            rep["silhouette"] = None
    else:
        rep["silhouette"] = None
    return labels, rep


def cluster_hdbscan(X: np.ndarray) -> Tuple[np.ndarray, dict]:
    if not HDBSCAN_AVAILABLE:
        raise RuntimeError("hdbscan not installed. Try: pip install hdbscan")
    model = hdbscan.HDBSCAN(min_cluster_size=15, min_samples=5)
    labels = model.fit_predict(X)
    rep = {
        "algo": "hdbscan",
        "n_clusters_found": int(len(set(labels)) - (1 if -1 in labels else 0)),
        "contains_noise": int(-1 in labels),
    }
    return labels, rep


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to input table (CSV/JSON/JSONL/Parquet).")
    parser.add_argument("--out-dir", default=None, help="Directory for outputs (default: alongside input).")
    parser.add_argument("--country-col", default="country", help="Country column name.")
    parser.add_argument("--region-col", default="region", help="Region column name.")
    parser.add_argument("--months-col", default="months_since_last_pub", help="Column with months since last publication.")
    parser.add_argument("--growth-col", default="growth_rate", help="Growth rate column.")
    parser.add_argument("--keep-country-none", action="store_true", help='Keep rows where country == "None" (default is to drop).')
    parser.add_argument("--missing-thresh", type=float, default=0.7, help="Drop features with missingness > threshold (0-1).")
    parser.add_argument("--algo", choices=["kmeans", "hdbscan"], default="kmeans")
    parser.add_argument("--k", type=int, default=3, help="K for kmeans when not using --k-range.")
    parser.add_argument("--k-range", nargs=2, type=int, default=None, help="If provided, search K in [lo, hi] and pick best silhouette.")
    parser.add_argument("--random-state", type=int, default=42)
    args = parser.parse_args()

    df_raw = read_table(args.input)
    out_dir = args.out_dir or os.path.dirname(os.path.abspath(args.input)) or "."
    os.makedirs(out_dir, exist_ok=True)

    # 1) Basic row cleaning
    df = df_raw.copy()
    if args.country_col in df.columns and not args.keep_country_none:
        bad_mask = df[args.country_col].isin(["None", "", "nan", "NaN"]) | df[args.country_col].isna()
        df = df.loc[~bad_mask].copy()

    # 2) Feature selection: all numeric columns except meta
    meta_exclude = set([args.country_col, args.region_col])
    feature_cols = [c for c in df.select_dtypes(include=[np.number]).columns if c not in meta_exclude]
    if not feature_cols:
        raise RuntimeError("No numeric feature columns detected. Ensure your dataset has numeric features.")

    # 3) Special imputations
    if args.months_col in df.columns:
        df[args.months_col] = df[args.months_col].fillna(60)

    if args.growth_col in df.columns:
        pubs_cols = [c for c in df.columns if c.lower() in ("publications", "journal_publications", "total_publications")]
        if pubs_cols:
            has_signal = df[pubs_cols].fillna(0).sum(axis=1) > 0
            df.loc[~has_signal & df[args.growth_col].isna(), args.growth_col] = 0.0

    # 4) Drop features with excessive missingness
    miss_frac = df[feature_cols].isna().mean()
    feature_cols = [c for c in feature_cols if miss_frac.get(c, 0.0) <= args.missing_thresh]
    if not feature_cols:
        raise RuntimeError("All features exceeded missingness threshold. Try increasing --missing-thresh.")

    # 5) Impute remaining NaNs with country/region/global medians
    impute_with_group_median(df, feature_cols, args.region_col, args.country_col)

    # 6) Winsorize and log1p-transform skewed features
    for c in feature_cols:
        df[c] = winsorize_series(df[c], 0.01, 0.99)
    _ = auto_log_transform(df, feature_cols)

    # 7) Scale
    scaler = StandardScaler()
    X = scaler.fit_transform(df[feature_cols].values)

    # 8) Cluster
    if args.algo == "kmeans":
        labels, report = cluster_kmeans(X, k=args.k, k_range=(tuple(args.k_range) if args.k_range else None), random_state=args.random_state)
    else:
        labels, report = cluster_hdbscan(X)

    # 9) Prepare outputs with strict compatibility
    out_df = df_raw.loc[df.index].copy()  # preserve original columns / order
    out_df["cluster"] = labels  # single new column named 'cluster'

    clusters_json_path = os.path.join(out_dir, "global_clusters.json")
    out_df.to_json(clusters_json_path, orient="records", lines=False)

    # Optional: cluster profiles for QA (not required by Tableau)
    profiles = {
        "n_rows": int(out_df.shape[0]),
        "n_features_used": int(len(feature_cols)),
        "algo_report": report,
        "clusters": {}
    }
    # summarize using the transformed df (df) to reflect preprocessing
    df_with_labels = df.copy()
    df_with_labels["cluster"] = labels
    for k, sub in df_with_labels.groupby("cluster"):
        prof = {
            "size": int(sub.shape[0]),
            "feature_medians": {c: float(sub[c].median()) for c in feature_cols},
            "feature_means": {c: float(sub[c].mean()) for c in feature_cols},
            "feature_p90": {c: float(sub[c].quantile(0.90)) for c in feature_cols},
        }
        profiles["clusters"][int(k)] = prof

    profiles_json_path = os.path.join(out_dir, "cluster_profiles.json")
    with open(profiles_json_path, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2, ensure_ascii=False)

    print(f"Saved:\n- {clusters_json_path}\n- {profiles_json_path}")
    print("Done.")


if __name__ == "__main__":
    main()
