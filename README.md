# Jewellery Pricing App (Local-Only)

A local Streamlit app for jewellery commission and workshop pricing.

## Stack
- Python 3.11+
- Streamlit UI
- SQLite (`sqlite3`)
- Requests (metal prices API)
- Pandas (CSV import/export)
- python-dotenv (`.env` API key loading)

## Features
- Login / sign-up page with local credentials
- Dashboard with cached XAG/XAU/XPT spot prices in GBP + refresh button
- Settings for labour, VAT, waste, overhead, profit, unit conversion, and cache TTL
- Stone catalog CRUD with optional stone image upload, plus CSV import/export + downloadable template
- Commission quote builder with itemised breakdown, save history, printable HTML export
- Dedicated per-account estimate/quote logs page with search, filters, CSV export, detailed breakdown view, and clear-all action
- Workshop pricing calculator with per-person/total output and saved templates
- Local SQLite storage per user (`data/pricing_<username>.db`) + auth DB (`data/auth.db`)

## Project Structure
- `app.py`
- `src/`
  - `db.py`
  - `models.py`
  - `pricing.py`
  - `providers/`
    - `base.py`
    - `metals_api.py`
  - `ui/`
    - `dashboard.py`
    - `settings.py`
    - `stones.py`
    - `commissions.py`
    - `workshops.py`
- `data/`
- `scripts/seed.py`
- `.env.example`
- `requirements.txt`

## API Provider
Implemented providers in `src/providers/metals_api.py`:
- **Gold API** (`https://api.gold-api.com/price/{symbol}`)
- **MetalpriceAPI** (alternative)

Provider is selected via `.env` using `PRICE_PROVIDER=goldapi` or `PRICE_PROVIDER=metalpriceapi`.
To swap later, implement another class from `MetalPriceProvider` in `src/providers/base.py` and register it in `_build_provider_from_env()`.

## Setup (Windows PowerShell)
From this project folder:

```powershell
cd c:\Users\Gibgi\jewellery_pricing_app
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env and set PRICE_PROVIDER + matching API key
python -m scripts.seed
streamlit run app.py
```

## How caching works
- Prices are stored in `metal_prices` table.
- App refreshes from API only if cached value is older than `price_cache_ttl_minutes` (default 60).
- If API fails, app falls back to cached prices and shows a warning.

## Troubleshooting API host/DNS issues
- If Gold API host resolution fails, set `GOLDAPI_BASE_URL` or `GOLDAPI_FALLBACK_BASE_URLS` in `.env`.
- Example fallback list: `https://gold-api.com/price,https://www.goldapi.io/api`

## Notes
- Currency is GBP.
- App is fully local; no cloud storage.
- First-run table creation is automatic in `app.py` via `init_db()`, and also available through `scripts/seed.py`.
