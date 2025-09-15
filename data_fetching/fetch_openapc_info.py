#!/usr/bin/env python3
"""
Enrich final_database.json (JSONL) with OpenAPC + institution metadata.

Input (assumed layout):
  data_fetching/data/<ISSN>/final_database.json

Outputs:
  data_fetching/data/<ISSN>/enriched_final_db.json   (JSON Lines)

Side files (adjust paths below if needed):
  apc_de.csv
  institutions.csv
"""

import os
import sys
import numpy as np
import pandas as pd
from typing import Optional

# --- config (edit if your CSVs live elsewhere) ---
APC_CSV_PATH = "open_apc/csv_files/apc_de.csv"
INSTITUTIONS_CSV_PATH = "open_apc/csv_files/institutions.csv"
CHUNK_SIZE = 200_000  # tune for your machine

# --- helpers ---
def norm_doi(doi: Optional[str]) -> str:
    if pd.isna(doi):
        return ""
    s = str(doi).strip().lower()
    for p in ("https://doi.org/", "http://doi.org/",
              "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if s.startswith(p):
            s = s[len(p):]
            break
    return s

def clean_bool_series(s: pd.Series) -> pd.Series:
    return (
        s.astype(str).str.strip().str.lower()
         .map({"true": True, "false": False, "1": True, "0": False})
    )

def load_openapc_tables(apc_path: str, inst_path: str) -> pd.DataFrame:
    # APCs
    apc = pd.read_csv(apc_path, dtype=str)
    if "doi" not in apc.columns:
        raise ValueError("apc_de.csv must contain a 'doi' column.")
    apc["doi_norm"] = apc["doi"].map(norm_doi)
    apc["euro"]   = pd.to_numeric(apc.get("euro"), errors="coerce")
    apc["period"] = pd.to_numeric(apc.get("period"), errors="coerce").astype("Int64")
    if "is_hybrid" in apc.columns:
        apc["is_hybrid"] = clean_bool_series(apc["is_hybrid"])

    needed_apc_cols = ["doi_norm", "institution", "period", "euro", "is_hybrid", "publisher"]
    for col in needed_apc_cols:
        if col not in apc.columns:
            apc[col] = np.nan
    apc = apc[needed_apc_cols]

    # Institutions
    inst = pd.read_csv(inst_path, dtype=str)
    if "institution" not in inst.columns:
        raise ValueError("institutions.csv must contain an 'institution' column.")
    if "country" not in inst.columns:
        inst["country"] = np.nan

    inst_map = inst[["institution", "country"]].drop_duplicates().rename(
        columns={"institution": "institution_full_name",
                 "country": "institution_country"}
    )

    # Enrich APC with institution metadata once
    apc_enriched = apc.merge(
        inst_map,
        left_on="institution",
        right_on="institution_full_name",
        how="left"
    )
    apc_enriched["in_open_apc"] = "yes"  # presence implies "yes"
    return apc_enriched

def main():
    base_issn = input("Enter base ISSN (e.g. 2296-987X): ").strip()
    base_dir = os.path.join("data_fetching", "data", base_issn)
    in_path  = os.path.join(base_dir, "final_database.json")
    out_path = os.path.join(base_dir, "enriched_final_db.json")

    if not os.path.exists(in_path):
        print(f"ERROR: {in_path} not found.", file=sys.stderr); sys.exit(1)
    if not os.path.exists(APC_CSV_PATH):
        print(f"ERROR: {APC_CSV_PATH} not found.", file=sys.stderr); sys.exit(1)
    if not os.path.exists(INSTITUTIONS_CSV_PATH):
        print(f"ERROR: {INSTITUTIONS_CSV_PATH} not found.", file=sys.stderr); sys.exit(1)

    print("Loading OpenAPC tables...")
    apc_enriched = load_openapc_tables(APC_CSV_PATH, INSTITUTIONS_CSV_PATH)

    # Prepare output file
    if os.path.exists(out_path):
        os.remove(out_path)
    print(f"Writing to {out_path} (JSON Lines)...")

    chunk_iter = pd.read_json(in_path, lines=True, dtype=str, chunksize=CHUNK_SIZE)

    total_rows = written_rows = 0
    for chunk_idx, base_chunk in enumerate(chunk_iter, start=1):
        total_rows += len(base_chunk)

        # Find DOI column in this chunk
        doi_col = next((c for c in base_chunk.columns if c.lower() == "doi"), None)
        if doi_col is None:
            doi_col = next((c for c in base_chunk.columns if "doi" in c.lower()), None)

        if doi_col is None:
            # No DOI? Pass-through plus ensure enrichment columns exist (empty)
            for c in ["in_open_apc","period","euro","is_hybrid","publisher",
                      "institution_full_name","institution_country"]:
                if c not in base_chunk.columns:
                    base_chunk[c] = np.nan
            base_chunk.to_json(out_path, orient="records", lines=True, force_ascii=False, mode="a")
            written_rows += len(base_chunk)
            print(f"Chunk {chunk_idx}: no DOI col → pass-through {len(base_chunk):,}")
            continue

        # Normalized DOI for join (drop from output later)
        base_chunk["doi_norm"] = base_chunk[doi_col].astype(str).map(norm_doi)

        # Left join to APC (may multiply rows)
        merged = base_chunk.merge(apc_enriched, on="doi_norm", how="left")

        # Mark non-matches
        merged["in_open_apc"] = merged["in_open_apc"].fillna("no")

        # Ensure enrichment columns exist
        for c in ["period","euro","is_hybrid","publisher",
                  "institution_full_name","institution_country"]:
            if c not in merged.columns:
                merged[c] = np.nan

        # --- DROP helper/raw columns from output ---
        if "doi_norm" in merged.columns:
            merged.drop(columns=["doi_norm"], inplace=True)
        if "institution" in merged.columns:
            merged.drop(columns=["institution"], inplace=True)

        # Append to output (JSONL)
        merged.to_json(out_path, orient="records", lines=True, force_ascii=False, mode="a")
        written_rows += len(merged)
        print(f"Chunk {chunk_idx}: base {len(base_chunk):,} → written {len(merged):,} (cumulative {written_rows:,})")

    print(f"Done. Read {total_rows:,} base rows; wrote {written_rows:,} enriched rows → {out_path}")

if __name__ == "__main__":
    main()
