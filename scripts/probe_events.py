"""
Diagnostic script: checks whether the football-data.org matches endpoint
returns goal or event-level detail for a World Cup fixture.

Not part of the production pipeline. Used during development to determine
whether the API could support event-based features before building on it.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

# Load a local .env file if python-dotenv is installed (for local testing).
# In GitHub Actions the package is absent and credentials come from
# repository secrets, so the import is guarded.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

API_KEY = os.environ.get("FOOTBALL_DATA_API_KEY")
COMPETITION = "WC"


def api_get(path: str) -> dict:
    url = f"https://api.football-data.org/v4{path}"
    req = urllib.request.Request(url, headers={"X-Auth-Token": API_KEY})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def main() -> None:
    if not API_KEY:
        sys.exit("Set FOOTBALL_DATA_API_KEY first.")

    # Find a recently finished match.
    today = datetime.now(timezone.utc).date()
    frm = (today - timedelta(days=7)).isoformat()
    to = today.isoformat()
    matches = api_get(
        f"/competitions/{COMPETITION}/matches?dateFrom={frm}&dateTo={to}"
    )["matches"]
    finished = [m for m in matches if m["status"] == "FINISHED"]

    if not finished:
        print("No finished matches in the last 7 days to probe. Try again later.")
        return

    match = finished[-1]
    mid = match["id"]
    print(f"Probing match {mid}: {match['homeTeam']['name']} vs {match['awayTeam']['name']}\n")

    # Fetch that single match in full detail.
    detail = api_get(f"/matches/{mid}")

    # The two things a goalscorers feature would need:
    goals = detail.get("goals")
    print("=== 'goals' field ===")
    if goals:
        print(f"  PRESENT: {len(goals)} goals returned. Sample keys: {list(goals[0].keys())}")
        for g in goals:
            scorer = g.get("scorer", {}).get("name", "?")
            minute = g.get("minute", "?")
            print(f"    {minute}'  {scorer}")
    else:
        print("  EMPTY or absent on this tier: a goalscorers feature is NOT feasible on free.")

    print("\n=== other potentially useful fields present ===")
    for key in ("bookings", "substitutions", "referees", "score"):
        state = "present" if detail.get(key) else "empty/absent"
        print(f"  {key}: {state}")

    print("\nVerdict: if 'goals' is PRESENT above, we build the feature. If EMPTY, we don't.")


if __name__ == "__main__":
    main()
