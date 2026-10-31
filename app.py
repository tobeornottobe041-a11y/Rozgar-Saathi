"""
Rozgar Saathi - Maharashtra district employment viewer (prototype)

Flask backend that serves district-wise MGNREGA data (Data.gov.in resource
"District-wise MGNREGA Data at a Glance") to the frontend (index.html).

Two ways to get the data:
  1. FILE (default, best for hosting): data/maharashtra_mgnrega.json, created by
     running `python fetch_data.py` on a computer in India. No API key needed on
     the server, and it works even if the server cannot reach Data.gov.in.
  2. LIVE: set USE_LIVE=1 (needs DATA_GOV_API_KEY and RESOURCE_ID).

API keys are read from the environment / .env file, never written in code.
"""

import json
import os
import re
import time

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API_KEY = os.getenv("DATA_GOV_API_KEY", "").strip()
RESOURCE_ID = os.getenv("RESOURCE_ID", "").strip()
STATE_FIELD = os.getenv("STATE_FIELD", "state_name")
DISTRICT_FIELD = os.getenv("DISTRICT_FIELD", "district_name")
STATE_VALUE = os.getenv("STATE_VALUE", "MAHARASHTRA")
FIN_YEAR = os.getenv("FIN_YEAR", "").strip()      # optional, e.g. 2025-2026
USE_LIVE = os.getenv("USE_LIVE", "0").strip() == "1"
DATA_FILE = os.getenv("DATA_FILE", os.path.join(BASE_DIR, "data", "maharashtra_mgnrega.json"))
CACHE_SECONDS = int(os.getenv("CACHE_SECONDS", "3600"))
BASE_URL = "https://api.data.gov.in/resource/"

