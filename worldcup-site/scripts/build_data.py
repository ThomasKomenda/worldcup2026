"""
build_data.py — fetches World Cup match data and writes it as JSON for the website.

This is the "scheduled script" box from our architecture diagram (Option B).
It runs in GitHub Actions every few hours. It is the ONLY thing that ever
talks to the football-data.org API — the website itself just reads the
JSON file this script produces.

Run it locally with:
    FOOTBALL_DATA_API_KEY=your_key_here python scripts/build_data.py
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# 1. Configuration
# ---------------------------------------------------------------------------

# The API key comes from an ENVIRONMENT VARIABLE, never from the code itself.
# Locally you set it in your shell; in GitHub Actions it comes from a secret.
API_KEY = os.environ.get("FOOTBALL_DATA_API_KEY")

# "WC" is football-data.org's code for the FIFA World Cup competition.
COMPETITION = "WC"

# Where the website expects to find its data.
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "site", "data", "matches.json")


# ---------------------------------------------------------------------------
# 2. Talking to the API
# ---------------------------------------------------------------------------

def fetch_matches(date_from: str, date_to: str) -> list:
    """Call the football-data.org API for matches in a date window.

    We ask for one window covering recent results AND upcoming games,
    so a single API call is enough (respecting the 10 requests/minute limit).
    """
    url = (
        f"https://api.football-data.org/v4/competitions/{COMPETITION}/matches"
        f"?dateFrom={date_from}&dateTo={date_to}"
    )
    request = urllib.request.Request(url, headers={"X-Auth-Token": API_KEY})
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())["matches"]


def simplify(match: dict) -> dict:
    """Keep only the fields the website needs.

    APIs return far more data than you use. Trimming it here keeps the
    JSON file small and makes the frontend code simpler — this is the
    'transform' step engineers talk about in data pipelines.
    """
    score = match.get("score", {}).get("fullTime", {})
    return {
        "id": match["id"],
        "utcDate": match["utcDate"],          # always stored in UTC!
        "status": match["status"],            # SCHEDULED / TIMED / IN_PLAY / FINISHED ...
        "stage": match.get("stage"),
        "home": match["homeTeam"]["name"],
        "away": match["awayTeam"]["name"],
        "homeScore": score.get("home"),
        "awayScore": score.get("away"),
        "venue": match.get("venue"),          # stadium name, when the API provides it
    }


# ---------------------------------------------------------------------------
# 3. Main build step
# ---------------------------------------------------------------------------

def main() -> None:
    if not API_KEY:
        sys.exit(
            "ERROR: FOOTBALL_DATA_API_KEY is not set.\n"
            "Locally: FOOTBALL_DATA_API_KEY=xxx python scripts/build_data.py\n"
            "GitHub Actions: add it under Settings > Secrets and variables > Actions."
        )

    today = datetime.now(timezone.utc).date()
    date_from = (today - timedelta(days=4)).isoformat()   # recent results
    date_to = (today + timedelta(days=2)).isoformat()     # next 2 days

    print(f"Fetching {COMPETITION} matches from {date_from} to {date_to} ...")
    matches = [simplify(m) for m in fetch_matches(date_from, date_to)]

    upcoming = [m for m in matches if m["status"] in ("SCHEDULED", "TIMED", "IN_PLAY", "PAUSED")]
    finished = [m for m in matches if m["status"] == "FINISHED"]

    output = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sample": False,
        "upcoming": sorted(upcoming, key=lambda m: m["utcDate"]),
        "finished": sorted(finished, key=lambda m: m["utcDate"], reverse=True),
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(upcoming)} upcoming and {len(finished)} finished matches "
          f"to {os.path.abspath(OUTPUT_FILE)}")


if __name__ == "__main__":
    main()
