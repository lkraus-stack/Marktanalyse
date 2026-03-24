# Markt-Intelligence & Auto-Trading Plattform (Phase 1-10)

Monorepo-Scaffolding fuer ein persoenliches Markt-Intelligence-System mit FastAPI-Backend und Next.js-Frontend.

## Tech-Stack

- Backend: Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), APScheduler, pandas, ta, slowapi, Sentry
- Frontend: Next.js 15, TypeScript (strict), Tailwind CSS 4, shadcn/ui-Basis
- Datenbank: SQLite (lokal) / PostgreSQL via asyncpg (Produktion, Neon)
- Lokale Orchestrierung: Docker Compose + Shell-Skripte

## Projektstruktur

```text
.
|-- backend
|   |-- main.py
|   |-- config.py
|   |-- database.py
|   |-- alembic.ini
|   |-- alembic/
|   |   `-- versions/
|   |-- requirements.txt
|   |-- .env.example
|   |-- models/__init__.py
|   |-- routers/__init__.py
|   |-- schemas/__init__.py
|   `-- services/__init__.py
|-- frontend
|   |-- app
|   |   |-- dashboard/page.tsx
|   |   |-- signale/page.tsx
|   |   |-- sentiment/page.tsx
|   |   |-- alerts/page.tsx
|   |   |-- trading/page.tsx
|   |   |-- einstellungen/page.tsx
|   |   |-- layout.tsx
|   |   `-- page.tsx
|   |-- components
|   |-- lib
|   |-- package.json
|   `-- next.config.ts
|-- scripts
|   |-- dev-start.sh
|   `-- dev-stop.sh
|-- docker-compose.yml
`-- .gitignore
```

## 1) Lokales Setup (ohne Docker)

### Backend starten

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend starten

```bash
cd frontend
npm install
npm run dev
```

Frontend: `http://localhost:3000`  
Backend: `http://localhost:8000`

Optional fuer API-Key-geschuetzte Umgebungen (Frontend):

- `BACKEND_URL` (z. B. `https://your-railway-backend.up.railway.app`)
- `NEXT_PUBLIC_API_KEY` (nur falls Backend `INTERNAL_API_KEY` erwartet)
- `NEXT_PUBLIC_WS_URL` (z. B. `wss://your-railway-backend.up.railway.app/ws/prices`)

## 2) Start per Docker Compose

```bash
./scripts/dev-start.sh
```

Stoppen:

```bash
./scripts/dev-stop.sh
```

## API & Connectivity

- Health-Check: `GET http://localhost:8000/api/health`
- Erwartete Antwort:

