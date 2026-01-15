"""M-OBS Worker main entry point."""
import asyncio
import logging
import signal
import sys

from .config import config
from .database import db
from .pipelines.provider_probe import probe
from .pipelines.block_scanner import scanner
from .pipelines.metrics_rollup import rollup
from .pipelines.alert_evaluator import evaluator

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


class Worker:
    """Main worker orchestrator."""

    def __init__(self) -> None:
        self.shutdown_event = asyncio.Event()
        self.tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """Start all worker pipelines."""
        logger.info(f"Starting M-OBS Worker {config.worker_id}")
        
        # Connect to database
        await db.connect()
        logger.info("Database connected")
        
        # Start pipelines
        self.tasks = [
            asyncio.create_task(probe.run(), name="provider_probe"),
            asyncio.create_task(scanner.run(), name="block_scanner"),
            asyncio.create_task(rollup.run(), name="metrics_rollup"),
            asyncio.create_task(evaluator.run(), name="alert_evaluator"),
        ]
        
        logger.info(f"Started {len(self.tasks)} pipelines")
        
        # Wait for shutdown signal
        await self.shutdown_event.wait()

    async def stop(self) -> None:
        """Stop all pipelines gracefully."""
        logger.info("Shutting down worker...")
        
        # Cancel all tasks
        for task in self.tasks:
            task.cancel()
        
        # Wait for tasks to complete
        await asyncio.gather(*self.tasks, return_exceptions=True)
        
        # Disconnect database
        await db.disconnect()
        logger.info("Worker stopped")

    def handle_signal(self, sig: int) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {sig}")
        self.shutdown_event.set()


async def main() -> None:
    """Main async entry point."""
    worker = Worker()
    
    # Setup signal handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: worker.handle_signal(s))
    
    try:
        await worker.start()
    finally:
        await worker.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
