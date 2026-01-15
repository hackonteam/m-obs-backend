# M-OBS Backend

Backend services for M-OBS (Mantle Observability Stack) - includes API and Worker services.

## Repository

**GitHub:** https://github.com/hackonteam/m-obs-backend  
**Main Repository:** https://github.com/hackonteam/m-obs

## Architecture

The backend consists of two main services:

### 1. **API Service** (FastAPI)
- REST API with 11 endpoints
- Read-only operations (no RPC interaction)
- Serves data to frontend
- Auto-generated OpenAPI docs

### 2. **Worker Service** (Python Async)
- 4 background pipelines:
  - **Provider Probe** (30s) - RPC health monitoring
  - **Block Scanner** (2s) - Transaction ingestion with reorg detection
  - **Metrics Rollup** (60s) - Per-minute metric aggregation
  - **Alert Evaluator** (30s) - Alert rule evaluation

```
┌──────────────┐
│   FastAPI    │───► Supabase PostgreSQL
│     API      │
└──────────────┘
       ▲
       │
┌──────┴──────────┐
│     Worker      │───► Supabase PostgreSQL
│   (4 Pipelines) │
└─────────────────┘
       ▲
       │
┌──────┴──────────┐
│  Mantle Mainnet │
│   RPC Providers │
└─────────────────┘
```

## Stack

- **Language:** Python 3.11+
- **API Framework:** FastAPI
- **Async Runtime:** asyncio
- **Database Client:** asyncpg
- **RPC Client:** aiohttp
- **Configuration:** pydantic-settings

## Prerequisites

- Python 3.11 or higher
- pip or uv package manager
- Supabase PostgreSQL database (with migrations applied)
- Mantle RPC endpoint(s)

## Environment Variables

Create `.env` file in the backend directory:

```bash
# Database
DATABASE_URL=postgresql://user:password@host:port/database

# Mantle RPC Endpoints (comma-separated)
MANTLE_RPC_ENDPOINTS=https://rpc.mantle.xyz,https://mantle.publicnode.com

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:5173,https://yourdomain.com

# Worker Configuration
WORKER_ENABLED_PIPELINES=provider_probe,block_scanner,metrics_rollup,alert_evaluator

# Optional: Sentry for error tracking
SENTRY_DSN=https://your-sentry-dsn
```

## Local Development

### 1. Setup API Service

```bash
cd api

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .

# Run API
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# API will be available at:
# - http://localhost:8000
# - OpenAPI docs: http://localhost:8000/docs
```

### 2. Setup Worker Service

```bash
cd worker

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -e .

# Run worker
python -m src.main

# Worker will start all 4 pipelines
```

### 3. Running Tests

```bash
# API tests
cd api
pytest

# Worker tests
cd worker
pytest
```

## Deployment on Render.com

### Prerequisites

1. **Supabase Database:** Set up and apply migrations from the main repository
2. **GitHub Account:** Connected to Render
3. **Render Account:** Sign up at https://render.com

### Step 1: Create API Service

1. Go to https://dashboard.render.com
2. Click **"New +"** → **"Web Service"**
3. Connect your repository: `https://github.com/hackonteam/m-obs-backend`
4. Configure:
   - **Name:** `m-obs-api`
   - **Region:** Choose closest to your users
   - **Branch:** `main`
   - **Root Directory:** `api`
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -e .`
   - **Start Command:** `uvicorn src.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** Start with `Starter` ($7/month)

5. **Add Environment Variables:**
   ```
   DATABASE_URL=postgresql://user:password@host:port/database
   MANTLE_RPC_ENDPOINTS=https://rpc.mantle.xyz,https://mantle.publicnode.com
   API_HOST=0.0.0.0
   CORS_ORIGINS=https://your-frontend-domain.vercel.app
   SENTRY_DSN=your-sentry-dsn (optional)
   ```

