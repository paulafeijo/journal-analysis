# 🧠 Journal Analysis Project

A full-stack data pipeline for retrieving, storing, and analyzing academic article metadata — powered by **FastAPI**, **PostgreSQL**, and a **Power BI** dashboard.

This project is currently focused on extracting and analyzing journal publication data to uncover trends in Open Access (OA) publishing. A backend service for extracting, storing, and analyzing academic article metadata using FastAPI and PostgreSQL.

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

🚀 Project Overview
This project is designed to:

Retrieve academic article metadata (e.g., title, authors, abstract)

Store the data in a PostgreSQL database

Use SQLAlchemy for ORM-based database interactions

Set the stage for future analysis and frontend development

🛠️ Tech Stack
Backend Framework: FastAPI

Database: PostgreSQL

ORM: SQLAlchemy

Development Tools: VSCode + Terminal


📂 Project Structure (so far)
pgsql
Copy
Edit
journal-analysis-project/
├── app/
│   ├── main.py
│   ├── models.py
│   ├── schemas.py
│   ├── crud.py
│   └── database.py
├── requirements.txt
└── README.md

✅ To-Do / Roadmap
 Set up FastAPI + PostgreSQL connection

 Add article retrieval endpoint

 Implement article parsing and validation

 Expand database schema for additional metadata

 Build frontend (TBD)
