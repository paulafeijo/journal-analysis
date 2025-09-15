#!/usr/bin/env python3
"""
build_institution_db.py

PART 1 (ready): Load all rows from enriched_final_db.json (JSON Lines) into a pandas DataFrame,
ENFORCE final dtypes for analysis, print df.info() and df.head(), and calibrate author-role weights.

PART 2 (new): Build the institutional_database DataFrame (one row per institution) following the
agreed schema, using the calibrated weights to allocate "paid_articles", and save to JSONL:
institutional_database.json

Notes:
- Uses PyArrow dtype backend for efficient, nullable types
- Calibration uses constrained optimization (SLSQP, sum-to-1, nonnegative) with APC–affiliation overlap GT
"""

# ============== PART 1 — LOADING + DTYPES + CALIBRATION (UNCHANGED LOGIC) ==============

import sys
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone
import pycountry 

# ---------- Config ----------
CHUNK_SIZE = 200_000
BATCH_SIZE = 5
READ_JSON_KW = {
    "lines": True,
    "dtype_backend": "pyarrow",
    "dtype": "string",
}

def step(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# --- helpers for safe casting ---
TRUE_SET  = {"true", "1", "yes", "y", "t"}
FALSE_SET = {"false", "0", "no", "n", "f"}

def to_boolean_nullable(s: pd.Series) -> pd.Series:
    if s.dtype.name.startswith("bool"):
        return s.astype("boolean")
    sm = (
        s.astype("string")
         .str.strip().str.lower()
         .map(lambda x: True if x in TRUE_SET else (False if x in FALSE_SET else pd.NA))
    )
    return sm.astype("boolean")

def enforce_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    # ---- timestamp ----
    if "published_date" in df.columns:
        df["published_date"] = pd.to_datetime(df["published_date"], errors="coerce", utc=True)
        try:
            df["published_date"] = df["published_date"].astype("timestamp[ns][pyarrow]")
        except Exception:
            pass
    # ---- integers ----
    for col, tgt in [("cites", "Int32[pyarrow]"),
                     ("referenced", "Int32[pyarrow]"),
                     ("period", "Int16[pyarrow]")]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            try:
                df[col] = df[col].astype(tgt)
            except Exception:
                df[col] = df[col].astype(tgt.replace("[pyarrow]", ""))
    # ---- float (money analytics) ----
    if "euro" in df.columns:
        df["euro"] = pd.to_numeric(df["euro"], errors="coerce")
        try:
            df["euro"] = df["euro"].astype("Float32[pyarrow]")
        except Exception:
            df["euro"] = df["euro"].astype("Float32")
    # ---- booleans ----
    if "is_hybrid" in df.columns:
        df["is_hybrid"] = to_boolean_nullable(df["is_hybrid"])
    if "in_open_apc" in df.columns:
        df["in_open_apc"] = (
            df["in_open_apc"].astype("string").str.strip().str.lower()
              .map({"yes": True, "no": False})
              .astype("boolean")
        )
    # ---- journal_author: autodetect flag vs text ----
    if "journal_author" in df.columns:
        sample = df["journal_author"].astype("string").str.strip().str.lower()
        looks_flag = sample.isin(TRUE_SET.union(FALSE_SET)).mean() > 0.9
        if looks_flag:
            df["journal_author"] = to_boolean_nullable(df["journal_author"])
        else:
            df["journal_author"] = df["journal_author"].astype("string[pyarrow]")
    # ---- categoricals ----
    for col in ["oa_status", "type", "country", "region", "journal",
                "publisher", "author_position", "institution_country"]:
        if col in df.columns:
            df[col] = df[col].astype("string").astype("category")
    # ---- strings (identifiers / free text) ----
    for col in ["doi", "issn", "author_name", "orcid", "affiliation",
                "author_id", "source_issn", "institution_full_name"]:
        if col in df.columns:
            try:
                df[col] = df[col].astype("string[pyarrow]")
            except Exception:
                df[col] = df[col].astype("string")
    try:
        df = df.convert_dtypes(dtype_backend="pyarrow")
    except Exception:
        df = df.convert_dtypes()
    return df

# ===============================
# Calibration function — returns (F_hat, M_hat, L_hat)
# ===============================
def run_calibration(df: pd.DataFrame):
    import re
    from collections import defaultdict

    step("Starting calibration (GT = overlap between affiliations and OpenAPC institutions)...")

    req_cols = ["doi", "affiliation", "author_position", "institution_full_name", "in_open_apc"]
    missing = [c for c in req_cols if c not in df.columns]
    if missing:
        step(f"WARNING: Missing columns for calibration: {missing}. Skipping calibration.")
        return None

    apc_mask = df["in_open_apc"].fillna(False)
    apc_dois = df.loc[apc_mask, "doi"].dropna().unique().tolist()
    step(f"APC-covered DOIs in dataset: {len(apc_dois):,}")
    if not apc_dois:
        step("No APC-covered DOIs found; skipping calibration.")
        return None

    def norm_name(s: str) -> str:
        if pd.isna(s):
            return ""
        s = str(s).lower().strip()
        s = re.sub(r"\s+", " ", s)
        s = re.sub(r"[.,;:()\[\]{}‘’'“”\"/\\|·\-]+", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    doi_groups = df.groupby("doi", observed=True, sort=False)
    role_insts, gt_payers, usable_dois = {}, {}, []

    for doi in apc_dois:
        g = doi_groups.get_group(doi)
        ap = g["author_position"].astype("string").str.strip().str.lower()
        aff_norm = g["affiliation"].map(norm_name).fillna("")

        first_set  = set(aff_norm[ap == "first"].dropna().replace("", pd.NA).dropna().unique())
        middle_set = set(aff_norm[ap == "middle"].dropna().replace("", pd.NA).dropna().unique())
        last_set   = set(aff_norm[ap == "last"].dropna().replace("", pd.NA).dropna().unique())

        role_insts[doi] = {
            "first":  {i for i in first_set if i},
            "middle": {i for i in middle_set if i},
            "last":   {i for i in last_set if i},
        }

        g_apc = g[g["in_open_apc"].fillna(False)]
        apc_insts = set(
            g_apc["institution_full_name"].dropna().astype(str)
                .map(norm_name).replace("", pd.NA).dropna().unique()
        )

        aff_all = role_insts[doi]["first"] | role_insts[doi]["middle"] | role_insts[doi]["last"]
        overlap = apc_insts & aff_all
        if overlap:
            gt_payers[doi] = overlap
            usable_dois.append(doi)

    step(f"Usable DOIs for calibration (with APC–affiliation overlap): {len(usable_dois):,}")
    if not usable_dois:
        step("No DOIs with APC–affiliation overlap. Skipping calibration.")
        return None

    from collections import defaultdict as _dd
    def loglik(F: float, M: float) -> float:
        L = 1.0 - F - M
        if F < 0 or M < 0 or L < 0:
            return -np.inf
        ll, any_used = 0.0, False
        for doi in usable_dois:
            roles = role_insts[doi]
            nF, nM, nL = len(roles["first"]), len(roles["middle"]), len(roles["last"])
            p = _dd(float)
            if nF and F > 0: p.update({inst: p.get(inst,0.0) + F/nF for inst in roles["first"]})
            if nM and M > 0: p.update({inst: p.get(inst,0.0) + M/nM for inst in roles["middle"]})
            if nL and L > 0: p.update({inst: p.get(inst,0.0) + L/nL for inst in roles["last"]})
            if not p: continue
            s = sum(p.values()); 
            if s: 
                for k in list(p.keys()): p[k] /= s
            gt = gt_payers.get(doi, set())
            if not gt: continue
            p_gt = sum(p.get(inst, 0.0) for inst in gt)
            ll += (-1e6 if p_gt <= 0 else np.log(p_gt))
            any_used = True
        return ll if any_used else -np.inf

    estimated = None
    try:
        from scipy.optimize import minimize
        def objective(x): return -loglik(x[0], x[1])
        cons = (
            {"type": "ineq", "fun": lambda x: x[0]},               # F >= 0
            {"type": "ineq", "fun": lambda x: x[1]},               # M >= 0
            {"type": "ineq", "fun": lambda x: 1.0 - x[0] - x[1]},  # L >= 0
        )
        res = minimize(objective, x0=np.array([0.45, 0.10]), method="SLSQP",
                       bounds=[(0,1),(0,1)], constraints=cons, options={"maxiter": 500})
        if res.success:
            F_hat, M_hat = res.x
            L_hat = 1.0 - F_hat - M_hat
            estimated = (float(F_hat), float(M_hat), float(L_hat))
        else:
            step(f"Optimization did not converge: {res.message}")
    except Exception as e:
        step(f"scipy.optimize not available or failed ({e}). Falling back to grid search.")
        best_ll, best_tuple = -np.inf, None
        for F in [0.30, 0.35, 0.40, 0.45, 0.50, 0.55]:
            for M in [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]:
                L = 1.0 - F - M
                if L < 0: continue
                ll = loglik(F, M)
                if ll > best_ll:
                    best_ll, best_tuple = ll, (F, M, L)
        estimated = best_tuple

    if estimated is None:
        step("Calibration: no weights estimated.")
        return None

    # Report performance with estimated weights
    def predict_ranked(doi, F, M, L):
        roles = role_insts.get(doi); 
        if not roles: return []
        w = _dd(float)
        if roles["first"] and F>0:  [w.__setitem__(inst, w.get(inst,0)+F/len(roles["first"]))  for inst in roles["first"]]
        if roles["middle"] and M>0: [w.__setitem__(inst, w.get(inst,0)+M/len(roles["middle"])) for inst in roles["middle"]]
        if roles["last"] and L>0:   [w.__setitem__(inst, w.get(inst,0)+L/len(roles["last"]))   for inst in roles["last"]]
        if not w: return []
        s=sum(w.values()); 
        if s: 
            for k in list(w.keys()): w[k]/=s
        return [k for k,_ in sorted(w.items(), key=lambda kv:(-kv[1],kv[0]))]

    F_hat, M_hat, L_hat = estimated
    top1=top3=0
    for doi in usable_dois:
        gt = gt_payers.get(doi,set()); ranked = predict_ranked(doi,F_hat,M_hat,L_hat)
        if not ranked or not gt: continue
        if ranked[0] in gt: top1 += 1
        if any(inst in gt for inst in ranked[:3]): top3 += 1
    total = len(usable_dois)
    print("\n[Calibration Summary — Affiliation/APC overlap GT]")
    print(f"Estimated weights (sum=1): F={F_hat:.4f}  M={M_hat:.4f}  L={L_hat:.4f}")
    print(f"Top-1 acc: {top1/total:.3f}  Top-3 acc: {top3/total:.3f}  (on {total} usable DOIs)")
    return (F_hat, M_hat, L_hat)

# ============== PART 2 — INSTITUTIONAL DATABASE BUILDER (NEW) ==============


# === Region classification ===
REGION_MAP = {
    "Europe (OpenAPC strong)": [
        "DE","GB","FR","IT","ES","NL","SE","FI","NO","DK","AT","BE","CH","IE",
        "PL","CZ","PT","GR","HU","SI","SK","EE","LV","LT","RO","BG","HR","LU","IS"
    ],
    "US & Canada": ["US","CA"],
    "China": ["CN"],  # Optionally add "HK","MO"
    "Latin America": [
        "BR","MX","AR","CL","CO","PE","UY","VE","CR","EC","PA","BO","PY",
        "SV","GT","HN","NI","DO","PR"
    ],
    "Asia-Pacific (ex-China)": ["JP","KR","IN","SG","AU","NZ","TW","TH","VN","MY","ID","PH"],
    "Middle East & Africa": [
        "IL","SA","AE","QA","KW","OM","EG","ZA","MA","TN","KE","NG","GH","ET"
    ],
    "Other": []
}

# Reverse-lookup for faster mapping
COUNTRY_TO_REGION = {
    country: region
    for region, countries in REGION_MAP.items()
    for country in countries
}

def map_region_from_country(code: str) -> str:
    if code is None or pd.isna(code):
        return pd.NA
    code = str(code).strip().upper()
    return COUNTRY_TO_REGION.get(code, "Other")

def mode_or_first(series: pd.Series):
    """Return the most frequent non-null value; fallback to first non-null; else NA."""
    s = series.dropna()
    if s.empty:
        return pd.NA
    try:
        return s.mode(dropna=True).iloc[0]
    except Exception:
        return s.iloc[0]
    
def name_to_iso2(name: str) -> str:
    if not name or pd.isna(name):
        return None
    try:
        return pycountry.countries.lookup(str(name)).alpha_2
    except Exception:
        return None

def months_between(a: pd.Timestamp, b: pd.Timestamp) -> int:
    """Full months between two dates (a >= b)."""
    return int((a.year*12 + a.month) - (b.year*12 + b.month))

def build_institutional_database(df: pd.DataFrame, base_issn: str, weights: tuple[float,float,float]) -> pd.DataFrame:
    """
    Build the institutional dataframe per the agreed schema.
    - Allocates 'paid_articles' using APC payer (1.0) or inferred weights (F,M,L) per DOI, normalized to sum=1.
    - Computes all other columns as defined.
    """
    step("Building institutional_database...")

    # ---------- Common helpers ----------
    # Current-year reference: Jan 1 of current year (UTC)
    current_year = datetime.now(timezone.utc).year
    ref_date = pd.Timestamp(year=current_year, month=1, day=1, tz="UTC")

    # OA classifier: exclude 'closed' and 'hybrid'
    def is_oa_label(x: str) -> bool:
        if x is None or pd.isna(x):
            return False
        x = str(x).strip().lower()
        return x not in {"closed", "hybrid", "none", ""}

    # Precompute DOI-level meta -----------------------
    step("Preparing DOI-level metadata...")
    doi_meta = (df
        .groupby("doi", observed=True)
        .agg(
            published_date=("published_date", "max"),
            year=("published_date", lambda s: pd.to_datetime(s, errors="coerce", utc=True).dt.year.max()),
            issn_any=("issn", lambda s: mode_or_first(s.astype("string"))),
            is_oa=("oa_status", lambda s: bool(is_oa_label(mode_or_first(s))))
        )
        .reset_index()
    )
    doi_meta["year"] = pd.to_numeric(doi_meta["year"], errors="coerce").astype("Int16")
    doi_meta["in_target_journal"] = doi_meta["issn_any"].astype("string").str.strip().eq(str(base_issn))

    # Map for quick lookup
    doi_to_year = pd.Series(doi_meta["year"].values, index=doi_meta["doi"]).to_dict()
    doi_to_is_oa = pd.Series(doi_meta["is_oa"].values, index=doi_meta["doi"]).to_dict()
    doi_to_in_target = pd.Series(doi_meta["in_target_journal"].values, index=doi_meta["doi"]).to_dict()
    doi_to_pubdate = pd.Series(doi_meta["published_date"].values, index=doi_meta["doi"]).to_dict()

    # ---------- STEP A: Build per-DOI institution assignments with paid weights ----------
    step("Allocating paid_articles per DOI (APC vs inferred)...")
    F, M, L = weights if weights is not None else (0.40, 0.20, 0.40)

    assign_rows = []  # rows: institution, doi, paid_weight, is_apc, euro_inst, is_hybrid, publisher, country, region
    doi_groups = df.groupby("doi", observed=True, sort=False)

    for doi, g in doi_groups:
        in_apc = bool(g["in_open_apc"].fillna(False).any())
        year = doi_to_year.get(doi, pd.NA)
        issn_set = g["issn"].dropna().astype(str).unique().tolist()

        if in_apc:
            # ------- APC DOI: allocate 1.0 "paid_articles" to APC payer institutions --------
            g_apc = g[g["in_open_apc"].fillna(False)]
            # sum euro per payer (if euro missing, fall back to equal split)
            euro_per_inst = (g_apc
                .dropna(subset=["institution_full_name"])
                .groupby("institution_full_name", dropna=True)["euro"]
                .sum(min_count=1)
            )
            unique_insts = euro_per_inst.index.astype("string").tolist() if len(euro_per_inst) else \
                           g_apc["institution_full_name"].dropna().astype("string").unique().tolist()

            if not unique_insts:
                continue  # no payer institution name, skip DOI

            total_euro = float(euro_per_inst.sum()) if len(euro_per_inst) else 0.0
            # Use euro share if available; else equal split
            weights_apc = {}
            if total_euro > 0:
                for inst, euro_val in euro_per_inst.items():
                    weights_apc[str(inst)] = float(euro_val) / total_euro
            else:
                split = 1.0 / len(unique_insts)
                weights_apc = {str(inst): split for inst in unique_insts}

            for inst, w in weights_apc.items():
                # Country/region for APC institution (row-level)
                row_apc = g_apc[g_apc["institution_full_name"].astype("string") == inst]
                country_name = mode_or_first(row_apc["institution_country"].astype("string"))
                inst_country_code = name_to_iso2(country_name)  # convert full name → ISO2
                inst_region = map_region_from_country(inst_country_code)

                is_hyb = bool(row_apc["is_hybrid"].fillna(False).any())
                publisher = mode_or_first(row_apc["publisher"].astype("string"))
                euro_inst = float(row_apc["euro"].sum(skipna=True)) if "euro" in row_apc else 0.0

                assign_rows.append({
                    "institution": inst,
                    "doi": doi,
                    "paid_weight": float(w),             # ---- (Schema) paid_articles (APC path) ----
                    "is_apc": True,
                    "euro_inst": euro_inst,              # used for APC spend metrics
                    "is_hybrid_apc": is_hyb,
                    "publisher_apc": publisher,
                    "inst_country": inst_country_code,      # ---- (Schema) country (APC path) ----
                    "inst_region": inst_region,          # ---- (Schema) region (APC path) ----
                    "issn_any": mode_or_first(pd.Series(issn_set, dtype="string")),
                    "year": year,
                    "published_date": doi_to_pubdate.get(doi, pd.NaT),
                    "in_target_journal": bool(doi_to_in_target.get(doi, False)),
                    "is_oa": bool(doi_to_is_oa.get(doi, False)),
                    "period": mode_or_first(g_apc["period"])
                })

        else:
            # ------- Non-APC DOI: allocate weights by roles (First/Middle/Last), normalized to sum=1 -------
            g_roles = g.copy()
            ap = g_roles["author_position"].astype("string").str.strip().str.lower()

            # Build unique institution sets by role
            first_insts  = set(g_roles.loc[ap=="first",  "affiliation"].astype("string").dropna().unique())
            middle_insts = set(g_roles.loc[ap=="middle", "affiliation"].astype("string").dropna().unique())
            last_insts   = set(g_roles.loc[ap=="last",   "affiliation"].astype("string").dropna().unique())

            # Distribute role pools equally among institutions in that role
            weights_non = {}
            if first_insts and F>0:
                share = F / len(first_insts)
                for inst in first_insts:  weights_non[str(inst)] = weights_non.get(str(inst),0.0) + share
            if middle_insts and M>0:
                share = M / len(middle_insts)
                for inst in middle_insts: weights_non[str(inst)] = weights_non.get(str(inst),0.0) + share
            if last_insts and L>0:
                share = L / len(last_insts)
                for inst in last_insts:   weights_non[str(inst)] = weights_non.get(str(inst),0.0) + share

            if not weights_non:
                continue

            # Normalize so total per DOI = 1.0
            s = sum(weights_non.values())
            if s > 0:
                for k in list(weights_non.keys()):
                    weights_non[k] /= s

            # Attach a row for each institution with country/region from affiliation rows
            for inst, w in weights_non.items():
                rows_inst = g_roles[g_roles["affiliation"].astype("string") == inst]
                inst_country = mode_or_first(rows_inst["country"].astype("string"))   # ---- (Schema) country (non-APC path) ----
                inst_region  = mode_or_first(rows_inst["region"].astype("string"))    # ---- (Schema) region (non-APC path) ----

                assign_rows.append({
                    "institution": inst,
                    "doi": doi,
                    "paid_weight": float(w),            # ---- (Schema) paid_articles (non-APC path) ----
                    "is_apc": False,
                    "euro_inst": 0.0,
                    "is_hybrid_apc": False,
                    "publisher_apc": pd.NA,
                    "inst_country": inst_country,
                    "inst_region": inst_region,
                    "issn_any": mode_or_first(pd.Series(issn_set, dtype="string")),
                    "year": year,
                    "published_date": doi_to_pubdate.get(doi, pd.NaT),
                    "in_target_journal": bool(doi_to_in_target.get(doi, False)),
                    "is_oa": bool(doi_to_is_oa.get(doi, False)),
                    "period": mode_or_first(g_roles["period"])
                })

    assignments = pd.DataFrame(assign_rows)
    step(f"Assignments built: {len(assignments):,} institution–DOI rows")

    if assignments.empty:
        step("No assignments to aggregate. Returning empty institutional database.")
        return pd.DataFrame()

    # ---------- STEP B: Aggregate to institution-level columns ----------
    step("Aggregating to institution-level...")

    g = assignments.groupby("institution", observed=True)

    # (1) institution — index preserved by groupby
    inst = pd.DataFrame({"institution": g.size().index.astype("string")})
    # --- FIX: align grouped series by institution index ---
    inst = inst.set_index("institution", drop=False)
    # --- END FIX ---

    # (2) paid_articles — sum of paid_weight
    inst["paid_articles"] = g["paid_weight"].sum(min_count=1).astype("Float32")

    # (3) country — mode of inst_country
    inst["country"] = g["inst_country"].agg(mode_or_first).astype("string")

    # (4) region — mode of inst_region
    inst["region"] = g["inst_region"].agg(mode_or_first).astype("string")

    # (5) publications — unique DOIs count
    inst["publications"] = g["doi"].nunique().astype("Int32")

    # (6) oa_percentage — share OA among institution DOIs
    inst["oa_percentage"] = (g["is_oa"].mean()).astype("Float32")

    # (7) leadership_percentage — from original df authorships (affiliation scope only)
    step("Computing leadership_percentage from authorships...")
    if "author_position" in df.columns and "affiliation" in df.columns:
        df_aff = df[["affiliation","author_position"]].dropna(subset=["affiliation"]).copy()
        df_aff["affiliation"] = df_aff["affiliation"].astype("string")
        df_aff["is_lead"] = df_aff["author_position"].astype("string").str.strip().str.lower().isin({"first","last"})
        grp_aff = df_aff.groupby("affiliation", observed=True)
        lead_ratio = (grp_aff["is_lead"].mean()).astype("Float32")
        inst["leadership_percentage"] = inst["institution"].map(lead_ratio).astype("Float32")
    else:
        inst["leadership_percentage"] = pd.NA

    # (8) journal_publications — DOIs in target journal
    inst["journal_publications"] = g.apply(lambda x: x.loc[x["in_target_journal"], "doi"].nunique()).astype("Int32")

    # (9) months_since_last_pub — ref = Jan 1 current_year
    last_pub = g["published_date"].max()
    # coerce to UTC timestamps
    last_pub = pd.to_datetime(last_pub, errors="coerce", utc=True)
    inst["months_since_last_pub"] = last_pub.map(lambda d: months_between(ref_date, d) if pd.notna(d) else pd.NA).astype("Int32")

    # (10) growth_rate — slope of yearly publication counts, excluding current_year
    def slope_counts(years: pd.Series) -> float:
        ys = pd.to_numeric(years, errors="coerce").dropna().astype(int)
        ys = ys[ys < current_year]
        if ys.empty:
            return np.nan
        counts = ys.value_counts().sort_index()
        if len(counts) < 2:
            return np.nan
        x = counts.index.to_numpy(dtype=float)   # use actual years
        y = counts.to_numpy(dtype=float)
        try:
            return float(np.polyfit(x, y, 1)[0])
        except Exception:
            return np.nan
    inst["growth_rate"] = g["published_date"].apply(lambda s: slope_counts(pd.to_datetime(s, errors="coerce", utc=True).dt.year)).astype("Float32")

    # (11) consecutive_years — longest run of consecutive years with ≥1 pub
    def longest_streak(years: pd.Series) -> int:
        ys = np.sort(pd.to_numeric(years, errors="coerce").dropna().astype(int).unique())
        if ys.size == 0:
            return 0
        best = cur = 1
        for i in range(1, ys.size):
            if ys[i] == ys[i-1] + 1:
                cur += 1; best = max(best, cur)
            else:
                cur = 1
        return int(best)
    inst["consecutive_years"] = g["year"].apply(longest_streak).astype("Int16")

    # (12) hhi_journal — HHI over ISSN shares by publication count
    def hhi_counts(issn: pd.Series) -> float:
        s = issn.dropna().astype("string")
        if s.empty:
            return np.nan
        counts = s.value_counts(dropna=True)
        shares = counts / counts.sum()
        return float((shares**2).sum())
    inst["hhi_journal"] = g["issn_any"].apply(hhi_counts).astype("Float32")

    # (13) in_open_apc_institution — any APC assignment?
    inst["in_open_apc_institution"] = g["is_apc"].any().astype("boolean")

    # APC-only aggregations (computed on APC assignment rows)
    apc_only = assignments[assignments["is_apc"] == True]
    g_apc = apc_only.groupby("institution", observed=True) if not apc_only.empty else None

    # (14) apc_total_euro — sum euro where institution is payer
    inst["apc_total_euro"] = (g_apc["euro_inst"].sum(min_count=1) if g_apc else pd.Series(dtype="float")).reindex(inst.index).to_numpy()
    inst["apc_total_euro"] = pd.Series(inst["apc_total_euro"]).astype("Float32")

    # (15) apc_publications — unique APC DOIs per institution
    inst["apc_publications"] = (g_apc["doi"].nunique() if g_apc else pd.Series(dtype="Int32")).reindex(inst.index).to_numpy()
    inst["apc_publications"] = pd.Series(inst["apc_publications"]).astype("Int32")

    # (16) apc_hybrid_share — mean of is_hybrid among APC DOIs
    def safe_mean_bool(s: pd.Series):
        return float(s.mean()) if len(s) else np.nan
    inst["apc_hybrid_share"] = (g_apc["is_hybrid_apc"].apply(safe_mean_bool) if g_apc else pd.Series(dtype="float")).reindex(inst.index).to_numpy()
    inst["apc_hybrid_share"] = pd.Series(inst["apc_hybrid_share"]).astype("Float32")

    # (17) apc_main_journal_share — euro share in target journal
    def euro_share_target(group: pd.DataFrame) -> float:
        total = float(group["euro_inst"].sum())
        if total <= 0:
            return np.nan
        in_target = float(group.loc[group["in_target_journal"], "euro_inst"].sum())
        return in_target / total
    inst["apc_main_journal_share"] = (g_apc.apply(euro_share_target) if g_apc else pd.Series(dtype="float")).reindex(inst.index).to_numpy()
    inst["apc_main_journal_share"] = pd.Series(inst["apc_main_journal_share"]).astype("Float32")

    # (18) apc_spend_growth_rate — slope of yearly APC euro, excluding current year
    def slope_apc(group: pd.DataFrame) -> float:
        sub = group.dropna(subset=["period", "euro_inst"]).copy()
        if sub.empty:
            return np.nan
        sub["period"] = pd.to_numeric(sub["period"], errors="coerce").dropna().astype(int)
        sub = sub[sub["period"] < current_year]
        if sub.empty:
            return np.nan
        euro_by_year = sub.groupby("period", as_index=True)["euro_inst"].sum().sort_index()
        if len(euro_by_year) < 2:
            return np.nan
        x = euro_by_year.index.to_numpy(dtype=float)
        y = euro_by_year.to_numpy(dtype=float)
        try:
            return float(np.polyfit(x, y, 1)[0])
        except Exception:
            return np.nan
    inst["apc_spend_growth_rate"] = (g_apc.apply(slope_apc) if g_apc else pd.Series(dtype="float")).reindex(inst.index).to_numpy()
    inst["apc_spend_growth_rate"] = pd.Series(inst["apc_spend_growth_rate"]).astype("Float32")

    # (19) hhi_publisher — HHI over APC spend shares by publisher
    def hhi_spend_publisher(group: pd.DataFrame) -> float:
        sub = group.dropna(subset=["publisher_apc"]).copy()
        if sub.empty:
            return np.nan
        spend = sub.groupby("publisher_apc", dropna=True)["euro_inst"].sum()
        if spend.sum() <= 0:
            return np.nan
        shares = spend / spend.sum()
        return float((shares**2).sum())
    inst["hhi_publisher"] = (g_apc.apply(hhi_spend_publisher) if g_apc else pd.Series(dtype="float")).reindex(inst.index).to_numpy()
    inst["hhi_publisher"] = pd.Series(inst["hhi_publisher"]).astype("Float32")

    # Clean up ordering & types
    cols_order = [
        "institution","country","region",
        "paid_articles","publications","oa_percentage","leadership_percentage","journal_publications",
        "months_since_last_pub","growth_rate","consecutive_years","hhi_journal",
        "in_open_apc_institution","apc_total_euro","apc_publications","apc_hybrid_share",
        "apc_main_journal_share","apc_spend_growth_rate","hhi_publisher"
    ]
    inst = inst[cols_order]
    step(f"institutional_database built with {len(inst):,} institutions.")

    return inst

# ============== MAIN ==============

def main():
    step("Start: asking for ISSN")
    base_issn = input("Enter base ISSN (e.g. 2296-987X): ").strip()
    step(f"ISSN received: {base_issn}")

    base_dir = Path("data_fetching") / "data" / base_issn
    in_path  = base_dir / "enriched_final_db.json"
    out_path = base_dir / "institutional_database.json"

    if not in_path.exists():
        print(f"ERROR: {in_path} not found.", file=sys.stderr)
        sys.exit(1)

    # --- Load in chunks ---
    step(f"Streaming JSON Lines from: {in_path}")
    chunk_iter = pd.read_json(in_path, chunksize=CHUNK_SIZE, **READ_JSON_KW)
    batches, buffer, total_rows, total_chunks = [], [], 0, 0

    try:
        for chunk in chunk_iter:
            total_chunks += 1; total_rows += len(chunk)
            buffer.append(chunk)
            step(f"Read chunk {total_chunks} (+{len(chunk):,} rows) → total {total_rows:,}")
            if len(buffer) >= BATCH_SIZE:
                step(f"Concatenating buffered {len(buffer)} chunks...")
                batches.append(pd.concat(buffer, ignore_index=True, copy=False)); buffer.clear()
        if buffer:
            step(f"Final concat of remaining {len(buffer)} buffered chunks...")
            batches.append(pd.concat(buffer, ignore_index=True, copy=False)); buffer.clear()
        step(f"Concatenating {len(batches)} batch(es) into final DataFrame...")
        df = pd.concat(batches, ignore_index=True, copy=False) if batches else pd.DataFrame()
    except MemoryError:
        print("\nERROR: Ran out of memory while assembling the full DataFrame.", file=sys.stderr)
        print("- Reduce CHUNK_SIZE and/or BATCH_SIZE.", file=sys.stderr)
        print("- Ensure pandas >= 2.0 with pyarrow installed.", file=sys.stderr)
        sys.exit(1)

    step(f"Loaded DataFrame with shape {df.shape}")
    step("Enforcing final dtypes...")
    df = enforce_dtypes(df)

    print("\n[DataFrame Info]")
    print(df.info())
    print("\n[DataFrame Head]")
    print(df.head())

    # --- Calibrate role weights ---
    weights = run_calibration(df)
    if weights is None:
        step("Calibration missing; defaulting to (F=0.40, M=0.20, L=0.40)")
        weights = (0.40, 0.20, 0.40)
    step(f"Using weights: F={weights[0]:.4f}  M={weights[1]:.4f}  L={weights[2]:.4f}")

    # --- Build institutional database ---
    inst_df = build_institutional_database(df, base_issn=base_issn, weights=weights)

    # --- Show institutional dataframe info/head ---
    print("\n[Institutional Database Info]")
    print(inst_df.info())

    print("\n[Institutional Database Head]")
    print(inst_df.head())

    # --- Save to JSONL ---
    if inst_df.empty:
        step("institutional_database is empty; nothing to save.")
    else:
        step(f"Saving institutional_database to: {out_path}")
        # JSON Lines for large dataframes (one object per line)
        inst_df.to_json(out_path, orient="records", lines=True, force_ascii=False)
        step("Saved successfully.")

if __name__ == "__main__":
    main()