6. Click **"Create Web Service"**
7. Wait for deployment (2-3 minutes)
8. **Note the API URL:** `https://m-obs-api.onrender.com`

### Step 2: Create Worker Service

1. Click **"New +"** → **"Background Worker"**
2. Connect same repository: `https://github.com/hackonteam/m-obs-backend`
3. Configure:
   - **Name:** `m-obs-worker`
   - **Region:** Same as API
   - **Branch:** `main`
   - **Root Directory:** `worker`
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -e .`
   - **Start Command:** `python -m src.main`
   - **Instance Type:** `Starter` ($7/month) or higher for better performance

4. **Add Environment Variables:**
   ```
   DATABASE_URL=postgresql://user:password@host:port/database
   MANTLE_RPC_ENDPOINTS=https://rpc.mantle.xyz,https://mantle.publicnode.com
   WORKER_ENABLED_PIPELINES=provider_probe,block_scanner,metrics_rollup,alert_evaluator
   SENTRY_DSN=your-sentry-dsn (optional)
   ```

5. Click **"Create Background Worker"**
6. Worker will start processing immediately

### Step 3: Verify Deployment

#### Check API Health
```bash
curl https://m-obs-api.onrender.com/health
# Expected: {"status": "ok", "timestamp": "..."}
```

#### Check API Documentation
Visit: `https://m-obs-api.onrender.com/docs`

#### Check Worker Logs
1. Go to Render Dashboard
2. Click on `m-obs-worker`
3. View **"Logs"** tab
4. Look for pipeline startup messages:
   ```
   Starting provider_probe pipeline...
   Starting block_scanner pipeline...
   Starting metrics_rollup pipeline...
   Starting alert_evaluator pipeline...
   ```

#### Check Database Activity
Connect to your Supabase database and verify:
```sql
-- Check if worker is running
SELECT * FROM worker_state WHERE worker_name = 'block_scanner';

-- Check recent transactions
SELECT COUNT(*) FROM txs WHERE created_at > NOW() - INTERVAL '5 minutes';

-- Check provider health samples
SELECT * FROM rpc_health_samples ORDER BY sampled_at DESC LIMIT 10;
```

### Deployment Tips

#### Auto-Deploy on Git Push
Render automatically deploys when you push to the `main` branch.

#### Environment Variables Updates
- Go to service → **"Environment"** tab
- Update variables
- Service will automatically restart

#### Scaling
- **API Service:** Can scale horizontally (multiple instances)
- **Worker Service:** Run single instance to avoid duplicate processing
- Consider upgrading instance types if experiencing performance issues

#### Monitoring
- Use Render's built-in **Metrics** and **Logs**
- Optional: Add Sentry for error tracking
- Monitor database performance in Supabase dashboard

#### Health Checks
Render automatically monitors API health via HTTP checks.

Configure in service settings:
- **Health Check Path:** `/health`
- **Health Check Interval:** 60 seconds

#### Costs (Estimated)
- **API Service:** $7/month (Starter) or $25/month (Standard)
- **Worker Service:** $7/month (Starter) or $25/month (Standard)
- **Total:** ~$14/month minimum

#### Free Tier Option
Render offers free tier with limitations:
- Services spin down after 15 minutes of inactivity
- 750 hours/month shared across services
- Not recommended for production

### Troubleshooting

#### API not starting
- Check build logs for dependency errors
- Verify `DATABASE_URL` is correct
- Ensure port binding uses `$PORT` environment variable

#### Worker not processing
- Check worker logs for connection errors
- Verify RPC endpoints are accessible
- Check `WORKER_ENABLED_PIPELINES` configuration
- Verify database migrations are applied

#### Database connection issues
- Whitelist Render's IP ranges in Supabase (if restricted)
- Check connection string format
- Verify SSL mode if required

#### High memory usage
- Worker processes large batches - consider upgrading instance
- API should be lightweight - check for memory leaks

## API Endpoints

