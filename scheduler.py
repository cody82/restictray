import asyncio
from sched import scheduler
from typing import Callable, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from storage import Storage, Job
from restic import BackupExecutor
import globals

class JobScheduler:
    """Manages scheduled backup jobs using APScheduler"""
    
    def __init__(self, storage: Storage, log_callback: Optional[Callable[[str], None]] = None):
        """
        Initialize the job scheduler
        
        Args:
            storage: Storage instance for loading jobs
            log_callback: Optional callback function for logging messages
        """
        self.storage = storage
        self.log_callback = log_callback
        self.scheduler = AsyncIOScheduler()
        self.running_executors = {}  # Track running backup executors
    
    def log(self, message: str):
        """Log a message using the callback if available"""
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)
    
    async def run_backup_job(self, job: Job):
        """Execute a backup job"""
        if job.name in self.running_executors:
            self.log(f"Job '{job.name}' is already running, skipping this execution")
            return
        
        self.log(f"Starting scheduled backup job: {job.name}")
        
        # Get repository configuration
        repository = self.storage.get_repository(job.target_repo)
        if not repository:
            self.log(f"Error: Repository '{job.target_repo}' not found for job '{job.name}'")
            return
        
        # Create and run backup executor
        executor = BackupExecutor(
            repository=repository,
            job=job,
            state_update_callback=lambda msg: self.log(f"[{job.name}] {msg}")
        )
        
        self.running_executors[job.name] = executor
        
        # Set tray icon to show backup is running
        globals.tray_icon.setIcon(globals.tray_icon.backup_icon)
        
        try:
            summary = await executor.run()
            
            if summary:
                self.log(f"Job '{job.name}' completed successfully")
            else:
                self.log(f"Job '{job.name}' failed")
        #except Exception as e:
        #    self.log(f"Job '{job.name}' failed with error: {e}")
        finally:
            # Remove from running executors
            if job.name in self.running_executors:
                del self.running_executors[job.name]
            
            # Restore normal tray icon if no more backups are running
            if not self.running_executors:
                globals.tray_icon.setIcon(globals.tray_icon.normal_icon)
    
    def _parse_schedule(self, schedule: str):
        """
        Parse schedule string and return appropriate trigger
        
        Supports:
        - Cron format: "0 2 * * *" (at 2:00 AM every day)
        - Interval format: "interval:1h", "interval:30m", "interval:1d"
        """
        if schedule.startswith("interval:"):
            # Parse interval format
            interval_str = schedule.split(":", 1)[1]
            
            # Parse time units
            if interval_str.endswith("m"):
                minutes = int(interval_str[:-1])
                return IntervalTrigger(minutes=minutes)
            elif interval_str.endswith("h"):
                hours = int(interval_str[:-1])
                return IntervalTrigger(hours=hours)
            elif interval_str.endswith("d"):
                days = int(interval_str[:-1])
                return IntervalTrigger(days=days)
            else:
                raise ValueError(f"Invalid interval format: {interval_str}")
        else:
            # Assume cron format
            return CronTrigger.from_crontab(schedule)
    
    def add_job(self, job: Job):
        """Add a job to the scheduler"""
        if not job.enabled:
            self.log(f"Job '{job.name}' is disabled, not scheduling")
            return
        
        try:
            trigger = self._parse_schedule(job.schedule)
            print(trigger)
            
            self.scheduler.add_job(
                self.run_backup_job,
                trigger=trigger,
                args=[job],
                id=job.name,
                name=job.name,
                replace_existing=False
            )
            
            self.log(f"Scheduled job '{job.name}' with schedule: {job.schedule}")
        except Exception as e:
            self.log(f"Error scheduling job '{job.name}': {e}")
    
    def remove_job(self, job_name: str):
        """Remove a job from the scheduler"""
        try:
            self.scheduler.remove_job(job_name)
            self.log(f"Removed scheduled job: {job_name}")
        except Exception as e:
            self.log(f"Error removing job '{job_name}': {e}")
    
    #def tick(self):
    #    print(f"Tick! The time is: 123")

    def load_and_schedule_all_jobs(self):
        """Load all jobs from storage and schedule them"""
        jobs = self.storage.load_jobs()
        
        # Clear existing jobs
        self.scheduler.remove_all_jobs()
        
        self.start()
        # Schedule each job
        for job in jobs:
            self.add_job(job)
        
        #print(self.scheduler.add_job(self.tick, "interval", seconds=3))
        self.log(f"Loaded and scheduled {len([j for j in jobs if j.enabled])} jobs")
    
    def start(self):
        """Start the scheduler"""
        if not self.scheduler.running:
            self.scheduler.start()
            self.log("Job scheduler started")
    
    def shutdown(self):
        """Shutdown the scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            self.log("Job scheduler stopped")
    
    def get_scheduled_jobs(self):
        """Get list of currently scheduled jobs"""
        return self.scheduler.get_jobs()
    
    def get_job_next_run_time(self, job_name: str):
        """Get the next run time for a specific job"""
        job = self.scheduler.get_job(job_name)
        if job:
            return job.next_run_time
        return None
