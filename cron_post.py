import schedule
import time
import subprocess
from datetime import datetime

def job():
    today = datetime.now().weekday()
    # 0=Monday, 2=Wednesday, 4=Friday
    if today in [0, 2, 4]:
        print(f"Running social post — {datetime.now().strftime('%A %B %d %Y %H:%M')}")
        try:
            subprocess.run(["python", "social_post.py"], check=True)
        except Exception as e:
            print(f"Post failed: {e}")
    else:
        print(f"Not a post day — skipping ({datetime.now().strftime('%A')})")

# Run every day at 9:00 AM — script checks internally if it's Mon/Wed/Fri
schedule.every().day.at("09:00").do(job)

print("Fenkell RX scheduler started — posts run Mon/Wed/Fri at 9:00 AM")
print(f"Server time now: {datetime.now().strftime('%A %B %d %Y %H:%M')}")

while True:
    schedule.run_pending()
    time.sleep(60)