### Health
- `GET /health` - Service health check

### Metrics
- `GET /metrics/overview` - Dashboard metrics (time-series)

### Providers
- `GET /providers/health` - RPC provider health status

### Transactions
- `GET /txs` - List transactions (filtered, paginated)
- `GET /txs/{hash}` - Transaction details

### Contracts
- `GET /contracts` - List watched contracts
- `POST /contracts` - Add contract to watchlist

### Alerts
- `GET /alerts` - List alert rules
- `POST /alerts` - Create alert rule
- `PATCH /alerts/{id}` - Update alert rule
- `DELETE /alerts/{id}` - Delete alert rule

## Worker Pipelines

### 1. Provider Probe (30s interval)
- Monitors RPC endpoint health
- Calculates performance scores
- Detects trace API support
- Updates `rpc_health_samples` table

### 2. Block Scanner (2s interval)
- Scans new blocks from Mantle
- Ingests transaction data
- Handles chain reorganizations
- Updates `txs` and `tx_traces` tables

### 3. Metrics Rollup (60s interval)
- Aggregates per-minute metrics
- Calculates failure rates, gas statistics
- Tracks top errors
- Updates `metrics_minute` table

### 4. Alert Evaluator (30s interval)
- Evaluates alert rules
- Detects threshold violations
- Creates alert events with cooldown
- Updates `alert_events` table

## Development

### Code Structure

```
backend/
├── api/
│   ├── src/
│   │   ├── main.py           # FastAPI app
│   │   ├── config.py         # Configuration
│   │   ├── database.py       # DB connection
│   │   ├── models/           # Pydantic schemas
│   │   └── routes/           # API endpoints
│   ├── pyproject.toml
│   └── README.md
└── worker/
    ├── src/
    │   ├── main.py           # Worker entry point
    │   ├── config.py         # Configuration
    │   ├── database.py       # DB connection
    │   ├── pipelines/        # 4 background pipelines
    │   ├── providers/        # RPC client & manager
    │   ├── decoders/         # Error decoding
    │   └── state/            # State management
    ├── pyproject.toml
    └── README.md
```

### Adding New API Endpoint

```python
# api/src/routes/your_route.py
from fastapi import APIRouter, Depends
from ..database import get_db

router = APIRouter()

@router.get("/your-endpoint")
async def your_endpoint(db = Depends(get_db)):
    # Your logic here
    return {"data": "response"}
```

### Adding New Worker Pipeline

```python
# worker/src/pipelines/your_pipeline.py
import asyncio
from ..database import get_db_pool

async def your_pipeline():
    pool = await get_db_pool()
    while True:
        try:
            # Your pipeline logic
            await asyncio.sleep(30)  # Interval
        except Exception as e:
            print(f"Error: {e}")
            await asyncio.sleep(5)
```

## Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/your-feature`
3. Make changes and test locally
4. Commit: `git commit -m "feat: your feature"`
5. Push: `git push origin feature/your-feature`
6. Create Pull Request

## Team

**HackOn Team Vietnam**

- **Bernie Nguyen** - Founder/Leader/Full-stack/Main developer
- **Thien Vo** - Front-end developer intern
- **Canh Trinh** - Researcher, Back-end developer intern
- **Sharkyz Duong Pham** - Business developer lead
- **Hieu Tran** - Business developer

**Collaboration:** Phu Nhuan Builder

**Contact:**
- Email: work.hackonteam@gmail.com
- Telegram: https://t.me/hackonteam

## License

MIT License - see LICENSE file in main repository

## Links

- **Main Repository:** https://github.com/hackonteam/m-obs
- **Backend Repository:** https://github.com/hackonteam/m-obs-backend
- **Frontend Repository:** https://github.com/hackonteam/m-obs-frontend
- **Supabase:** Your Supabase project URL
- **API Deployment:** https://m-obs-api.onrender.com (your URL)
