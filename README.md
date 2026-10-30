# TeraSmart — Plant with Insight

TeraSmart is a streamlined agricultural decision-support application built with Streamlit. It is designed as a second, distinct project alongside IhingaAI, with a lighter scope and a different interface. The app supports two roles only: **Farmer** and **Planner**.

## What it includes

- Field registration and management
- Harvest estimation for 10 supported crops
- Crop monitoring notes
- Farm activity tracking
- Basic farm finance records
- District weather lookups
- AI Assistant support
- Planner dashboards with aggregated views
- Planner production forecasts from the latest saved estimate per field
- Downloadable planning reports (Markdown and CSV)
- In-app **Data Sources** page

## Run locally

Use Python 3.11 or 3.12.

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Notes

Weather forecasts are supplied by [Open-Meteo](https://open-meteo.com/) using approximate district reference locations. Harvest estimation reuses the frozen prediction models packaged in `data/`. Planner views show aggregated user-entered records only and should not be treated as official agricultural statistics.

## Planner reporting note

Production totals use the latest saved estimate for each forecasted field, to prevent double counting. Reports are based on fields entered into TeraSmart, not nationally representative agricultural statistics.

## October 2026 feature update

- Edit registered fields (name, crop, season, district, area, farmer type, planting date, seed variety and fertilizer). Older databases are migrated automatically on app start. Existing saved estimates are **not** recalculated automatically following field edits; generate a fresh forecast.
- Seed variety: Local / Improved / Not sure. Fertilizer: Organic / Inorganic / None.
- The farmer dashboard displays a balance of **recorded sales minus recorded expenses** across all fields. This is a recorded cash-flow balance, not a complete accounting profit.
- Overdue activities display 🔴, upcoming and today's activities display 🟢; activities can be completed or removed.
- District daily forecast includes maximum precipitation probability (%) alongside projected rainfall in millimetres. This is a forecast, not observed rainfall.
- The assistant can answer general questions **when Gemini API access is configured**. Without the API key or connectivity, only limited rule-based farming tips are supported; general questions will transparently indicate the limitation.

## AI service configuration

Set `GEMINI_API_KEY` through an environment variable or in a local `.streamlit/secrets.toml` (not committed or shared):

```toml
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
PLANNER_SETUP_CODE = "YOUR_LONG_PRIVATE_PLANNER_CODE"
```

Keep this file private. Planner account creation requires a private setup code at least 12 characters long. Do not publish real farmers' data or API keys. Weather and AI require outbound internet access.

## Privacy and deployment

The distributed ZIP intentionally excludes the original `storage/terasmart.sqlite3` and `.streamlit/secrets.toml` because they can contain private user data and credentials. The app creates a fresh database automatically on first launch. To upgrade an existing instance, separately back up and preserve its SQLite database in `storage/` before running the new code. Use durable disk storage and authentication/operational security review before any real deployment. SQLite is suitable for a small demo, not a high-scale multi-user production service.
