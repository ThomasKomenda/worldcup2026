"""
Fetches World Cup match data and team squads, joins player market values, and
writes the JSON files consumed by the frontend.

Runs every three hours via GitHub Actions and produces three files:
  matches.json   fixtures and results in a window of 4 days back to 2 days ahead
  squads.json    squad of every team in that window, with market values joined
                 from values.json (generated weekly by extract_values.py)
  standings.json group tables

Local execution:
  FOOTBALL_DATA_API_KEY=<key> python scripts/build_data.py
"""

import json
import os
import re
import sys
import time
import unicodedata
import urllib.request
from datetime import datetime, timedelta, timezone

# Load a local .env file when python-dotenv is available. In GitHub Actions the
# package is absent and the API key is supplied via repository secrets, so the
# import is guarded and the absence of dotenv is a no-op.
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

# The football-data.org free tier permits 10 requests per minute. Calls are
# spaced to stay within this limit: 1 matches request plus up to ~16 team
# requests per build.
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
# Name matching: joining two datasets that share no common identifier.
#
# football-data.org and Transfermarkt spell player names differently
# ("Heung-Min Son" vs "Son Heung-min"). The matching strategy is:
#   1. Normalize: strip accents, lowercase, remove punctuation.
#   2. Sort the name tokens so word order does not affect the match.
#   3. Fall back to last name plus nationality when the sorted match fails.
# Entity reconciliation across sources is inherently imperfect, so the build
# also reports the number of unmatched players.
# ---------------------------------------------------------------------------

def norm_tokens(name: str) -> list:
    text = unicodedata.normalize("NFD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z ]", " ", text.lower().replace("-", " "))
    return sorted(t for t in text.split() if t)


def build_value_index(values: list) -> tuple:
    exact = {}      # normalized sorted name -> player record
    by_last = {}    # last name -> [records], used as fallback
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
    # Fallback: match on last name plus nationality when unambiguous.
    candidates = [
        p for p in by_last.get(tokens[-1], [])
        if p.get("nationality") and nationality
        and p["nationality"].lower() == nationality.lower()
    ]
    if len(candidates) == 1:
        return candidates[0]
    return None  # ambiguous or missing; omit rather than risk a wrong value


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

    # ---- standings (group tables) ----------------------------------------
    # The standings endpoint may respond differently during the knockout
    # stage than during the group stage. It is wrapped in try/except so a
    # failure here skips standings rather than failing the entire build.
    try:
        st = api_get(f"/competitions/{COMPETITION}/standings")
        with open(os.path.join(DATA_DIR, "standings.json"), "w", encoding="utf-8") as f:
            json.dump({"generatedAt": datetime.now(timezone.utc).isoformat(),
                       "standings": st.get("standings", [])}, f, indent=2, ensure_ascii=False)
        print(f"standings.json: {len(st.get('standings', []))} groups/tables")
    except Exception as err:
        print(f"standings skipped ({err}); bracket falls back to match stages")

    # ---- squads ----------------------------------------------------------
    # Load market values if extract_values.py has produced values.json.
    values = []
    if os.path.exists(VALUES_FILE):
        with open(VALUES_FILE, encoding="utf-8") as f:
            values = json.load(f).get("players", [])
        print(f"Loaded {len(values)} market values")
    else:
        print("No values.json found; squads will render without market values.")
    exact, by_last = build_value_index(values)

    # Deduplicated set of teams appearing in the window.
    teams = {}
    for m in matches:
        teams[m["homeId"]] = m["home"]
        teams[m["awayId"]] = m["away"]

    squads = {}
    for team_id, team_name in teams.items():
        time.sleep(SECONDS_BETWEEN_CALLS)   # respect the 10 req/min limit
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
            "crest": team.get("crest"),          # crest URL used by the pitch view
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
