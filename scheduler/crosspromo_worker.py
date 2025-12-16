"""
Cross Promo Worker - Background job processor for cross promo automation.
Polls for due jobs every 10 seconds, claims them atomically, and executes.
Safe for multi-instance deployment via FOR UPDATE SKIP LOCKED.
"""
import time
import threading
from core.logging import get_logger
from domains.crosspromo import repo, service

logger = get_logger(__name__)

POLL_INTERVAL_SECONDS = 10
BATCH_SIZE = 20


def process_jobs():
    """Claim and process due jobs."""
    jobs = repo.claim_due_jobs(batch_size=BATCH_SIZE)
    
    if not jobs:
        return 0
    
    processed = 0
    for job in jobs:
        job_id = job['id']
        job_type = job['job_type']
        tenant_id = job['tenant_id']
        
        try:
            logger.info(f"Processing job {job_id} type={job_type} tenant={tenant_id}")
            result = service.send_job(job)
            
            if result.get('success'):
                repo.mark_sent(job_id)
                logger.info(f"Job {job_id} completed successfully")
            else:
                error = result.get('error', 'Unknown error')
                repo.mark_failed(job_id, error)
                logger.warning(f"Job {job_id} failed: {error}")
            
            processed += 1
            
        except Exception as e:
            logger.exception(f"Exception processing job {job_id}: {e}")
            repo.mark_failed(job_id, str(e))
            processed += 1
    
    return processed


def run_worker():
    """Main worker loop. Runs indefinitely, polling every 10 seconds."""
    logger.info("Cross Promo worker started")
    
    while True:
        try:
            processed = process_jobs()
            if processed > 0:
                logger.info(f"Processed {processed} job(s)")
        except Exception as e:
            logger.exception(f"Error in worker loop: {e}")
        
        time.sleep(POLL_INTERVAL_SECONDS)


def start_worker_thread():
    """Start the worker in a background thread."""
    thread = threading.Thread(target=run_worker, daemon=True, name="crosspromo-worker")
    thread.start()
    logger.info("Cross Promo worker thread started")
    return thread


if __name__ == "__main__":
    run_worker()
