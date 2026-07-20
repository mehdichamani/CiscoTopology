import logging
from apscheduler.schedulers.background import BackgroundScheduler
from app.db import get_settings
from app.scanner import crawl_cdp, check_all_switches_status
from app.collector import run_full_collection

logger = logging.getLogger("ciscotools.scheduler")
scheduler = BackgroundScheduler()

def scheduled_job():
    logger.info("⏰ Automated Background Refresh Triggered!")
    try:
        crawl_cdp()
        run_full_collection()
    except Exception as e:
        logger.error(f"Error in background scheduled job: {e}")

def status_job():
    try:
        check_all_switches_status()
    except Exception as e:
        logger.error(f"Error in status check job: {e}")

def start_scheduler():
    if not scheduler.running:
        settings = get_settings()
        hours = settings.get("auto_refresh_hours", 24) or 24
        scheduler.add_job(scheduled_job, 'interval', hours=hours, id='daily_refresh', replace_existing=True)
        scheduler.add_job(status_job, 'interval', minutes=1, id='minutely_status_check', replace_existing=True)
        scheduler.start()
        logger.info(f"✔ Background scheduler started (Full refresh: {hours}h, Status check: 1m).")

def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("✔ Background scheduler stopped.")
