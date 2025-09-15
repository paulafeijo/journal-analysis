#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clean_cluster_compat_issn.py

Interactive, strict-compat clustering:
- Prompts for an ISSN (e.g., 2296-987X)
- Reads: data_fetching/data/{ISSN}/institutional_database.json
- Writes (same folder): global_clusters.json (drop-in for Tableau), cluster_profiles.json

Behavior:
- Preserves ALL original input columns.
- Adds ONE column named `cluster` (not `_cluster`).
- No auxiliary has_* flags in the output JSON.
- Robust preprocessing: missingness filtering, median imputation (country→region→global),
  special handling for months_since_last_pub and growth_rate, winsorization, log1p on skew,
  scaling, clustering (KMeans with K search 2..6 by default).
"""

import json
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import MiniBatchKMeans
from sklearn.metrics import silhouette_score

# Optional: HDBSCAN (if installed) can be toggled below
try:
    import hdbscan  # type: ignore
    HDBSCAN_AVAILABLE = True
except Exception:
    HDBSCAN_AVAILABLE = False


def step(msg: str) -> None:
    print(f"[INFO] {msg}", file=sys.stderr)


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
        if s.min() >= 0 and s.max() > 1.0 and s.skew(skipna=True) > 1.0:
            df[c] = np.log1p(s)
            transformed.append(c)
    return transformed


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
                if ctry_medians is not None and pd.notna(row.get(country_col, np.nan)) and hasattr(ctry_medians, 'index') and row[country_col] in ctry_medians.index:
                    val = ctry_medians.loc[row[country_col], c]
                if (val is None or pd.isna(val)) and reg_medians is not None and pd.notna(row.get(region_col, np.nan)) and hasattr(reg_medians, 'index') and row[region_col] in reg_medians.index:
                    val = reg_medians.loc[row[region_col], c]
                if val is None or pd.isna(val):
                    val = glob_medians[c]
                row[c] = val
        return row

    df[feature_cols] = df.apply(impute_row, axis=1)[feature_cols]


def cluster_kmeans_with_search(X: np.ndarray, k_lo: int = 2, k_hi: int = 6, random_state: int = 42) -> Tuple[np.ndarray, dict]:
    best_s = -1
    best_k = None
    best_labels = None
    for kk in range(k_lo, k_hi + 1):
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
            best_labels = labels
    if best_labels is None:
        # fallback to K=3
        km = MiniBatchKMeans(n_clusters=3, random_state=random_state, n_init="auto")
        best_labels = km.fit_predict(X)
        best_k = 3
        best_s = None
    rep = {
        "algo": "kmeans",
        "k": int(best_k),
        "silhouette": (float(best_s) if best_s is not None else None),
        "n_clusters_found": int(len(set(best_labels))),
    }
    return best_labels, rep


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
    step("Start: asking for ISSN")
    base_issn = input("Enter base ISSN (e.g. 2296-987X): ").strip()
    step(f"ISSN received: {base_issn}")

    # Configuration (can be adjusted if your dataset uses different column names)
    country_col = "country"
    region_col = "region"
    months_col = "months_since_last_pub"
    growth_col = "growth_rate"
    missing_thresh = 0.7  # drop features with >70% missingness
    use_hdbscan = False   # set True to use HDBSCAN (requires installation)

    base_dir = Path("data_fetching") / "data" / base_issn
    in_path = base_dir / "institutional_database.json"

    if not in_path.exists():
        print(f"ERROR: {in_path} not found.", file=sys.stderr)
        sys.exit(1)

    step(f"Reading input: {in_path}")
    # Load (supports JSON (records or object), JSONL is also handled by lines=True if needed)
    try:
        df_raw = pd.read_json(in_path, lines=False)
    except ValueError:
        # try JSONL
        df_raw = pd.read_json(in_path, lines=True)

    df = df_raw.copy()

    # Basic row cleaning: drop country == "None" / empty / NaN
    if country_col in df.columns:
        bad_mask = df[country_col].isin(["None", "", "nan", "NaN"]) | df[country_col].isna()
        dropped = int(bad_mask.sum())
        if dropped:
            step(f"Dropping {dropped} rows with invalid country")
        df = df.loc[~bad_mask].copy()

    # Feature selection: all numeric columns except meta
    meta_exclude = set([country_col, region_col])
    feature_cols = [c for c in df.select_dtypes(include=[np.number]).columns if c not in meta_exclude]
    if not feature_cols:
        print("ERROR: No numeric feature columns detected. Check your dataset.", file=sys.stderr)
        sys.exit(1)

    # Special imputations
    if months_col in df.columns:
        df[months_col] = df[months_col].fillna(60)

    if growth_col in df.columns:
        pubs_cols = [c for c in df.columns if c.lower() in ("publications", "journal_publications", "total_publications")]
        if pubs_cols:
            has_signal = df[pubs_cols].fillna(0).sum(axis=1) > 0
            df.loc[~has_signal & df[growth_col].isna(), growth_col] = 0.0

    # Drop features with excessive missingness
    miss_frac = df[feature_cols].isna().mean()
    feature_cols = [c for c in feature_cols if miss_frac.get(c, 0.0) <= missing_thresh]
    if not feature_cols:
        print("ERROR: All features exceeded missingness threshold. Try lowering the threshold.", file=sys.stderr)
        sys.exit(1)

    # Impute remaining NaNs with country/region/global medians
    impute_with_group_median(df, feature_cols, region_col=region_col, country_col=country_col)

    # Winsorize and log1p-transform skewed features
    for c in feature_cols:
        df[c] = winsorize_series(df[c], 0.01, 0.99)
    _ = auto_log_transform(df, feature_cols)

    # Scale
    scaler = StandardScaler()
    X = scaler.fit_transform(df[feature_cols].values)

    # Cluster
    if use_hdbscan:
        labels, report = cluster_hdbscan(X)
    else:
        labels, report = cluster_kmeans_with_search(X, k_lo=2, k_hi=6, random_state=42)

    # Prepare outputs with strict compatibility
    out_df = df_raw.loc[df.index].copy()  # preserve original columns / order for surviving rows
    out_df["cluster"] = labels

    clusters_json_path = base_dir / "global_clusters.json"
    profiles_json_path = base_dir / "cluster_profiles.json"

    # Write outputs
    out_df.to_json(clusters_json_path, orient="records", lines=False)

    profiles = {
        "n_rows": int(out_df.shape[0]),
        "n_features_used": int(len(feature_cols)),
        "algo_report": report,
        "clusters": {}
    }
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

    with open(profiles_json_path, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2, ensure_ascii=False)

    step(f"Wrote clusters to: {clusters_json_path}")
    step(f"Wrote profiles to: {profiles_json_path}")
    step("Done.")


if __name__ == "__main__":
    main()
