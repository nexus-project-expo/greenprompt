"""Record the backup demo video (DEMO_SCRIPT.md flow) with Playwright and the installed Chrome.
Starts its own server on port 8010 with an empty cache and log, so the first question really goes to the model.
    pip install playwright && python scripts/record_demo.py
Writes results/demo_backup.webm."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PORT = 8010
URL = f"http://127.0.0.1:{PORT}"
OUT = ROOT / "results" / "demo_backup.webm"

db = Path(tempfile.gettempdir()) / "gp_record.db"
db.unlink(missing_ok=True)
server = subprocess.Popen([sys.executable, "-m", "uvicorn", "server:app", "--port", str(PORT)], cwd=ROOT,
                          env={**os.environ, "DB_PATH": str(db)}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(200):
        try:
            if json.load(urllib.request.urlopen(URL + "/api/status", timeout=5))["warm"] != "starting":
                break
        except Exception:
            pass
        time.sleep(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        vid_dir = Path(tempfile.mkdtemp())
        ctx = browser.new_context(viewport={"width": 1366, "height": 768}, record_video_dir=str(vid_dir),
                                  record_video_size={"width": 1366, "height": 768})
        pg = ctx.new_page()
        pg.goto(URL)
        pg.wait_for_selector(".pill")
        pg.wait_for_timeout(3000)

        def ask(q, pause=6000, accuracy=False):
            if accuracy:
                pg.click(".switch")
                pg.wait_for_timeout(800)
            pg.click("textarea")
            pg.keyboard.type(q, delay=45)
            pg.wait_for_timeout(500)
            pg.keyboard.press("Enter")
            pg.wait_for_function("document.querySelectorAll('.thinking').length === 0", timeout=150000)
            pg.wait_for_timeout(pause)
            if accuracy:
                pg.click(".switch")

        ask("What is normalization in DBMS?", 8000)
        ask("A shop gives 20% off and then 10% off. Is that 30% off? Show the working.", 7000)
        ask("Explain normalization in DBMS", 6000)
        ask("What is 5% of 800?", 4000)
        ask("What is 50% of 800?", 5000)
        ask("What is the weather in Udupi today?", 5000)
        ask("Define osmosis.", 6000, accuracy=True)
        pg.click("text=Dashboard")
        pg.wait_for_timeout(7000)
        pg.click("text=Evaluation")
        pg.wait_for_timeout(9000)
        pg.click("text=Chat")
        pg.wait_for_timeout(1500)
        video = pg.video.path()
        ctx.close()
        browser.close()
        OUT.parent.mkdir(exist_ok=True)
        shutil.move(video, OUT)
        print("saved", OUT)
finally:
    server.terminate()
