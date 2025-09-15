# Journal Analysis

A complete **data pipeline** for retrieving, analyzing, and visualizing academic journal metadata — using data from **Crossref** and **OpenAlex**, with a focus on **institutional research trends**, and presented through an interactive **Tableau** dashboard.

> **For detailed documentation, visit the project's wiki:** \
> https://github.com/paulafeijo/journal-analysis/wiki


## Overview

This project is focused on:
- **Collecting** academic metadata from **Crossref** and **OpenAlex** (articles, authors, institutions, citations).
- **Storing** structured raw data in **JSON** format.
- **Enriching** article-level data with **OpenAPC payment and institution metadata**.
- **Aggregating** to the **institution level**, building metrics such as OA percentage, growth rate, APC spend, and concentration indices.
- **Analyzing** institutions using clustering techniques to detect publishing and funding patterns.
- **Generating leads** by scoring and ranking institutions (Commitment, Ecosystem, Momentum, Openness).
- **Visualizing** trends and insights in a **Tableau dashboard** for exploration.

**Goal:** build a model that can **recommend institutions** for strategic partnerships, collaborations, or commercial outreach based on research output, openness, and APC spending.


## Current Features

- Automated retrieval of articles, authors, affiliations, and citation data from **Crossref**, **OpenAlex**, and **OpenCitations**.
- **OpenAPC integration**: enrich article-level data with APC payments and institution metadata.
- **Institutional database builder**: aggregating institution-level metrics (publications, OA share, APC spend, growth, concentration).
- **Clustering analysis**: assign institutions to global research clusters.
- **Lead generation model**: compute Lead Scores (0–100), tiers (High/Medium/Low), and agreement suggestions (TA / Waiver / Other).
- **Tableau dashboard** with:
  - Top institutions by publication volume.
  - Citation and co-authorship networks.
  - Regional and institutional cluster patterns.
  - Ranked institutional leads.


## Tech Stack

| Stage             | Tools/Libraries                                                          |
|-------------------|--------------------------------------------------------------------------|
| Data Fetching     | Python, Requests, Crossref API, OpenAlex API, OpenCitations API          |
| Enrichment        | OpenAPC CSVs, Pandas, NumPy                                              |
| Analysis          | Pandas, NumPy, Scikit-learn (MiniBatchKMeans), HDBSCAN (optional)        |
| Lead Generation   | Pandas, NumPy, domain-specific scoring model                             |
| Visualization     | Tableau Public                                                           |
| Dev Tools         | VSCode, Terminal, GitHub   



## Project Structure

```
journal-analysis/
├── dashboard/
│   └── dashboard.twbx                 # Tableau dashboards
│   └── dashboard-nova.twbx
├── data_analysis/
│   └── institution_database.py        # Build institution-level dataset
│   └── cluster.py                     # Cluster analysis script
│   └── generate_leads.py              # Lead generation model
├── data_fetching/
│   ├── data/                          # Stored JSON data
│   ├── error_tracking.py
│   ├── fetch_articles.py
│   ├── fetch_authors.py
│   ├── fetch_competitor_articles.py
│   ├── fetch_competitor_authors.py
│   ├── fetch_openapc_info.py          # Enrich with OpenAPC
│   ├── generating_final_db.py         
│   ├── main_script.py                 # Pipeline orchestrator
│   ├── references_citations.py
├── LICENSE
├── README.md
├── requirements.txt
└── venv/                              # Local virtual environment
```

## Tableau Dashboard

The interactive dashboard visualizes institutional publishing patterns by showing:
- Top contributing institutions over time  
- Co-authorship and citation networks  
- Regional clusters of institutions  
- Lead generation outputs (tiers, scores, agreement suggestions)  
- Filters for journal, year, and region  

🔗 [**View the Tableau Dashboard**](https://public.tableau.com/views/dashboard_17516543242160/Dashboard)



## Roadmap

- [x] Fetch metadata from Crossref/OpenAlex  
- [x] Store raw data in JSON format  
- [x] Build final article-level database  
- [x] Enrich with OpenAPC data  
- [x] Aggregate to institution-level metrics  
- [x] Perform clustering analysis  
- [x] Develop lead generation model  
- [x] Publish Tableau dashboards  
- [ ] Explore open-source dashboard alternatives (e.g., Superset)  
- [ ] Migrate storage to SQL for scalability  
- [ ] Automate data refresh cycle  
 

## License
This project is licensed under the MIT License.

