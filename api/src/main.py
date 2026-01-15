"""M-OBS API main entry point."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import config
from .database import db
from .routes import health, providers, transactions, contracts, metrics, alerts

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting M-OBS API")
    logger.info(f"Attempting to connect to database...")
    
    try:
        await db.connect()
        logger.info("Database connected successfully")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        logger.error("Application will continue but database operations will fail")
        # Don't raise - allow app to start even if DB connection fails
        # This helps with debugging on Render
    
    yield
    
    # Shutdown
    logger.info("Shutting down M-OBS API")
    try:
        await db.disconnect()
        logger.info("Database disconnected")
    except Exception as e:
        logger.error(f"Error disconnecting database: {e}")


# Create FastAPI app
app = FastAPI(
    title="M-OBS API",
    description="Mantle Observability Stack REST API",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(health.router)
app.include_router(metrics.router)
app.include_router(providers.router)
app.include_router(transactions.router)
app.include_router(contracts.router)
app.include_router(alerts.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "M-OBS API",
        "version": "0.1.0",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "src.main:app",
        host=config.api_host,
        port=config.api_port,
        reload=True,
        log_level=config.log_level.lower(),
    )
