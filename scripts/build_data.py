"""
build_data.py — fetches World Cup match data AND team squads, joins market
values onto players, and writes JSON files for the website.

This is the FAST data rhythm (every 3 hours, via GitHub Actions):
  1. matches in a window: 4 days back to 2 days ahead  -> matches.json
  2. the squad of every team in that window            -> squads.json
     ...with market values joined from values.json (produced weekly
     by the other workflow).

Run locally:  FOOTBALL_DATA_API_KEY=your_key python scripts/build_data.py
"""

import json
import os
import re
import sys
import time
import unicodedata
import urllib.request
from datetime import datetime, timedelta, timezone

# Load a local .env file if python-dotenv is installed (for local testing).
# In GitHub Actions there's no .env and the package isn't installed — the key
# comes from repository secrets — so we import defensively and move on.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

API_KEY = os.environ.get("FOOTBALL_DATA_API_KEY")
COMPETITION = "WC"

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "site", "data")
MATCHES_FILE = os.path.join(DATA_DIR, "matches.json")
SQUADS_FILE = os.path.join(DATA_DIR, "squads.json")
VALUES_FILE = os.path.join(DATA_DIR, "values.json")

# football-data.org free tier allows 10 requests/minute. We sleep between
# calls to stay politely under it. 1 matches call + up to ~16 team calls.
SECONDS_BETWEEN_CALLS = 7


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api_get(path: str) -> dict:
    url = f"https://api.football-data.org/v4{path}"
    request = urllib.request.Request(url, headers={"X-Auth-Token": API_KEY})
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())


def simplify_match(match: dict) -> dict:
    score = match.get("score", {}).get("fullTime", {})
    return {
        "id": match["id"],
        "utcDate": match["utcDate"],
        "status": match["status"],
        "stage": match.get("stage"),
        "home": match["homeTeam"]["name"],
        "away": match["awayTeam"]["name"],
        "homeId": match["homeTeam"]["id"],
        "awayId": match["awayTeam"]["id"],
        "homeScore": score.get("home"),
        "awayScore": score.get("away"),
        "venue": match.get("venue"),
    }


# ---------------------------------------------------------------------------
# Name matching — joining two datasets that share no IDs.
#
# football-data.org spells a player one way, Transfermarkt another
# ("Heung-Min Son" vs "Son Heung-min"). Strategy:
#   1. normalize: strip accents, lowercase, drop punctuation
#   2. SORT the name parts, so word order stops mattering
#   3. if that fails, fall back to last name + nationality
# This "entity reconciliation" is imperfect by nature — we also report
# how many players we failed to match, because honest data shows its gaps.
# ---------------------------------------------------------------------------

def norm_tokens(name: str) -> list:
    text = unicodedata.normalize("NFD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z ]", " ", text.lower().replace("-", " "))
    return sorted(t for t in text.split() if t)


def build_value_index(values: list) -> tuple:
    exact = {}      # "heung min son" -> player record
    by_last = {}    # "son" -> [records]  (fallback)
    for p in values:
        tokens = norm_tokens(p["name"])
        if not tokens:
            continue
        exact.setdefault(" ".join(tokens), p)
        last = norm_tokens(p["name"])[-1]
        by_last.setdefault(last, []).append(p)
    return exact, by_last


def find_value(player_name: str, nationality: str, exact: dict, by_last: dict):
    tokens = norm_tokens(player_name)
    if not tokens:
        return None
    hit = exact.get(" ".join(tokens))
    if hit:
        return hit
    # Fallback: same last name AND same nationality, if that's unambiguous.
    candidates = [
        p for p in by_last.get(tokens[-1], [])
        if p.get("nationality") and nationality
        and p["nationality"].lower() == nationality.lower()
    ]
    if len(candidates) == 1:
        return candidates[0]
    return None  # ambiguous or missing — better no value than a wrong one


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------

def main() -> None:
    if not API_KEY:
        sys.exit("ERROR: FOOTBALL_DATA_API_KEY is not set.")

    today = datetime.now(timezone.utc).date()
    date_from = (today - timedelta(days=4)).isoformat()
    date_to = (today + timedelta(days=2)).isoformat()

    print(f"Fetching matches {date_from} .. {date_to}")
    raw = api_get(f"/competitions/{COMPETITION}/matches?dateFrom={date_from}&dateTo={date_to}")
    matches = [simplify_match(m) for m in raw["matches"]]

    upcoming = [m for m in matches if m["status"] in ("SCHEDULED", "TIMED", "IN_PLAY", "PAUSED")]
    finished = [m for m in matches if m["status"] == "FINISHED"]

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MATCHES_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "sample": False,
            "upcoming": sorted(upcoming, key=lambda m: m["utcDate"]),
            "finished": sorted(finished, key=lambda m: m["utcDate"], reverse=True),
        }, f, indent=2, ensure_ascii=False)
    print(f"matches.json: {len(upcoming)} upcoming, {len(finished)} finished")

    # ---- standings (for the group tables / bracket) ----------------------
    # One extra API call. Wrapped in try/except because during the knockout
    # stage the standings endpoint can return differently than in groups —
    # we'd rather skip this gracefully than fail the whole build.
    try:
        st = api_get(f"/competitions/{COMPETITION}/standings")
        with open(os.path.join(DATA_DIR, "standings.json"), "w", encoding="utf-8") as f:
            json.dump({"generatedAt": datetime.now(timezone.utc).isoformat(),
                       "standings": st.get("standings", [])}, f, indent=2, ensure_ascii=False)
        print(f"standings.json: {len(st.get('standings', []))} groups/tables")
    except Exception as err:
        print(f"standings skipped ({err}) — bracket will use match stages instead")

    # ---- squads ----------------------------------------------------------
    # Load the weekly market values, if the weekly workflow has produced them.
    values = []
    if os.path.exists(VALUES_FILE):
        with open(VALUES_FILE, encoding="utf-8") as f:
            values = json.load(f).get("players", [])
        print(f"Loaded {len(values)} market values")
    else:
        print("No values.json yet — squads will appear without market values.")
    exact, by_last = build_value_index(values)

    # Every team appearing in the window, deduplicated.
    teams = {}
    for m in matches:
        teams[m["homeId"]] = m["home"]
        teams[m["awayId"]] = m["away"]

    squads = {}
    for team_id, team_name in teams.items():
        time.sleep(SECONDS_BETWEEN_CALLS)   # stay under 10 requests/minute
        print(f"Fetching squad: {team_name}")
        team = api_get(f"/teams/{team_id}")

        players, matched = [], 0
        for p in team.get("squad", []):
            rec = find_value(p["name"], p.get("nationality", ""), exact, by_last)
            if rec:
                matched += 1
            players.append({
                "name": p["name"],
                "position": p.get("position"),
                "club": rec["club"] if rec else None,
                "value_eur": rec["value_eur"] if rec else None,
            })

        players.sort(key=lambda x: x["value_eur"] or 0, reverse=True)
        squads[team_name] = {
            "players": players,
            "matched": matched,
            "squadSize": len(players),
        }
        print(f"  {matched}/{len(players)} players matched to market values")

    with open(SQUADS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "teams": squads,
        }, f, indent=2, ensure_ascii=False)
    print(f"squads.json: {len(squads)} teams")


if __name__ == "__main__":
    main()
