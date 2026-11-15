# EOAgriTool Farm-Monitoring Project Footprint

## What this is
**EOAgriTool** is a farm-monitoring and decision-support web app, with its clearest implemented monitoring functions focused on climate forecasts, water balance, field records, and agronomic recommendations. The current implementation is a Python/Quart backend with a JavaScript and HTML frontend; some farm records are browser-local, while live climate and water readings come from Open-Meteo.

## Stack
- **Language(s):** Python, JavaScript, HTML, CSS
- **Framework / runtime:** Quart with Hypercorn; static multi-page frontend
- **Notable libraries:** `httpx` for async requests, Azure OpenAI client for chat, `quart-cors`, Chart.js for charts
- **Optional services:** Azure Cosmos DB for conversation history; Open-Meteo for live climate and water data

## Current farm-monitoring footprint

| Area | Current functions | What to keep in mind |
|---|---|---|
| **Climate** | `/climate_data` fetches temperature, rainfall, and wind forecasts for configured regions and forecast horizons. The Climate page displays charts, refresh time, and derived risk signals. | Region coordinates are predefined; this is regional monitoring, not a field-bound satellite or sensor feed. |
| **Water and irrigation** | `/water_data` returns soil moisture, reference evapotranspiration (ET₀), rainfall, and a derived irrigation deficit. The Water page visualizes these metrics. | The endpoint uses forecast-service data; validate the deficit calculation and thresholds against local agronomic requirements before treating them as irrigation prescriptions. |
| **Fields and crops** | The Fields page supports field records, crop/health details, and media uploads. `assets/app.js` and the page use browser `localStorage` for field data. | Records are currently browser-local, so they are not a shared, server-backed farm database. |
| **Recommendations** | `/recommendations` applies rule-based thresholds for water, soil pH, organic matter, energy, carbon, and previous-crop rotation. | These are rules and thresholds, not a demonstrated predictive model. Validate thresholds by crop, region, season, and units. |
| **Reports and dashboard** | Dashboard and report pages present farm signals and rotation-oriented summaries; sample agronomic data includes a Nile Delta field and a multi-year crop plan. | Confirm each displayed value is calculated from current farm data rather than sample or locally stored values. |
| **Alerts** | The frontend has an Alerts page; climate and water screens show status and stale-data messages. | The climate/water fallback is useful for availability, but stale readings must remain clearly labeled so users do not mistake them for current conditions. |
| **Farm advisor / chat** | The backend provides Azure OpenAI conversation endpoints; Cosmos DB can store conversation history when configured. | This is an optional service dependency, separate from the core climate and water endpoints. |

The advertised integration of satellite, UAV, and ground-sensor observations is **not established by the current code paths reviewed**. Similarly, there is no evident farm-wide carbon-accounting pipeline: the recommendation engine recognizes carbon-footprint inputs, but that is not the same as measuring emissions from farm activity. See [`backend/routes.py`](https://github.com/aimtyaem/EOAgriTool/blob/gh-pages/backend/routes.py), [`backend/recommend/engine.py`](https://github.com/aimtyaem/EOAgriTool/blob/gh-pages/backend/recommend/engine.py), [`assets/app.js`](https://github.com/aimtyaem/EOAgriTool/blob/gh-pages/assets/app.js), and [`agronomic-plan.json`](https://github.com/aimtyaem/EOAgriTool/blob/gh-pages/agronomic-plan.json).

## How it's organized

```text
backend/
  routes.py             Quart routes; Open-Meteo, recommendations, chat, history
  recommend/engine.py   Rule-based farm recommendations and energy-bill parsing
assets/
  app.js                Shared navigation, browser storage, API helper
  styles.css            Shared frontend styling
tests/
  test_routes.py        Recommendation and energy-bill parser tests
  test_climate_water_endpoints.py  Climate/water API behavior tests
*.html                  Dashboard, fields, climate, water, reports, alerts, and other pages
```

**How it fits together:** `app.py` creates the Quart app through `backend.routes.create_app()`. The frontend pages call backend endpoints; climate and water responses are fetched from Open-Meteo and cached in process for five minutes, with last-good data returned as stale if a refresh fails. Field records use browser `localStorage`, while optional Azure services support chat and conversation history. The data flow and app entry point are in [`backend/routes.py`](https://github.com/aimtyaem/EOAgriTool/blob/gh-pages/backend/routes.py) and [`app.py`](https://github.com/aimtyaem/EOAgriTool/blob/gh-pages/app.py).

## Development priorities for reliable farm monitoring

1. **Make farm data persistent and field-specific:** move field records from browser-only storage to a backend data model, and associate observations with a field, coordinates, crop, and timestamp.
2. **Connect and document observation sources:** identify which satellite, sensor, or UAV providers are actually supported; define units, spatial resolution, update cadence, and data provenance.
3. **Validate agronomic rules:** review soil, water, and crop thresholds with local experts and record their applicable crop/region/season. Mark estimates and advisory outputs clearly.
4. **Protect against misleading data:** show source, timestamp, and stale status consistently; test upstream outage and recovery behavior.
5. **Strengthen testing and deployment consistency:** run tests in CI, align deployment instructions with the Python/Quart app, and verify health checks and required Azure settings for each deployment target.

## How to run it

The repository’s deployment guide gives this local setup and test path:

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
pytest
```

The app listens on port `8000` by default. Open-Meteo climate/water access does not require credentials; Azure OpenAI and Cosmos DB features require their corresponding environment settings. See [`DEPLOYMENT.md`](https://github.com/aimtyaem/EOAgriTool/blob/gh-pages/DEPLOYMENT.md) and [`.env.example`](https://github.com/aimtyaem/EOAgriTool/blob/gh-pages/.env.example).

## Follow-up questions

- “How can I make field records persistent instead of using `localStorage`?”
- “Which climate and water endpoint tests should I extend for field-specific monitoring?”
- “What would it take to connect satellite or sensor observations to `backend/routes.py`?”
