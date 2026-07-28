import logging
from apscheduler.schedulers.background import BackgroundScheduler
from app.db import get_task_schedules, save_task_schedule
from app.scanner import scan_subnet, crawl_cdp, check_all_switches_status
from app.collector import run_full_collection

logger = logging.getLogger("ciscotools.scheduler")
scheduler = BackgroundScheduler()

def run_task_discovery():
    logger.info("⏰ [SCHEDULED TASK] Running Network Discovery...")
    try:
        scan_subnet()
        crawl_cdp()
        run_full_collection()
        save_task_schedule("task_discovery", update_last_run=True)
    except Exception as e:
        logger.error(f"Error in task_discovery: {e}")

def run_task_collector():
    logger.info("⏰ [SCHEDULED TASK] Running Switch Data Refresh (Full Sequence)...")
    try:
        scan_subnet()
        crawl_cdp()
        run_full_collection()
        save_task_schedule("task_collector", update_last_run=True)
    except Exception as e:
        logger.error(f"Error in task_collector: {e}")

def run_task_status():
    try:
        check_all_switches_status()
        save_task_schedule("task_status", update_last_run=True)
    except Exception as e:
        logger.error(f"Error in task_status: {e}")

TASK_FUNCTIONS = {
    "task_discovery": run_task_discovery,
    "task_collector": run_task_collector,
    "task_status": run_task_status,
}

def reload_task_jobs():
    """Reload or reschedule APScheduler jobs from SQLite task_schedules table."""
    tasks = get_task_schedules()
    for task in tasks:
        t_id = task["task_id"]
        enabled = task["enabled"]
        interval = task["interval_minutes"] or 60
        fn = TASK_FUNCTIONS.get(t_id)

        if not fn:
            continue

        if enabled and interval > 0:
            scheduler.add_job(fn, 'interval', minutes=interval, id=t_id, replace_existing=True)
            logger.info(f"✔ Scheduled '{t_id}' every {interval} minute(s).")
        else:
            if scheduler.get_job(t_id):
                scheduler.remove_job(t_id)
                logger.info(f"⏸ Paused/Removed scheduled task '{t_id}'.")

def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        reload_task_jobs()
        logger.info("✔ Background scheduler started successfully.")

def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("✔ Background scheduler stopped.")
