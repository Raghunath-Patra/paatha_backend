# services/scheduler_service.py - Background Scheduler for Auto-Grading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import logging
import os
from sqlalchemy.orm import Session
from config.database import SessionLocal
from services.auto_grading_service import auto_grading_service

logger = logging.getLogger(__name__)

class SchedulerService:
    """Background scheduler service for automatic tasks"""
    
    def __init__(self):
        self.scheduler = None
        self.is_running = False
        
    def start(self):
        """Start the background scheduler"""
        if self.scheduler is not None:
            logger.warning("Scheduler is already running")
            return
            
        try:
            # Configure scheduler with thread pool
            executors = {
                'default': ThreadPoolExecutor(max_workers=3)
            }
            
            job_defaults = {
                'coalesce': True,          # Combine multiple pending executions into one
                'max_instances': 1,        # Only one instance of each job at a time
                'misfire_grace_time': 300  # 5 minutes grace time for missed jobs
            }
            
            self.scheduler = BackgroundScheduler(
                executors=executors,
                job_defaults=job_defaults,
                timezone='UTC'
            )
            
            # Add auto-grading job
            self._add_auto_grading_job()
            
            # Start the scheduler
            self.scheduler.start()
            self.is_running = True
            
            logger.info("✅ Background scheduler started successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to start scheduler: {str(e)}")
            raise
    
    def stop(self):
        """Stop the background scheduler"""
        if self.scheduler is None:
            return
            
        try:
            self.scheduler.shutdown(wait=True)
            self.scheduler = None
            self.is_running = False
            logger.info("✅ Background scheduler stopped successfully")
            
        except Exception as e:
            logger.error(f"❌ Error stopping scheduler: {str(e)}")
    
    def _add_auto_grading_job(self):
        """Add auto-grading job to scheduler"""
        try:
            # Get grading interval from environment (default: every 10 minutes)
            grading_interval_minutes = int(os.getenv("AUTO_GRADING_INTERVAL_MINUTES", "10"))
            
            # Add interval-based job (runs every X minutes)
            self.scheduler.add_job(
                func=self._run_auto_grading_job,
                trigger=IntervalTrigger(minutes=grading_interval_minutes),
                id='auto_grading_interval',
                name='Auto Grade Quizzes (Interval)',
                replace_existing=True
            )
            
            # Also add a cron job that runs at specific times (useful for peak hours)
            # Run at minute 5, 15, 25, 35, 45, 55 of every hour
            self.scheduler.add_job(
                func=self._run_auto_grading_job,
                trigger=CronTrigger(minute='5,15,25,35,45,55'),
                id='auto_grading_cron',
                name='Auto Grade Quizzes (Scheduled)',
                replace_existing=True
            )
            
            logger.info(f"✅ Auto-grading jobs scheduled:")
            logger.info(f"   - Interval: Every {grading_interval_minutes} minutes")
            logger.info(f"   - Cron: At minutes 5,15,25,35,45,55 of every hour")
            
        except Exception as e:
            logger.error(f"❌ Error adding auto-grading job: {str(e)}")
            raise
    
    def _run_auto_grading_job(self):
        """Execute auto-grading job"""
        job_start_time = datetime.utcnow()
        logger.info(f"🚀 Starting auto-grading job at {job_start_time}")
        
        db = None
        try:
            # Create database session
            db = SessionLocal()
            
            # Run auto-grading
            result = auto_grading_service.run_auto_grading_batch(db)
            
            # Log results
            job_end_time = datetime.utcnow()
            duration = (job_end_time - job_start_time).total_seconds()
            
            logger.info(f"✅ Auto-grading job completed in {duration:.2f} seconds:")
            logger.info(f"   - Processed quizzes: {result.get('processed_quizzes', 0)}")
            logger.info(f"   - Graded submissions: {result.get('total_submissions', 0)}")
            logger.info(f"   - Tokens used: {result.get('total_tokens', 0)}")
            
            if result.get('results'):
                for quiz_result in result['results']:
                    if quiz_result.get('error'):
                        logger.error(f"   ❌ Quiz {quiz_result['quiz_id']}: {quiz_result['error']}")
                    else:
                        logger.info(f"   ✅ Quiz {quiz_result.get('quiz_title', quiz_result['quiz_id'])}: "
                                   f"{quiz_result.get('graded_submissions', 0)} submissions, "
                                   f"{quiz_result.get('total_tokens', 0)} tokens")
            
        except Exception as e:
            logger.error(f"❌ Error in auto-grading job: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            
        finally:
            if db:
                try:
                    db.close()
                except:
                    pass
    
    def get_job_status(self):
        """Get status of scheduled jobs"""
        if not self.scheduler:
            return {"status": "not_running", "jobs": []}
        
        jobs = []
        for job in self.scheduler.get_jobs():
            next_run = job.next_run_time
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": next_run.isoformat() if next_run else None,
                "trigger": str(job.trigger)
            })
        
        return {
            "status": "running" if self.is_running else "stopped",
            "jobs": jobs
        }
    
    def trigger_auto_grading_now(self):
        """Manually trigger auto-grading job"""
        if not self.scheduler:
            raise Exception("Scheduler is not running")
        
        try:
            # Add a one-time job to run immediately
            self.scheduler.add_job(
                func=self._run_auto_grading_job,
                trigger='date',  # Run once at specified time
                run_date=datetime.utcnow() + timedelta(seconds=5),  # Run in 5 seconds
                id='manual_auto_grading',
                name='Manual Auto Grade Trigger',
                replace_existing=True
            )
            
            logger.info("✅ Manual auto-grading job triggered")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error triggering manual auto-grading: {str(e)}")
            return False

# Singleton instance
scheduler_service = SchedulerService()