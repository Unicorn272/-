import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from apscheduler.schedulers.blocking import BlockingScheduler
from functions.dart_collector import collect_and_save

scheduler = BlockingScheduler(timezone="Asia/Seoul")


@scheduler.scheduled_job("cron", day_of_week="sun", hour=2, minute=0)
def weekly_job():
    print("주간 DART 수집 시작")
    collect_and_save()
    print("주간 DART 수집 완료")


if __name__ == "__main__":
    print("스케줄러 시작 (매주 일요일 02:00)")
    scheduler.start()
