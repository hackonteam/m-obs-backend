"""Worker configuration management."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerConfig(BaseSettings):
    """Worker configuration from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase
    supabase_url: str
    supabase_service_key: str

    # Worker Identity
    worker_id: str = "worker-1"
    chain_id: int = 5000

    # Polling Intervals (seconds)
    poll_interval_probe: int = 30
    poll_interval_scanner: int = 2
    poll_interval_rollup: int = 60
    poll_interval_alerts: int = 30

    # Concurrency
    max_concurrent_probes: int = 3
    block_batch_size: int = 10
    trace_queue_size: int = 100
    max_traces_per_minute: int = 10

    # Retry & Timeouts
    rpc_timeout_default: int = 5
    rpc_timeout_trace: int = 10
    max_retries: int = 3
    backoff_base: int = 2

    # Logging
    log_level: str = "INFO"


config = WorkerConfig()
