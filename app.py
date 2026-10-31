"""
Rozgar Saathi - Maharashtra district employment viewer (prototype)

Flask backend that:
  1. Fetches district-wise MGNREGA records from the Data.gov.in API
     (resource: "District-wise MGNREGA Data at a Glance")
  2. Keeps the latest available month for each Maharashtra district
  3. Serves them to the frontend (index.html) through simple JSON endpoints

The API key is read from the .env file (never hard-code keys in source code).
"""

import os
import re
import time

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

load_dotenv()

API_KEY = os.getenv("DATA_GOV_API_KEY", "").strip()
RESOURCE_ID = os.getenv("RESOURCE_ID", "").strip()
STATE_FIELD = os.getenv("STATE_FIELD", "state_name")
DISTRICT_FIELD = os.getenv("DISTRICT_FIELD", "district_name")
STATE_VALUE = os.getenv("STATE_VALUE", "MAHARASHTRA")
FIN_YEAR = os.getenv("FIN_YEAR", "").strip()      # optional, e.g. 2025-2026
CACHE_SECONDS = int(os.getenv("CACHE_SECONDS", "3600"))
BASE_URL = "https://api.data.gov.in/resource/"

# Financial year runs April -> March
MONTH_RANK = {m: i for i, m in enumerate(
    ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"])}

app = Flask(__name__, static_folder=".", static_url_path="")

# Used only so the district box still works if the live API is unreachable.
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


def fetch_records():
    """Latest-month Maharashtra record for each district (cached)."""
    now = time.time()
    if _cache["records"] and now - _cache["time"] < CACHE_SECONDS:
        return _cache["records"]

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

    records = latest_per_district(records)
    _cache.update(time=now, records=records)
    return records


def api_error(message, status=502):
    return jsonify({"ok": False, "error": message}), status


@app.route("/")
def home():
    return send_from_directory(".", "index.html")


@app.route("/api/health")
def health():
    return jsonify({
        "ok": True,
        "api_key_set": bool(API_KEY),
        "resource_id_set": bool(RESOURCE_ID),
    })


@app.route("/api/debug")
def debug():
    """Shows a few raw records so you can check the column names."""
    try:
        url = BASE_URL + RESOURCE_ID
        params = {"api-key": API_KEY, "format": "json", "limit": 3}
        resp = get_with_retry(url, params, {"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        try:
            data = resp.json()
        except ValueError:
            return jsonify({"http_status": resp.status_code, "not_json": resp.text[:1500]})
        return jsonify({
            "http_status": resp.status_code,
            "resource_id_used": RESOURCE_ID,
            "title": data.get("title"),
            "total_records_in_dataset": data.get("total"),
            "columns": [f.get("id") for f in data.get("field", [])],
            "settings_expect": {"STATE_FIELD": STATE_FIELD, "DISTRICT_FIELD": DISTRICT_FIELD, "STATE_VALUE": STATE_VALUE},
            "years_tried": candidate_years(),
            "first_records": data.get("records", [])[:3],
            "error": data.get("error") or data.get("message"),
        })
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)})


@app.route("/api/districts")
def districts():
    """List of district names (from the live data if possible)."""
    try:
        records = fetch_records()
        names = sorted({str(r.get(DISTRICT_FIELD, "")).strip() for r in records if r.get(DISTRICT_FIELD)})
        if names:
            return jsonify({"ok": True, "source": "live", "districts": names})
        raise RuntimeError("The API returned no records for Maharashtra.")
    except Exception as exc:  # noqa: BLE001 - we want to show any failure to the UI
        return jsonify({
            "ok": False,
            "source": "fallback",
            "error": str(exc),
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
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else "unknown"
        return api_error(f"Data.gov.in returned an error (HTTP {code}). Check your API key and RESOURCE_ID.")
    except requests.RequestException as exc:
        return api_error(f"Could not reach Data.gov.in: {exc}")
    except RuntimeError as exc:
        return api_error(str(exc), 503)

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
