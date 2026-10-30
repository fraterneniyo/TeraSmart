
# TeraSmart | Plant with Insight

**NISR Hackathon 2026 | Agricultural Productivity Track**

**Team RwandaRise**
- JustinenAmizero Uwase
- Fraterne Niyomugenga

## 1. About TeraSmart

TeraSmart is an agricultural decision-support application designed to help Rwandan farmers manage their farming activities and make informed agricultural decisions.

The application combines machine-learning-based crop-production estimates, farm management, financial tracking, district weather forecasts, and AI-assisted guidance.

It supports two user roles: **Farmer** and **Agricultural Planner**.

## 2. Project Features

### Farmer Dashboard
- Register farms and edit field information.
- Select crop, season, field area, seed variety, and fertilizer type.
- Estimate crop production using trained machine-learning models.
- Track agricultural activities, including overdue and upcoming tasks.
- Record farm income and expenses and view the recorded cash balance.
- Access district weather forecasts, including rainfall probability.
- Receive optional AI-powered farming guidance.

### Planner Dashboard
- View agricultural information summarized from registered farms.
- Explore district-level agricultural data and production estimates.
- Review planning dashboards and resource-related information.
- Download agricultural planning reports in CSV and Markdown formats.

## 3. Machine Learning and Data

TeraSmart uses supervised machine-learning models developed using prepared data derived from the **NISR 2025 Seasonal Agricultural Survey (SAS)**.

The application supports crop-production estimation for 10 crops, subject to the model's supported combinations and input requirements.

Two trained prediction artifacts are included:

| Model File | Purpose |
|---|---|
| `data/IhingaAI_Frozen_Model_v1.pkl` | Baseline crop-production prediction model |
| `data/IhingaAI_Frozen_Extension_v1.pkl` | Extended crop-production prediction model |

These are shared underlying model artifacts adapted for use in TeraSmart. TeraSmart remains a separate application with its own interface, database, and workflows.

Predictions are experimental estimates based on historical agricultural information and are not guaranteed harvest outcomes.

## 4. Technologies Used

- **Python and Streamlit:** Application development
- **Scikit-learn, Pandas, NumPy:** Machine learning and data processing
- **SQLite:** Application database
- **Plotly:** Interactive dashboards
- **Open-Meteo:** District weather information
- **Google Gemini:** Optional AI assistant

## 5. Installation and Usage

TeraSmart is provided through GitHub for local installation.

### Step 1: Clone the Repository

```bash
git lfs install
git clone https://github.com/fraterneniyo/TeraSmart.git
cd TeraSmart
git lfs pull
```

Git LFS is required to download the large trained model files.

### Step 2: Install Dependencies

Use Python 3.11 or 3.12.

```bash
python -m pip install -r requirements.txt
```

### Step 3: Run the Application

```bash
python -m streamlit run app.py
```

Open the local address displayed by Streamlit, usually:

http://localhost:8501

An internet connection is required for live weather information and optional AI services.

## 6. Demonstration Accounts

The following accounts are intended for testing with the supplied demonstration database.

| Role | Phone Number | Password |
|---|---|---|
| Farmer | `0790888558` | `Frat@2026` |
| Planner | `079088559` | `Just@2026` |

**Note:** These credentials require the matching demonstration database. If the application creates a fresh database, the accounts must be registered again.

## 7. Repository Structure

```text
TeraSmart/
├── app.py
├── core/
├── assets/
├── data/
│   ├── IhingaAI_Frozen_Model_v1.pkl
│   └── IhingaAI_Frozen_Extension_v1.pkl
├── storage/
├── .streamlit/
│   └── config.toml
├── requirements.txt
├── README.md
└── DEPLOYMENT_NOTES.md
```

The `data/` folder also contains crop and district reference files.

The `storage/` folder is used for local database records.

**Security:** Never upload `.streamlit/secrets.toml`, API keys, or private user information to this public repository. Optional AI access requires a privately configured `GEMINI_API_KEY`.

## 8. Limitations

- Crop predictions depend on historical data and require further field validation.
- The application is a hackathon prototype, not a production agricultural advisory service.
- Weather information represents district reference locations, not individual farms.
- The AI assistant requires Gemini API access for general questions.
- Financial balances represent recorded transactions, not complete accounting profits.
- Planner statistics reflect application records, not official national agricultural totals.

## 9. Project Team

**Team:** RwandaRise

**Members:**
- JustinenAmizero Uwase
- Fraterne Niyomugenga

**Competition:** NISR Hackathon 2026

**Track:** Agricultural Productivity

**GitHub:** https://github.com/fraterneniyo/TeraSmart

TeraSmart | Plant with Insight | Team RwandaRise