# Financial year runs April -> March
MONTH_RANK = {m: i for i, m in enumerate(
    ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"])}

app = Flask(__name__, static_folder=BASE_DIR, static_url_path="")

# Used only so the district box still works if no data is available.
MAHARASHTRA_DISTRICTS = [
    "Ahmednagar", "Akola", "Amravati", "Aurangabad", "Beed", "Bhandara",
    "Buldhana", "Chandrapur", "Dhule", "Gadchiroli", "Gondia", "Hingoli",
    "Jalgaon", "Jalna", "Kolhapur", "Latur", "Mumbai City", "Mumbai Suburban",
    "Nagpur", "Nanded", "Nandurbar", "Nashik", "Osmanabad", "Palghar",
    "Parbhani", "Pune", "Raigad", "Ratnagiri", "Sangli", "Satara",
    "Sindhudurg", "Solapur", "Thane", "Wardha", "Washim", "Yavatmal",
]

_cache = {"time": 0.0, "records": []}


def norm(text):
    """Lower-case and strip everything except letters/digits for matching."""
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def safe_message(exc):
    """Error text that is safe to show to visitors: never contains the key or URL."""
    if isinstance(exc, requests.HTTPError):
        code = exc.response.status_code if exc.response is not None else "unknown"
        return f"Data.gov.in returned an error (HTTP {code})."
    if isinstance(exc, requests.RequestException):
        return "The server could not reach Data.gov.in."
    if isinstance(exc, RuntimeError):
        text = str(exc)
        return text.replace(API_KEY, "***") if API_KEY else text
    return "Something went wrong while loading the data."


def get_with_retry(url, params, headers, attempts=3):
    """data.gov.in can be slow, so wait longer and retry a few times."""
    last = None
    for i in range(attempts):
        try:
            return requests.get(url, params=params, headers=headers, timeout=(15, 120))
        except (requests.Timeout, requests.ConnectionError) as exc:
            last = exc
            time.sleep(2 * (i + 1))
    raise last


def candidate_years():
    """Financial years to try, newest first (e.g. 2026-2027, 2025-2026, ...)."""
    if FIN_YEAR:
        return [FIN_YEAR]
    t = time.localtime()
    start = t.tm_year if t.tm_mon >= 4 else t.tm_year - 1
    return [f"{y}-{y + 1}" for y in range(start, start - 4, -1)]


def download(url, headers, fin_year):
    """Download every Maharashtra row for one financial year."""
    records, offset, page = [], 0, 100
    while True:
        params = {
            "api-key": API_KEY, "format": "json", "limit": page, "offset": offset,
            f"filters[{STATE_FIELD}]": STATE_VALUE.upper(),
            "filters[fin_year]": fin_year,
        }
        resp = get_with_retry(url, params, headers)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("error"):
            raise RuntimeError(f"Data.gov.in says: {payload['error']}")
        batch = payload.get("records", [])
        records.extend(batch)
        total = int(payload.get("total", len(records)) or 0)
        offset += page
        if not batch or offset >= total or offset >= 5000:
            break
    return [r for r in records if norm(r.get(STATE_FIELD, "")) == norm(STATE_VALUE)]


def latest_per_district(records):
    """The dataset has one row per district per month; keep the newest month."""
    best = {}
    for r in records:
        key = norm(r.get(DISTRICT_FIELD, ""))
        if not key:
            continue
        rank = MONTH_RANK.get(str(r.get("month", "")).strip()[:3].title(), -1)
        if key not in best or rank > best[key][0]:
            best[key] = (rank, r)
    return [v[1] for v in best.values()]


def fetch_live():
    """Latest-month Maharashtra record for each district, straight from the API."""
    if not API_KEY:
        raise RuntimeError("DATA_GOV_API_KEY is missing. Add it to the .env file.")
    if not RESOURCE_ID:
        raise RuntimeError("RESOURCE_ID is missing. Add the dataset's resource ID to the .env file.")

    url = BASE_URL + RESOURCE_ID
    headers = {"User-Agent": "Mozilla/5.0 (compatible; RozgarSaathi/1.0)", "Accept": "application/json"}
    records = []
    for fy in candidate_years():
        records = download(url, headers, fy)
        if records:
            break
    if not records:
        raise RuntimeError("The API returned no Maharashtra records for the recent financial years.")
    return latest_per_district(records)


def load_file():
    with open(DATA_FILE, encoding="utf-8") as f:
        payload = json.load(f)
    records = payload.get("records", []) if isinstance(payload, dict) else payload
    if not records:
        raise RuntimeError("The saved data file is empty. Run fetch_data.py again.")
    return records


def fetch_records():
    """District records, from the saved file if present, otherwise live (cached)."""
    now = time.time()
    if _cache["records"] and now - _cache["time"] < CACHE_SECONDS:
        return _cache["records"]
    if not USE_LIVE and os.path.exists(DATA_FILE):
        records = load_file()
    else:
        records = fetch_live()
    _cache.update(time=now, records=records)
    return records


def api_error(message, status=502):
    return jsonify({"ok": False, "error": message}), status


@app.route("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/api/health")
def health():
    return jsonify({
        "ok": True,
        "mode": "live" if USE_LIVE or not os.path.exists(DATA_FILE) else "file",
        "data_file_found": os.path.exists(DATA_FILE),
    })


@app.route("/api/debug")
def debug():
    """Shows a few raw records from the live API (use on your own computer)."""
    try:
        url = BASE_URL + RESOURCE_ID
        params = {"api-key": API_KEY, "format": "json", "limit": 3}
        resp = get_with_retry(url, params, {"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        try:
            data = resp.json()
        except ValueError:
            return jsonify({"http_status": resp.status_code, "not_json": True})
        return jsonify({
            "http_status": resp.status_code,
            "title": data.get("title"),
            "total_records_in_dataset": data.get("total"),
            "columns": [f.get("id") for f in data.get("field", [])],
            "first_records": data.get("records", [])[:3],
            "error": data.get("error") or data.get("message"),
        })
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": safe_message(exc)})


@app.route("/api/districts")
def districts():
    """List of district names (from the real data if possible)."""
    try:
        records = fetch_records()
        names = sorted({str(r.get(DISTRICT_FIELD, "")).strip() for r in records if r.get(DISTRICT_FIELD)})
        if names:
            return jsonify({"ok": True, "source": "live", "districts": names})
        raise RuntimeError("No Maharashtra records were found.")
    except Exception as exc:  # noqa: BLE001 - we want to show any failure to the UI
        return jsonify({
            "ok": False,
            "source": "fallback",
            "error": safe_message(exc),
            "districts": MAHARASHTRA_DISTRICTS,
        })


@app.route("/api/employment")
def employment():
    """Latest employment record for one district: /api/employment?district=Pune"""
    query = norm(request.args.get("district", ""))
    if not query:
        return api_error("Please provide a district name.", 400)
    try:
        records = fetch_records()
    except Exception as exc:  # noqa: BLE001
        status = 503 if isinstance(exc, RuntimeError) else 502
        return api_error(safe_message(exc), status)

    matches = [r for r in records if norm(r.get(DISTRICT_FIELD, "")) == query]
    if not matches:
        return api_error("No employment data found for this district.", 404)
    rec = matches[0]
    return jsonify({
        "ok": True,
        "district": rec.get(DISTRICT_FIELD),
        "period": f"{rec.get('month', '')} {rec.get('fin_year', '')}".strip(),
        "count": 1,
        "records": [rec],
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=True)
