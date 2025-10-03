from celery import Celery
from celery.schedules import crontab

celery_app = Celery('s3_worker',
                    broker='redis://localhost:6379/0',
                    backend = 'redis://localhost:6379/0',
                    include = ['s3_worker.worker2','s3_worker.worker']
 # “Hey, when you start, also import the module s3_worker.worker2 because that’s where my tasks are defined.”                    
                    )

celery_app.conf.timezone = 'UTC' #Celery Beat needs a timezone when running scheduled tasks.

celery_app.conf.beat_schedule = {
    'calculate-trending-every-six-hours':{
    'task' : 's3_worker.worker2.calculate_trending',
    'schedule' : crontab(minute=0, hour='*/6'),
    },
}
"""
task: full dotted path to your task (s3_worker.worker2.calculate_trending). Celery finds it because of the include.
schedule: tells Beat when to run it.
Celery provides crontab just like Linux cron.
minute=0, hour='*/6' means run every 6 hours at the top of the hour → 00:00, 06:00, 12:00, 18:00.
"""