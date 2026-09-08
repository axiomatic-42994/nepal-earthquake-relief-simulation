# 🚀 Setup & Execution Guide: Nepal Earthquake Topic Modeling

Welcome to the **2015 Nepal Earthquake Humanitarian Needs Topic Modeling Pipeline** repository! This guide provides complete step-by-step instructions to set up the environment, download and preprocess the crisis dataset, train candidate topic models (LDA & NMF), and generate benchmark evaluation reports.

---

## 📋 Prerequisites & System Requirements

- **Operating System:** Windows, macOS, or Linux
- **Python:** Python `3.10` or higher (`3.10`, `3.11`, or `3.12` recommended)
- **Git:** Installed on your system ([Download Git](https://git-scm.com/))
- **Hardware:** Standard CPU (No GPU required; training takes under 2 minutes for all sweeps)

---

## 🛠️ Step 1: Clone the Repository

Open your terminal (PowerShell, Command Prompt, or Bash) and clone the repository:

```bash
git clone https://github.com/yasho11/earthquaker_2015_lda_topic_modeling.git
cd earthquaker_2015_lda_topic_modeling
```

---

## 🐍 Step 2: Create & Activate Virtual Environment

It is strongly recommended to use an isolated virtual environment (`.venv`).

### On Windows (PowerShell / Command Prompt):
```powershell
# 1. Create virtual environment
python -m venv .venv

# 2. Activate virtual environment (PowerShell)
.venv\Scripts\Activate.ps1

# (If using CMD instead of PowerShell):
# .venv\Scripts\activate.bat
```

> **Note for Windows PowerShell users:** If you see an execution policy restriction error (`cannot be loaded because running scripts is disabled`), run this command once and retry activating:
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
> ```

### On macOS / Linux (Terminal):
```bash
# 1. Create virtual environment
python3 -m venv .venv

# 2. Activate virtual environment
source .venv/bin/activate
```

---

## 📦 Step 3: Install Required Dependencies

Upgrade `pip` and install all required libraries from `requirements.txt`:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> **Note:** NLP tokenizers and NLTK resources (`stopwords`, `wordnet`, `omw-1.4`) will download automatically on first run without manual intervention.

---

## ⚡ Step 4: Run the Pipeline

You can run the entire pipeline end-to-end with a single command, or run individual sprints sequentially.

### Option A: Run Full Pipeline (Recommended)
This automatically runs Data Acquisition $\rightarrow$ NLP Cleaning $\rightarrow$ Model Sweeps ($K \in [5, 30]$) $\rightarrow$ Evaluation & Leaderboard $\rightarrow$ Model Selection:

```bash
python main.py
```
*(Alternative runner: `python scripts/run_pipeline.py`)*

---

### Option B: Run Sprint-by-Sprint (Step-by-Step)

If you want to observe each stage individually:

#### 1. Sprint 0 — Data Acquisition & Filtering
Downloads `QCRI/CrisisBench-all-lang` from Hugging Face, filters for the 2015 Nepal earthquake, extracts English tweets, and deduplicates records.
```bash
python main.py --sprint 0
```
- **Output:** `data/interim/nepal_eq.csv` (~11,032 filtered crisis tweets)

#### 2. Sprint 1 — NLP Preprocessing & Corpus Construction
Sanitizes raw text (strips URLs, mentions, RTs), performs lemmatization, removes custom disaster stopwords, learns bigram/trigram collocations, and generates Gensim Dictionary, Bag-of-Words, and TF-IDF matrices.
```bash
python main.py --sprint 1
```
- **Outputs in `data/processed/`:**
  - `nepal_eq_processed.parquet` (Clean tokenized documents)
  - `dictionary.gensim` (Filtered vocabulary: 2,251 terms)
  - `corpus_bow.mm` (Bag-of-Words matrix)
  - `corpus_tfidf.mm` (TF-IDF matrix)

#### 3. Sprint 2 — Candidate Model Training Sweeps
Trains 24 candidate topic models across $K \in \{5, 8, 10, 12, 15, 20, 25, 30\}$ for **Gensim Variational LDA**, **Scikit-Learn Batch LDA**, and **Scikit-Learn NMF**.
```bash
python main.py --sprint 2
```
*Custom $K$ sweep example:*
```bash
python main.py --sprint 2 --k-sweep 5 10 15 20 25 30
```
- **Output:** Serialized models and metadata in `models/checkpoints/`

#### 4. Sprint 3 — Coherence Evaluation, Leaderboard & Selection
Computes $C_v$ and $U_{\text{mass}}$ topic coherence, maps discovered topics to human-annotated crisis categories via SentenceTransformer embeddings, calculates NMI/F1/ARI scores, ranks all configurations, and exports the winning model (`sklearn_nmf_k30`).
```bash
python main.py --sprint 3
```
- **Outputs:**
  - `reports/model_leaderboard.csv` (Ranked table of all 24 models)
  - `reports/figures/coherence_curves.png` (Coherence vs. $K$ chart)
  - `reports/figures/confusion_matrix.png` (Topic-to-class alignment heatmap)
  - `models/selected/` (Winning model checkpoint, metadata, and 30-topic schema)

---

## 🧪 Step 5: Run Automated Unit Tests

To verify that the dataset loader, text cleaner, and coherence evaluation modules function correctly on your machine, run `pytest`:

```bash
pytest
```

---

## 📂 Project Directory Structure

```
earthquaker_2015_lda_topic_modeling/
├── config/
│   └── config.yaml            # Master hyperparameter & path configuration
├── data/                      # Data storage (generated automatically upon running)
│   ├── interim/               # Filtered Nepal earthquake tweets (nepal_eq.csv)
│   └── processed/             # Tokenized parquet, Gensim dictionary, BoW & TF-IDF
├── models/
│   ├── checkpoints/           # All 24 trained candidate model checkpoints
│   └── selected/              # Top-ranked winning model, metadata & topic schema
├── notebooks/
│   └── 02_eda.ipynb           # Exploratory data analysis notebook
├── reports/
│   ├── figures/               # Coherence curves & confusion matrix plots
│   └── model_leaderboard.csv  # Full empirical leaderboard with rankings
├── scripts/
│   ├── download_data.py       # Standalone data fetcher
│   ├── run_preprocessing.py   # Standalone NLP cleaner
│   └── run_pipeline.py        # End-to-end pipeline runner
├── src/
│   ├── data/                  # Loading, cleaning, and corpus builder scripts
│   ├── evaluation/            # Coherence, ground-truth alignment, and leaderboard
│   ├── models/                # Training modules for LDA (Gensim/Sklearn) and NMF
│   └── utils/                 # I/O, logging, and plotting helpers
├── tests/                     # Pytest automated test suite
├── main.py                    # Main CLI entry point
├── pytest.ini                 # Pytest configuration
├── requirements.txt           # Python package dependencies
└── INSTRUCTIONS.md            # This setup & run guide
```

---

## ⚙️ Custom Configuration (`config/config.yaml`)

You can modify experiment parameters directly in [`config/config.yaml`](config/config.yaml):
- **Topic Sweep ($K$):** Change `models.k_sweep` (e.g. `[5, 10, 15, 20, 25, 30]`)
- **Stopwords:** Add domain-specific terms under `preprocessing.custom_stopwords`
- **Vocabulary Filters:** Adjust `no_below`, `no_above`, or `keep_n`
- **Embedding Model:** Change `evaluation.embedding_model` (defaults to `sentence-transformers/all-MiniLM-L6-v2`)

---

## ❓ Frequently Asked Questions & Troubleshooting

1. **First-time embedding model download is slow?**
   - The first time Sprint 3 runs, `sentence-transformers` downloads the lightweight `all-MiniLM-L6-v2` model (~80 MB) into your local cache. Subsequent runs will use the cached weights instantly.

2. **How do I inspect the discovered topics?**
   - After running the pipeline, open `models/selected/topic_schema.json` or `models/selected/metadata.json` to view the top keywords and representative tweets for all 30 discovered humanitarian topics.

3. **How do I view the leaderboard in the console?**
   - Running `python main.py --sprint 3` prints a formatted ASCII table ranking the top models by composite score. You can also open `reports/model_leaderboard.csv` in Excel or pandas.

---
*Happy Experimenting! If you encounter any issues, verify your virtual environment is active and all packages from `requirements.txt` are installed.*
