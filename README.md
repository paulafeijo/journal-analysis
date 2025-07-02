# 📊 Journal Analysis for Open Access Insights

**FastAPI-based backend and data pipeline for analyzing Open Access publication patterns at the institutional level.**

This project is currently focused on extracting and analyzing journal publication data to uncover trends in Open Access (OA) publishing. It includes a modular data pipeline and a RESTful API to expose early results.

> 📌 *Note: This is an early-stage version of the project. Integration with a database and full publication system is planned for future development.*

---

## 🚀 Features

- 🔎 **OA Publication Tracking**: Analyze proportions of OA vs. closed access articles.
- 🏫 **Institutional Filtering**: Filter publications by institution or affiliation metadata.
- 📈 **Trend Analysis**: Visualize OA evolution over time, across fields or journals.
- 🧪 **FastAPI Backend**: RESTful API to expose analysis results and interact with processed data.
- 📂 **Modular Data Pipeline**: Load, clean, and transform publication data from various sources (e.g., DOAJ, Crossref, internal CSVs).

---

## 🛠️ Tech Stack

- **Python 3.10+**
- **FastAPI** – for the REST API
- **Pandas** – data manipulation
- **Uvicorn** – ASGI server
- **Jupyter** – for exploratory analysis and prototyping

---

## 📁 Project Structure

```
journal-analysis/
├── api/               # FastAPI application
│   ├── main.py
│   └── routes/
├── data/              # Raw and processed datasets
├── notebooks/         # Jupyter notebooks for exploration
├── pipeline/          # Data extraction, cleaning, and transformation logic
├── models/            # ML models or scoring logic (if any)
├── tests/             # Unit tests
├── requirements.txt
├── README.md
└── .gitignore
```

---

## 🚧 Setup Instructions

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-username/journal-analysis.git
   cd journal-analysis
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the API**:
   ```bash
   uvicorn api.main:app --reload
   ```

---

## 📊 Example Use Cases

- Determine % of OA articles published by a university over the past 5 years.
- Compare OA adoption rates across departments.
- Generate visual dashboards of OA publishing trends.
- Serve data to external systems (e.g., institutional repositories).

---

## 📜 License

This project is open-source and available under the [MIT License](LICENSE).

---

## 🙌 Acknowledgements

Data sources may include:
- [DOAJ](https://doaj.org)
- [Crossref](https://www.crossref.org/)
- [Unpaywall](https://unpaywall.org/)
- Internal institutional records or Scopus/WoS exports

---

## ✍️ Author

*Your Name*  
TCC – MBA Project  
[Your Email or LinkedIn]
