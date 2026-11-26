"""APScheduler-based background service for periodic pipeline execution."""
import sys
import time
import signal
from apscheduler.schedulers.blocking import BlockingScheduler
from src.config import AppSettings, setup_logger
from src.load.database import init_db
from src.pipeline import ETLPipeline

logger = setup_logger("scheduler")


def run_job():
    """Scheduled task callback."""
    try:
        pipeline = ETLPipeline()
        summary = pipeline.run()
        logger.info(f"Scheduled job completed. Success: {summary['successes']}, Failed: {summary['failures']}")
    except Exception as e:
        logger.error(f"Unhandled error in scheduled pipeline job: {e}", exc_info=True)


def main():
    settings = AppSettings()
    interval = settings.ingest_interval_minutes
    logger.info(f"Initializing Pune Air Quality Scheduler (interval: {interval} minutes)...")

    # Initialize database
    init_db()

    # Run one initial job immediately upon startup
    logger.info("Triggering initial ingestion job on startup...")
    run_job()

    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_job,
        "interval",
        minutes=interval,
        id="pune_aq_weather_ingest",
        max_instances=1,
        coalesce=True
    )

    def handle_exit(signum, frame):
        logger.info("Shutdown signal received. Stopping scheduler...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    logger.info(f"Scheduler running. Next run scheduled in {interval} minutes. Press Ctrl+C to exit.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
