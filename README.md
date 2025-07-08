# 🧠 Journal Analysis Project

A data pipeline for retrieving, analyzing, and visualizing academic journal metadata — using data from **Crossref** and **OpenAlex**, with a focus on **institutional research trends**, and presented through an interactive **Tableau** dashboard.

## 📌 Overview

This project is focused on:
- **Collecting** academic metadata from **Crossref** and **OpenAlex** APIs  
- **Storing** structured raw data in **JSON** format  
- **Analyzing** institutional-level publication and citation patterns using clustering techniques  
- **Visualizing** key insights in a **Tableau dashboard** for exploration  
- **Generating leads** by identifying high-output or emerging institutions in specific research areas

The **main goal** is to use these insights to **develop a model that generates institutional leads** for strategic or commercial purposes.

## ✅ Current Progress

- ✅ Fetched articles, authors, affiliations, and citation data from **Crossref** and **OpenAlex**  
- ✅ Saved metadata to structured **JSON** files  
- ✅ Performed clustering analysis to identify institutional publishing trends  
- ✅ Published an interactive **Tableau dashboard** highlighting top institutions, citation networks, and research clusters  

## 🛠 Tech Stack

| Stage        | Tools/Libraries                             |
|--------------|---------------------------------------------|
| Data Fetch   | Python, Requests, Crossref API, OpenAlex API |
| Storage      | JSON files                                  |
| Analysis     | Pandas, NumPy, Scikit-learn                 |
| Visualization| Tableau Public                              |
| Dev Tools    | Jupyter, VSCode, Terminal                   |

---

## 🗂 Project Structure

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
│   ├── generating_final_db.py         # Final data merge
│   ├── main_script.py                 # Pipeline orchestrator
│   ├── references_citations.py
│   └── top_competitors_citations.py
├── LICENSE
├── README.md
├── requirements.txt
└── venv/                              # Local virtual environment
```

---

## 📊 Tableau Dashboard

The dashboard visualizes institutional publishing patterns by showing:
- Top contributing institutions over time  
- Co-authorship and citation networks  
- Clustered research areas and collaborations  
- Filters for journal, year, and field  

🔗 [**View the Tableau Dashboard**](https://public.tableau.com/app/profile/paula.feijo.de.medeiros6771/viz/dashboard_17516543242160/Dashboard)

---

## 🚧 Roadmap

- [x] Fetch metadata from Crossref/OpenAlex  
- [x] Store raw data in JSON format  
- [x] Perform cluster analysis on institutions  
- [x] Publish Tableau dashboard  
- [ ] Expand clustering features (e.g., keyword embeddings)  
- [ ] Automate refresh and update cycle  
- [ ] **Develop institutional lead generation model** based on clustering + output metrics  
- [ ] Explore open-source dashboard alternatives (e.g., Superset)  
