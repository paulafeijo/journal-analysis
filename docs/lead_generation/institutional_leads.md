Awesome—since you already generate (1) a rich, author-level “final” dataset and (2) a region-aware clustering dataset, you’re 90% of the way there. Below is a practical way to turn those into institutional leads plus a compact, reproducible way to score and validate them.

I’ll give you a single, ready‑to‑run script that:

1. builds an institution table from your final_database.json
2. merges in your region_cluster.json
3. computes a transparent lead score per institution
4. outputs ranked leads
5. runs a few quality checks (offline evaluation) automatically, including a time‑based backtest if your data has a year column.


## What makes a good “institutional lead” here?
Heuristics that usually map well to “high potential to publish with us soon”:

- Research intensity: more unique DOIs from the institution in your field (publications)
- Openness fit: higher share of non-hybrid OA output (oa_percentage)
- Leadership footprint: higher share of first/last authorships (leadership_percentage)
- White‑space: fewer publications in your target journal so far (journal_publications → lower is better for new leads)
- Impact proxy (optional, from your final DB): higher average citations per DOI (mean_cites)

We combine those—with region‑local scaling and a modest cluster boost—into one lead_score.

## How to use it
1. Run your existing pipeline to create:
    - data_fetching/data/<ISSN>/final_database.json (from your generating_final_db.py)
    - data_fetching/data/<ISSN>/region_cluster.json (from your clustering.py)

2. Run:
    ```
    python generate_and_evaluate_leads.py <ISSN>
    ```

3. You’ll get:
    - institution_leads.csv (easy to inspect and share)
    - institution_leads.json (for downstream apps)
    - Console quality checks:
        - correlation between score and research intensity (sanity)
        - Precision@K using “already published in base journal” as a weak fit proxy
        - If your data has year, a temporal backtest reporting Precision@K for actual future publications in your journal (stronger signal)


## Interpreting lead quality
- Precision@K (existing in base journal): Higher means your score is surfacing institutions already “aligned” with the journal’s scope—useful as a sanity check, but not the full story (they might be existing customers rather than new).
- Temporal Precision@K (if year is present): This is gold—it tells you how often yesterday’s top leads actually published with you next year. Use this to tune weights.
- Manual sampling: Take the top ~50, browse their lab pages, recent grants, and OA mandates—expect most to be a good narrative fit (e.g., right subfields, publishing volume, rising leaders).
- Outreach A/B: Split top‑N by score deciles and track response/conversion rates. If higher deciles convert better, your score is doing its job.

## Tuning tips
- Adjust WEIGHTS to your business goals:
    - Want new accounts? Increase journal_gap weight and cap ranks where journal_publications == 0.
    - Prefer high‑visibility articles? Increase mean_cites.
    - OA push? Increase oa_percentage.
- Add region‑specific weights if needed: different markets respond differently.
- Consider contact enrichments:
    - If your final DB has email or corresponding author signals, aggregate the most frequent domains per institution and output 2–3 “best bet” contacts.
    - If not, export the top 3 most prolific authors per institution for manual lookup.

    