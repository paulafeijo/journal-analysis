# Journal Analysis

A complete **data pipeline** for retrieving, analyzing, and visualizing academic journal metadata — using data from **Crossref** and **OpenAlex**, with a focus on **institutional research trends**, and presented through an interactive **Tableau** dashboard.

> **For detailed documentation, visit the project's wiki:** \
> https://github.com/paulafeijo/journal-analysis/wiki


## Overview

This project is focused on:
- **Collecting** academic metadata from **Crossref** and **OpenAlex** APIs (articles, authors, institutions, citations).
- **Storing** structured raw data in **JSON** format. 
- **Analyzing** institutional-level publication and citation patterns using clustering techniques. 
- **Visualizing** key insights in a **Tableau dashboard** for exploration.
- **Generating leads** by identifying high-output or emerging institutions in specific research areas.

**Goal:** build a model that can **recomment institutionss** for strategic partnerships, collaborations, or commercial outreach based on research output and trends.


## Current Features

- Automated retrieval of articles, authors, affiliations, and citation data from **Crossref**, **OpenAlex** and **OpenCitations**.
- Structured storage of metadata in JSON files.
- Institutional trend analysis using **clustering algorithms**.
- **Tableau dashboard** displaying:
  - Top institutions by publication volume.
  - Citation and co-authorship networks.
  - Clusters of research topics and collaborations.


## Tech Stack

| Stage           | Tools/Libraries                                                 |
|-----------------|-----------------------------------------------------------------|
| Data Fetching   | Python, Requests, Crossref API, OpenAlex API, OpenCitations API |
| Storage         | JSON files                                                      |
| Analysis        | Pandas, NumPy, Scikit-learn                                     |
| Visualization   | Tableau Public                                                  |
| Dev Tools       | VSCode, Terminal                                                |




## Project Structure

```
journal-analysis/
├── dashboard/
│   └── dashboard.twbx                 # Tableau dashboard file
├── data_analysis/
│   └── clustering.py                  # Cluster analysis script
├── data_fetching/
│   ├── data/                          # Stored JSON data
│   ├── error_tracking.py
│   ├── fetch_articles.py
│   ├── fetch_authors.py
│   ├── fetch_competitor_articles.py
│   ├── fetch_competitor_authors.py
│   ├── generating_final_db.py         
│   ├── main_script.py                 # Pipeline orchestrator
│   ├── references_citations.py
│   └── top_competitors_citations.py
├── LICENSE
├── README.md
├── requirements.txt
└── venv/                              # Local virtual environment
```



## Tableau Dashboard

The interactive dashboard visualizes institutional publishing patterns by showing:
- Top contributing institutions over time  
- Co-authorship and citation networks  
- Clustered research areas and collaborations  
- Filters for journal, year, and field  

🔗 [**View the Tableau Dashboard**](https://public.tableau.com/app/profile/paula.feijo.de.medeiros6771/viz/dashboard_17516543242160/Dashboard)



## Roadmap

- [x] Fetch metadata from Crossref/OpenAlex  
- [x] Store raw data in JSON format  
- [x] Perform cluster analysis on institutions  
- [x] Publish Tableau dashboard  
- [ ] **Develop institutional lead generation model** based on clustering + output metrics  
- [ ] Explore open-source dashboard alternatives (e.g., Superset)  

## Improvement backlog
- Migrate database to SQL.
- Uptade datafetching scripts to consult existing database before fetching via API.
- Automade data refresh cycle.
- Add keyword embeddings for topic clustering

## License
This project is licensed under the MIT License.

