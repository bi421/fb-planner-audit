import os
import sys
import threading
import time

import schedule

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from core.db import init_db
from bot.app import app
from core.policy_updater import update


def _run_scheduler():
    schedule.every().monday.at("09:00").do(update)
    while True:
        schedule.run_pending()
        time.sleep(60)


def main():
    init_db()
    t = threading.Thread(target=_run_scheduler, daemon=True)
    t.start()
    app.run(host='0.0.0.0', port=5000, debug=True)


if __name__ == "__main__":
    main()
