
# Information Retrieval System

This project implements a full Information Retrieval (IR) system with REST APIs, document representation models, search capabilities, evaluation notebooks, and a simple web-based UI.

---

## 📌 Project Structure

```
information-retrieval-system-hussam/
├── api/
├── core/
├── notebooks/
├── ui/
├── utils/
├── extract.py
├── config.py.example
├── run_services.sh
├── IR_Project_SOA.postman_collection.json
├── README.md
└── .gitignore
```

---

### ✅ **Folder & File Explanations**

---

### `/api/`

Contains REST API services built with **FastAPI (most likely)**. Each Python file exposes endpoints for interacting with different system modules:

- **data_loader_api.py** → APIs for data loading and ingestion.
- **representation_api.py** → APIs for generating document representations (TF-IDF, BM25, embeddings, etc).
- **search_api.py** → APIs for performing search and retrieving ranked documents.

---

### `/core/`

Holds the core logic and processing modules:

- **text_preprocessor.py** → Responsible for text cleaning, tokenization, stop-word removal, and other preprocessing steps essential for building IR models.

---

### `/notebooks/`

Contains **Jupyter Notebooks** used for:

- Running offline evaluations.
- Comparing different retrieval models (e.g., BM25, TF-IDF, dense retrievers).
- Testing FAISS performance on different datasets like **Antique**, **LoTTE**, and **Quora**.
- Doing experiments on clustering and its impact on retrieval.

Example notebooks:

- `comparative_evaluation_antique.ipynb`
- `faiss_performance_comparison_quora.ipynb`
- `test-building-clusters.py`

---

### `/ui/`

Contains a minimal web-based user interface:

- **app.py** → Likely a simple web front-end (maybe Streamlit or Flask) to interact with the IR backend.
- **__init__.py** → For making it a package.

---

### `/utils/`

Utility scripts used for setup and support tasks:

- **database_setup.py** → Likely responsible for initializing database tables or collections needed by the IR system.

---

### Top-Level Files:

- **extract.py** → Script to extract or preprocess raw datasets (before indexing).
- **config.py.example** → Sample configuration file for environment settings (database connection, paths, hyperparameters, etc).
- **run_services.sh** → Shell script to run/start all necessary backend services in one go.
- **IR_Project_SOA.postman_collection.json** → A Postman collection for testing the APIs (contains predefined API requests).

---

## ⚙️ How to Run the Project

### 1. Setup Python Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt  # Make sure you have a requirements file, if not create one.
```

### 2. Set Up Config

```bash
cp config.py.example config.py
# Edit config.py with your database credentials, paths, etc.
```

### 3. Run All Services

```bash
bash run_services.sh
```
This should launch the backend APIs and possibly the UI.

### 4. Test APIs

Use **Postman** with the provided collection:

- Import `IR_Project_SOA.postman_collection.json` into Postman.
- Hit the endpoints (data load, search, etc).

---

## 📊 Running Evaluations

Open the Jupyter Notebooks in `/notebooks/` folder to run:

- Comparative evaluations on different datasets.
- FAISS performance comparisons.
- Clustering experiments.

```bash
jupyter notebook
```

---

## 🖥️ Running the UI


```bash
flask --app ui/app run --port 5001
```

---

## ✅ Features Summary

- Text preprocessing and indexing.
- Multiple document representation models.
- Search APIs.
- Performance evaluation on standard IR datasets.
- FAISS-based dense retrieval support.
- Optional web UI for demonstration.

---

## 🏗️ Future Improvements (Suggestions)

- Add detailed documentation for each API endpoint.
- Include installation and environment setup instructions for FAISS if used.
- Containerize the project with Docker.
- Add user authentication for search APIs.

---

## 👨‍💻 Author

Hussam Eldeen (GitLab: [@hussameldeen](https://gitlab.com/hussameldeen))

---
