# -*- coding: utf-8 -*-
"""
generate_leads.py — Journal-specific institutional lead scoring (interactive, base_issn-aware)

Includes REGION in the output. Region is:
- carried through from institutional_database.json if present
- otherwise derived from Country (ISO alpha-2) via a simple mapping

Other features:
- Prompts ONLY for base_issn; root fixed to data_fetching/data
- Prints progress at each step
- Scores institutions and writes institutional_leads.json
- --debug flag appends component scores and RAW (uncapped) values
- --tier-mode {percentile,fixed} with optional --high-cutoff/--medium-cutoff
- UPDATED Agreement Suggestion rules:
    TA: journal_publications >= 10 AND (oa% < 0.5 OR in_open_apc_institution OR paid_articles >= P60)
    Waiver: 1..9 journal_publications AND oa% >= 0.4 AND NOT in_open_apc_institution AND paid_articles < P60
"""

import argparse
import io
import json
import math
import os
import sys
from typing import Optional

import numpy as np
import pandas as pd

ROOT = "data_fetching/data"


def step(msg: str) -> None:
    print(f"[generate_leads] {msg}", flush=True)


def _read_json(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")
    try:
        return pd.read_json(path, lines=False)
    except ValueError:
        return pd.read_json(path, lines=True)


def _norm_key(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
        .str.strip()
        .str.replace(r"\\s+", " ", regex=True)
        .str.replace(r"^nan$", "", regex=True)
        .str.replace(r"^none$", "", regex=True, case=False)
    )


def _country_to_region(code: str) -> str:
    """Very lightweight ISO2 -> region mapping; extend as needed."""
    if not isinstance(code, str) or len(code) == 0:
        return "Other/Unknown"
    c = code.upper()

    europe = {
        "AL","AD","AM","AT","AZ","BA","BE","BG","BY","CH","CY","CZ","DE","DK","EE",
        "ES","FI","FO","FR","GB","GE","GG","GI","GR","HR","HU","IE","IM","IS","IT",
        "JE","KZ","LI","LT","LU","LV","MC","MD","ME","MK","MT","NL","NO","PL","PT",
        "RO","RS","RU","SE","SI","SK","SM","TR","UA","VA"
    }
    asia = {
        "AE","AF","BD","BH","BN","BT","CC","CN","CX","HK","ID","IL","IN","IO","IQ",
        "IR","JO","JP","KG","KH","KP","KR","KW","LA","LB","LK","MM","MN","MO","MV",
        "MY","NP","OM","PH","PK","PS","QA","SA","SG","SY","TH","TJ","TL","TM","TW",
        "UZ","VN","YE"
    }
    north_america = {
        "AG","AI","AW","BB","BL","BM","BQ","BS","BZ","CA","CR","CU","CW","DM","DO",
        "GD","GL","GP","GT","HN","HT","JM","KN","KY","LC","MF","MQ","MS","MX","NI",
        "PA","PM","PR","SV","SX","TC","TT","US","VC","VG","VI"
    }
    south_america = {"AR","BO","BR","CL","CO","EC","FK","GF","GY","PE","PY","SR","UY","VE"}
    africa = {
        "AO","BF","BI","BJ","BW","CD","CF","CG","CI","CM","CV","DJ","DZ","EG","EH",
        "ER","ET","GA","GH","GM","GN","GQ","GW","KE","KM","LR","LS","LY","MA","MG",
        "ML","MR","MU","MW","MZ","NA","NE","NG","RE","RW","SC","SD","SH","SL","SN",
        "SO","SS","ST","SZ","TD","TG","TN","TZ","UG","YT","ZA","ZM","ZW"
    }
    oceania = {
        "AS","AU","CK","FJ","FM","GU","KI","MH","MP","NC","NF","NR","NU","NZ","PF",
        "PG","PN","PW","SB","TK","TL","TO","TV","UM","VU","WF","WS"
    }
    if c in europe: return "Europe"
    if c in asia: return "Asia"
    if c in north_america: return "North America"
    if c in south_america: return "South America"
    if c in africa: return "Africa"
    if c in oceania: return "Oceania"
    return "Other/Unknown"


def winsorize_series(x: pd.Series, lower=0.01, upper=0.99) -> pd.Series:
    if x.isna().all():
        return x.fillna(0.0)
    lo = x.quantile(lower)
    hi = x.quantile(upper)
    return x.clip(lower=lo, upper=hi)


def minmax(x: pd.Series) -> pd.Series:
    if x.isna().all():
        return x.fillna(0.0)
    xmin = x.min()
    xmax = x.max()
    if pd.isna(xmin) or pd.isna(xmax) or abs(xmax - xmin) < 1e-12:
        return pd.Series(np.zeros(len(x)), index=x.index, dtype=float)
    return (x - xmin) / (xmax - xmin)


def clamp01(s: pd.Series) -> pd.Series:
    return s.clip(lower=0.0, upper=1.0)


def prepare_dataframe(gc_path: str, inst_path: str) -> pd.DataFrame:
    step(f"Loading global clusters: {gc_path}")
    gc = _read_json(gc_path)
    step(f"Loading institutional database: {inst_path}")
    inst = _read_json(inst_path)

    for df, name in ((gc, "global_clusters"), (inst, "institutional_database")):
        if "institution" not in df.columns:
            raise KeyError(f"[{name}] Expected column 'institution' not found")
        if "country" not in df.columns:
            raise KeyError(f"[{name}] Expected column 'country' not found")
        df["institution"] = _norm_key(df["institution"])
        df["country"] = _norm_key(df["country"])

    # Drop empty institutions and invalid/missing countries (match cluster hygiene)
    before = len(gc)
    gc = gc[(gc["institution"] != "") & (gc["country"] != "")].copy()
    step(f"Filtered global_clusters (invalid institution/country): {before} -> {len(gc)} rows")

    # Roster from clusters (already cleaned) + cluster label if present
    keep_cols = ["institution", "country"]
    if "cluster" in gc.columns:
        keep_cols.append("cluster")
    roster = gc[keep_cols].drop_duplicates()

    # Deduplicate institutional DB on key; keep first occurrence
    inst_use = inst.drop_duplicates(subset=["institution", "country"], keep="first")

    # Bring region if present; else derive from country
    if "region" not in inst_use.columns:
        step("No 'region' column found in institutional_database; deriving from country...")
        inst_use["region"] = inst_use["country"].apply(_country_to_region)
    else:
        step("'region' found in institutional_database; will carry through.")

    # Join metrics
    df = roster.merge(inst_use, on=["institution", "country"], how="left", suffixes=("", "_inst"))
    step(f"Joined roster + metrics: {len(df)} rows")

    # Defaults for numerics
    num_defaults = {
        "publications": 0.0,
        "journal_publications": 0.0,
        "paid_articles": 0.0,
        "oa_percentage": 0.0,
        "leadership_percentage": 0.0,
        "months_since_last_pub": 60.0,
        "growth_rate": 0.0,
        "consecutive_years": 0.0,
        "apc_total_euro": 0.0,
    }
    for col, default in num_defaults.items():
        if col not in df.columns:
            df[col] = default
        df[col] = df[col].fillna(default)

    if "in_open_apc_institution" not in df.columns:
        df["in_open_apc_institution"] = False
    df["in_open_apc_institution"] = df["in_open_apc_institution"].fillna(False).astype(bool)

    # Safety: floor nonnegative for core numerics
    nonneg_cols = [
        "publications",
        "journal_publications",
        "paid_articles",
        "oa_percentage",
        "leadership_percentage",
        "months_since_last_pub",
        "consecutive_years",
        "apc_total_euro",
    ]
    for col in nonneg_cols:
        df[col] = df[col].clip(lower=0.0)

    # Clamp percents to [0,1]; if many values >1, assume 0..100 scale and downscale
    for frac_col in ["oa_percentage", "leadership_percentage"]:
        frac = df[frac_col].copy()
        if (frac > 1).mean() > 0.2:
            frac = frac / 100.0
        df[frac_col] = clamp01(frac)

    # Ensure region exists post-merge (in case it was only in clusters)
    if "region" not in df.columns:
        df["region"] = df["country"].apply(_country_to_region)

    return df


def winsorize_and_log(out: pd.DataFrame, cols):
    for col in cols:
        out[col] = winsorize_series(out[col])
        out[f"log1p_{col}"] = np.log1p(out[col])
    return out


def compute_components_and_score(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    # RAW copies for debug/output
    out["publications_raw"] = out["publications"]
    out["journal_publications_raw"] = out["journal_publications"]
    out["paid_articles_raw"] = out["paid_articles"]
    out["apc_total_euro_raw"] = out["apc_total_euro"]

    # Winsorize + log1p
    out = winsorize_and_log(out, ["publications", "journal_publications", "paid_articles", "apc_total_euro"])

    # Components
    c1 = minmax(out["log1p_journal_publications"])
    c2 = 1.0 - (out["months_since_last_pub"].clip(0, 48) / 48.0)
    c3 = clamp01(out["leadership_percentage"])
    commitment = (c1 + c2 + c3) / 3.0

    e1 = minmax(out["log1p_publications"])
    denom = out["publications"].where(out["publications"] > 0, 1.0)
    e2 = clamp01(out["journal_publications"] / denom)
    ecosystem = (e1 + e2) / 2.0

    m1 = out["growth_rate"].copy()
    m1 = m1.where(m1 > 0, 0.0)
    m1 = minmax(winsorize_series(m1))
    m2 = out["consecutive_years"].copy()
    m2 = minmax(winsorize_series(m2))
    momentum = (m1 + m2) / 2.0

    o_openapc = out["in_open_apc_institution"].astype(float)
    o_paid = minmax(out["log1p_paid_articles"])
    o_oa = clamp01(out["oa_percentage"])
    apc_propensity = 0.6 * o_paid + 0.4 * o_oa
    open_component = np.maximum(o_openapc, apc_propensity)

    score_0_1 = 0.40 * commitment + 0.20 * ecosystem + 0.20 * momentum + 0.20 * open_component
    lead_score = np.round(100.0 * score_0_1, 0).astype(int)

    out["Commitment"] = commitment
    out["Ecosystem"] = ecosystem
    out["Momentum"] = momentum
    out["Open"] = open_component
    out["Lead Score"] = lead_score

    return out


def assign_tiers(df: pd.DataFrame, mode: str = "percentile", high_cutoff: int = 70, med_cutoff: int = 45) -> pd.Series:
    if mode == "fixed":
        def tier_fn_fixed(x):
            if x >= high_cutoff:
                return "High"
            elif x >= med_cutoff:
                return "Medium"
            else:
                return "Low"
        return df["Lead Score"].apply(tier_fn_fixed)

    p75 = np.nanpercentile(df["Lead Score"], 75)
    p40 = np.nanpercentile(df["Lead Score"], 40)
    def tier_fn_pct(x):
        if x >= p75:
            return "High"
        elif x >= p40:
            return "Medium"
        else:
            return "Low"
    return df["Lead Score"].apply(tier_fn_pct)


def compute_suggestion(df: pd.DataFrame) -> pd.Series:
    # Percentile for paid_articles (Open signal)
    paid_p60 = np.nanpercentile(df["paid_articles"], 60)

    # TA: high volume AND (low OA OR OpenAPC OR high paid_articles)
    is_ta = (
        (df["journal_publications"] >= 10) &
        (
            (df["oa_percentage"] < 0.5) |
            (df["in_open_apc_institution"]) |
            (df["paid_articles"] >= paid_p60)
        )
    )

    # Waiver: modest volume, OA-friendly, low paid_articles, not in OpenAPC
    is_waiver = (
        (df["journal_publications"] >= 1) & (df["journal_publications"] < 10) &
        (df["oa_percentage"] >= 0.4) &
        (~df["in_open_apc_institution"]) &
        (df["paid_articles"] < paid_p60)
    )

    return np.where(is_ta, "TA", np.where(is_waiver, "Waiver", "Other"))


def main():
    parser = argparse.ArgumentParser(description="Generate journal-specific institutional leads (interactive, base_issn-aware).")
    parser.add_argument("--tier-mode", choices=["percentile", "fixed"], default="percentile", help="Tiering strategy. Default: percentile")
    parser.add_argument("--high-cutoff", type=int, default=70, help="High tier cutoff for fixed mode (Lead Score). Default: 70")
    parser.add_argument("--medium-cutoff", type=int, default=45, help="Medium tier cutoff for fixed mode (Lead Score). Default: 45")
    parser.add_argument("--debug", action="store_true", help="Append component scores and raw (uncapped) values to output JSON")
    args = parser.parse_args()

    base_issn = input("Enter base ISSN (e.g. 2296-987X): ").strip()
    step(f"ISSN received: {base_issn}")
    base_dir = os.path.join(ROOT, base_issn)
    clusters_path = os.path.join(base_dir, "global_clusters.json")
    inst_path = os.path.join(base_dir, "institutional_database.json")
    out_path = os.path.join(base_dir, "institutional_leads.json")
    step(f"Resolved paths:\\n  clusters={clusters_path}\\n  inst={inst_path}\\n  out={out_path}")

    df0 = prepare_dataframe(clusters_path, inst_path)
    step("Scoring institutions...")
    df = compute_components_and_score(df0)

    step("Assigning tiers...")
    df["Tier"] = assign_tiers(df, mode=args.tier_mode, high_cutoff=args.high_cutoff, med_cutoff=args.medium_cutoff)

    step("Suggesting agreement types...")
    df["Agreement Suggestion"] = compute_suggestion(df)

    step("Setting APC Confidence...")
    paid_p60 = np.nanpercentile(df["paid_articles"], 60)
    apc_conf_high = df["in_open_apc_institution"] | (df["paid_articles"] >= paid_p60)
    df["APC Confidence"] = np.where(apc_conf_high, "High", "Low")

    # Extra safety: drop blank institutions from output
    df = df[df["institution"].astype(str).str.strip() != ""]

    base_cols = [
        "institution", "country", "region",
        "cluster" if "cluster" in df.columns else None,
        "publications", "journal_publications", "paid_articles",
        "oa_percentage", "in_open_apc_institution", "apc_total_euro",
        "Lead Score", "Tier", "Agreement Suggestion", "APC Confidence",
    ]
    base_cols = [c for c in base_cols if c and c in df.columns]

    debug_cols = [
        "Commitment", "Ecosystem", "Momentum", "Open",
        "publications_raw", "journal_publications_raw", "paid_articles_raw", "apc_total_euro_raw",
    ] if args.debug else []

    display_cols = base_cols + [c for c in debug_cols if c in df.columns]
    df_out = df[display_cols].sort_values(["Tier", "Lead Score"], ascending=[True, False])

    os.makedirs(base_dir, exist_ok=True)
    step("Writing JSON output...")
    df_out.to_json(out_path, orient="records", force_ascii=False)
    step(f"Done. Wrote {len(df_out):,} rows to {out_path}\\n")

    print("=== DataFrame.info() ===")
    buf = io.StringIO()
    df_out.info(buf=buf)
    print(buf.getvalue())

    print("\\n=== DataFrame.head() ===")
    print(df_out.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