```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

Das Frontend fragt auf dem Dashboard `GET /api/health` ab.  
`next.config.ts` rewritet alle `/api/*`-Requests standardmaessig auf `http://localhost:8000/api/*`.

Wichtige Hinweise zur Konfiguration:

- Lokal ohne Docker reicht der Fallback auf `http://localhost:8000`.
- Im Docker-Compose-Setup muss das Frontend `BACKEND_URL=http://backend:8000` bekommen, damit der Rewrite im Container auf den Backend-Service zeigt.
- Auf Vercel muss `BACKEND_URL` auf deine Railway-Backend-URL zeigen, zum Beispiel `https://dein-backend.up.railway.app`.
- Wenn dein Backend mit `INTERNAL_API_KEY` geschuetzt ist, muss im Frontend zusaetzlich `NEXT_PUBLIC_API_KEY` gesetzt sein.

## Datenbankmigrationen (Alembic)

Alembic ist eingerichtet, damit Schemaaenderungen reproduzierbar versioniert sind.
In `development` erstellt die App weiterhin fehlende Tabellen automatisch, in anderen Umgebungen solltest du Migrationen explizit ausfuehren.

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
```

Neue Migration erzeugen:

```bash
alembic revision --autogenerate -m "beschreibung"
```

Wenn bereits eine alte, nicht versionierte SQLite-Datei vorhanden ist, zuerst ein Backup machen und die lokale DB neu erzeugen (`market_intelligence.db` loeschen), dann `alembic upgrade head` und anschliessend Seed ausfuehren.

## Umgebungsvariablen

Vorlagen liegen in `backend/.env.example`:

- `DATABASE_URL`
- `NEON_DATABASE_URL`
- `FRONTEND_URL`
- `REDIS_URL`
- `INTERNAL_API_KEY`
- `SENTRY_DSN`
- `SENTRY_TRACES_SAMPLE_RATE`
- `FINNHUB_API_KEY`
- `COINGECKO_API_KEY`
- `ALPHA_VANTAGE_API_KEY`
- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USER_AGENT`
- `PERPLEXITY_API_KEY`
- `PERPLEXITY_DAILY_BUDGET_USD`
- `PERPLEXITY_REQUEST_COST_USD`
- `FINBERT_ENABLED`
- `SENTIMENT_BATCH_SIZE`
- `SENTIMENT_PROCESS_LIMIT`
- `SIGNAL_WEIGHT_SENTIMENT`
- `SIGNAL_WEIGHT_TECHNICAL`
- `SIGNAL_WEIGHT_VOLUME`
- `SIGNAL_WEIGHT_MOMENTUM`
- `ALERT_COOLDOWN_MINUTES`
- `ALERT_DELIVERY_RETRIES`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM_EMAIL`
- `SMTP_USE_TLS`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `ALPACA_API_KEY`
- `ALPACA_SECRET_KEY`
- `ALPACA_PAPER_BASE_URL`
- `ALPACA_LIVE_BASE_URL`
- `KRAKEN_API_KEY`
- `KRAKEN_SECRET_KEY`
- `KRAKEN_BASE_URL`
- `AUTO_TRADER_MODE`
- `AUTO_IS_LIVE`
- `AUTO_MAX_POSITION_SIZE_USD`
- `AUTO_MAX_POSITIONS`
- `AUTO_MIN_SIGNAL_STRENGTH`
- `AUTO_STOP_LOSS_PCT`
- `AUTO_TAKE_PROFIT_PCT`
- `AUTO_DOUBLE_CONFIRM_THRESHOLD_EUR`
- `AUTO_DAILY_LOSS_LIMIT_EUR`
- `AUTO_MAX_TRADES_PER_DAY`
- `BINANCE_API_KEY`
- `ENABLE_SCHEDULER` (default `false`)

## Hinweise fuer Phase 2+

- Router/Services/Models/Schemas sind als Erweiterungspunkte vorbereitet.
- SQLite kann spaeter auf PostgreSQL migriert werden, ohne Frontend-Aenderungen.
- Cache/Scheduler/Signal-Pipeline lassen sich im bestehenden modularen Monolith sauber erweitern.

## Phase 3 Market Data APIs

- `GET /api/prices/{symbol}`: neuester gespeicherter 1m Preis
- `GET /api/prices/{symbol}/history?timeframe=1d&limit=100`: Historie pro Zeitrahmen
- `GET /api/assets`: alle Assets inklusive letztem Preis (`scope=all|watchlist|holding`)
- `POST /api/assets`: neues Asset anlegen (Default `watch_status=watchlist`)
- `PATCH /api/assets/{symbol}/watch`: Asset als `none|watchlist|holding` markieren
- `POST /api/assets/import`: CSV-Import fuer Watchlist/Holdings (Bulk Upsert)
- `GET /api/assets/import-template`: CSV-Header + Beispielzeile

## Phase 4 Social Data APIs

- `GET /api/social/{symbol}/feed`: neueste Social- und News-Eintraege
- `GET /api/social/{symbol}/stats`: Erwaehnungs- und Sentimentstatistik
- `GET /api/market-summary`: neueste Perplexity-Marktzusammenfassung

## Phase 5 Sentiment APIs

- `GET /api/sentiment/{symbol}`: aktueller Sentiment-Snapshot (1h/1d-Mentions)
- `GET /api/sentiment/{symbol}/history?timeframe=1h&limit=48`: Sentimentverlauf
- `GET /api/sentiment/overview`: alle Assets, nach `|score|` sortiert

## Phase 7 Signal APIs

- `GET /api/signals`: alle aktiven Signale, nach Staerke sortiert
- `GET /api/signals/{symbol}`: letztes aktives (oder zuletzt erzeugtes) Signal fuer ein Asset
- `GET /api/signals/{symbol}/history?limit=50`: Signal-Historie pro Asset
- `GET /api/signals/leaderboard`: Top 10 Buy + Top 10 Sell
- `GET /api/signals/recommendations?direction=all&include_hold=true&min_strength=0&limit=20`: Tool-Vorschlaege/Candidates (BUY/SELL/HOLD)
- `GET /api/signals/pipeline-status`: Readiness + Blocker der Signal-Pipeline (inkl. M1/H1 Coverage)
- `POST /api/signals/bootstrap`: manueller End-to-End Lauf (H1 Backfill -> M1 Backfill -> Prices -> Sentiment -> Aggregation -> Signals)

## Keine Signale? Quickstart

Wenn aktuell keine Signale angezeigt werden, sind fast immer `price_data` und/oder `aggregated_sentiments` leer.

1. API-Keys in `backend/.env` setzen (mindestens Finnhub fuer Aktien, optional Binance/CoinGecko fuer Krypto).
2. Entweder Scheduler aktivieren:
   - `ENABLE_SCHEDULER=true`
3. Oder manuell einen Pipeline-Lauf starten:
   - API: `POST /api/signals/bootstrap`
   - CLI: `python backend/scripts/bootstrap_pipeline.py`
4. Status pruefen:
   - `GET /api/signals/pipeline-status`
5. Erwartung:
   - Fuer Krypto sollten nach dem Bootstrap genug M1/H1 Candles vorhanden sein, damit Momentum/Volume/Technik nicht mehr dauerhaft neutral sind.
   - Fuer Aktien nutzt das System Finnhub (Quote/News). Falls Finnhub-Candle-Endpunkte `403` liefern, greift automatisch ein Yahoo-Chart-Fallback fuer M1/H1-Backfill.

## Phase 8 Alert APIs

- `GET /api/alerts`: Alert-Regeln (optional gefiltert)
- `POST /api/alerts`: neue Alert-Regel erstellen
- `GET /api/alerts/{alert_id}`: Detail einer Alert-Regel
- `PATCH /api/alerts/{alert_id}`: Alert-Regel aktualisieren (z. B. `is_enabled`)
- `DELETE /api/alerts/{alert_id}`: Alert-Regel loeschen
- `GET /api/alerts/history?limit=100`: globaler History-Feed
- `GET /api/alerts/{alert_id}/history`: History pro Alert

## Phase 9 Paper Trading APIs

- `GET /api/trading/account`: Paper-Account Uebersicht (Alpaca)
- `GET /api/trading/positions`: aktuelle Paper-Positionen
- `GET /api/trading/orders?limit=100`: lokale Trade/Order-Historie
- `POST /api/trading/orders`: manuelle Paper-Order einreichen
- `GET /api/trading/orders/{trade_id}`: Order-Detail
- `POST /api/trading/orders/{trade_id}/confirm`: Semi-Auto Pending-Order bestaetigen
- `DELETE /api/trading/orders/{trade_id}`: Order stornieren
- `GET /api/trading/portfolio/history?limit=168`: Equity-Snapshots
- `GET /api/trading/performance`: Performance-Metriken
- `GET /api/trading/settings`: AutoTrader-Settings
- `PATCH /api/trading/settings`: AutoTrader-Settings aktualisieren
- `POST /api/trading/run/evaluate`: Buy-Zyklus manuell triggern
- `POST /api/trading/run/exits`: Exit-Zyklus manuell triggern
- `POST /api/trading/run/snapshot`: Portfolio-Snapshot manuell triggern

## Phase 10 Live & Security APIs

- `GET /api/trading/status`: Broker- und Live-Sicherheitsstatus
- `GET /api/health`: erweiterter Health-Check (DB, Redis, API-Key-Status)

## Scheduler Jobs (aktuell)

- Preise: Krypto alle 2 Min, Aktien waehrend Marktzeiten
- Social/News: alle 30 Min, Perplexity alle 4h
- Sentiment: FinVADER 15 Min, FinBERT 60 Min, Aggregation 1h/1d
- Signale: Generierung alle 30 Min, Verfallpruefung stuendlich
- Alerts: Auswertung alle 5 Min (inkl. Cooldown/History/Delivery)
- Paper Trading: Buy-Check alle 30 Min, Exit-Check alle 15 Min, Snapshot stuendlich

## Produktionshaertung (Phase 10)

- API-Key Middleware fuer `/api/*` (Header `X-API-Key`, wenn `INTERNAL_API_KEY` gesetzt)
- Rate Limiting via slowapi:
  - Daten-Endpunkte: default `60/min`
  - Trading-Endpunkte: `10/min`
- Globaler Exception Handler mit strukturiertem JSON-Logging
- Sentry-Integration optional via `SENTRY_DSN`
- Multi-Broker AutoTrader:
  - Aktien -> Alpaca
  - Krypto (live) -> Kraken
  - Sicherheitsregeln: Double-Confirm ueber 500 EUR, Tagesverlustlimit, max Trades/Tag

## SQLite -> PostgreSQL Migration

Migrationsskript:

```bash
cd backend
source .venv/bin/activate
python scripts/migrate_sqlite_to_postgres.py \
  --source-url "sqlite+aiosqlite:///./market_intelligence.db" \
  --target-url "postgresql://user:password@host/db?sslmode=require" \
  --truncate-target
```

Danach:

```bash
alembic upgrade head
```

## Deployment

- Backend Dockerfile: `backend/Dockerfile`
- Railway Config: `railway.toml`
- Lokale Prod-Tests: `docker-compose.prod.yml`

### Railway Backend

Pflichtwerte fuer ein lauffaehiges Deployment:

- `DATABASE_URL`
- `FRONTEND_URL`

Empfohlen bzw. je nach Feature noetig:

- `REDIS_URL`
- `ENABLE_SCHEDULER=true`
- `FINNHUB_API_KEY` fuer Aktienpreise und News
- `INTERNAL_API_KEY` optional fuer geschuetzte API-Zugriffe
- weitere Broker-/KI-Keys je nach verwendeten Bereichen (`ALPACA_*`, `KRAKEN_*`, `AI_API_KEY` bzw. `PERPLEXITY_API_KEY`)

Wichtig: Das Backend-Container-Image fuehrt beim Start bereits `alembic upgrade head` aus. Wenn du ausserhalb des Docker-Deployments startest, musst du Migrationen weiterhin selbst ausfuehren.

### Vercel Frontend

Setze auf Vercel mindestens diese Variablen:

- `BACKEND_URL=https://dein-backend.up.railway.app`
- `NEXT_PUBLIC_WS_URL=wss://dein-backend.up.railway.app/ws/prices`
- `NEXT_PUBLIC_API_KEY=...` nur falls das Backend `INTERNAL_API_KEY` verlangt

Das Frontend nutzt die Next.js-Rewrites in `frontend/next.config.ts`. Eine separate `vercel.json` ist dafuer aktuell nicht noetig.

Start lokaler Production-Stack:

```bash
docker compose -f docker-compose.prod.yml up --build
```

## WebSocket Streams

- `ws://localhost:8000/ws/prices` liefert:
  - Preisupdates (`type=price_update`)
  - Alert-Events (`type=alert_triggered`, `channel=alerts`)

Fuer Deployments solltest du `NEXT_PUBLIC_WS_URL` explizit setzen. Ohne diese Variable verbindet sich das Frontend ausserhalb von localhost absichtlich nicht automatisch per WebSocket, damit keine fehlerhaften localhost-Verbindungen im Browser entstehen.
