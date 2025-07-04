# 🧠 Journal Analysis Project

A full-stack data pipeline for retrieving, storing, and analyzing academic article metadata — powered by **FastAPI**, **PostgreSQL**, and a **Power BI** dashboard.

## 📌 Overview

This project is designed to:
- **Backend**: Extract and store metadata from academic articles (e.g., title, authors, abstract) using a FastAPI service and SQLAlchemy ORM.
- **Database**: Store structured metadata in a PostgreSQL database.
- **Frontend**: Visualize insights via an interactive Power BI dashboard (planned).

## 🛠 Tech Stack

| Layer     | Tech                  |
|-----------|-----------------------|
| Backend   | FastAPI, SQLAlchemy   |
| Database  | PostgreSQL            |
| Frontend  | Power BI (planned)    |
| Dev Tools | VSCode, Terminal      |

---

## 🔧 Backend Setup

### Prerequisites
- Python 3.9+
- PostgreSQL
- Virtual environment (`venv` or `conda`)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/your-username/journal-analysis-project.git
cd journal-analysis-project

# 2. Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

### PostgreSQL Setup

1. Install PostgreSQL and create a database (e.g., `journal_db`)
2. Add your DB credentials in a `.env` file:

```
DATABASE_URL=postgresql://username:password@localhost/journal_db
```

### Run the API

```bash
uvicorn app.main:app --reload
```

---

## 🧱 Project Structure

```
journal-analysis-project/
├── app/
│   ├── main.py          # FastAPI entry point
│   ├── models.py        # SQLAlchemy models
│   ├── schemas.py       # Pydantic schemas
│   ├── crud.py          # DB logic
│   └── database.py      # DB connection
├── requirements.txt
└── README.md
```

---

## 📊 Frontend: Tableau

The frontend will be built using Tableau and then upgraded to Apache Superset (planned) to:
- Visualize article trends and metadata insights
- Connect to the PostgreSQL backend
- Provide filtering by author, keyword, source, etc.

Check out the interactive version on Tableau Public:  
👉 [View Dashboard]([https://public.tableau.com/app/profile/your-username/viz/your-dashboard-name](https://public.tableau.com/app/profile/paula.feijo.de.medeiros6771/viz/dashboard_17516543242160/Dashboard1))

*(Apache Superset setup instructions will be added when development begins.)*

---

## 🚧 Roadmap

- [x] Backend FastAPI + DB setup
- [ ] Implement article ingestion endpoint
- [ ] Expand DB schema (e.g., keywords, citations)
- [ ] Develop Power BI reports
- [ ] Automate data refresh pipeline
