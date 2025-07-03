# 📊 Journal Analysis for Open Access Insights

**FastAPI-based backend and data pipeline for analyzing Open Access publication patterns at the institutional level.**

This project is currently focused on extracting and analyzing journal publication data to uncover trends in Open Access (OA) publishing. A backend service for extracting, storing, and analyzing academic article metadata using FastAPI and PostgreSQL.

> 📌 *Note: This is an early-stage version of the project. Integration with a database and full publication system is planned for future development.*

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
