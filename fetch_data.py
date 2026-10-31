"""
Download the latest Maharashtra district data from Data.gov.in and save it to
data/maharashtra_mgnrega.json.

Run this on YOUR OWN computer (in India), with .env filled in:

    python fetch_data.py

Then commit and push the new data file. The hosted website reads this file,
so it does not need an API key or a connection to Data.gov.in.
"""

import json
import os
import time

import app

records = app.fetch_live()
os.makedirs(os.path.dirname(app.DATA_FILE), exist_ok=True)

payload = {
    "source": "Data.gov.in - District-wise MGNREGA Data at a Glance (Ministry of Rural Development)",
    "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    "records": records,
}
with open(app.DATA_FILE, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=1)

sample = records[0]
print(f"Saved {len(records)} districts to {app.DATA_FILE}")
print(f"Period of data: {sample.get('month')} {sample.get('fin_year')}")
