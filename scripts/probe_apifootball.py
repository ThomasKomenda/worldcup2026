"""
probe_apifootball.py — verify what API-Football's FREE tier actually returns
for the World Cup, BEFORE we rewrite anything to use it.

We've been burned twice by "the field exists but the free tier is empty," so
this probe answers the specific questions that decide whether the pitch view
is buildable for free:

  1. Does the free tier cover World Cup 2026 at all?
  2. For a FINISHED match, does it return lineups? With positions/grid?
  3. Does it return the market-value-relevant player info?
  4. How many of our daily-100 requests does a typical match cost?

Run:
  1. Sign up free at https://www.api-football.com/  (no credit card)
  2. Put your key in .env as:  API_FOOTBALL_KEY=your_key_here
  3. python scripts/probe_apifootball.py
"""

import json
import os
import sys
import urllib.request

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

API_KEY = os.environ.get("API_FOOTBALL_KEY")

# API-Football is reached either directly (api-sports.io) or via RapidAPI.
# The direct host is simplest for a free account created on api-football.com.
HOST = "v3.football.api-sports.io"


def api_get(path: str) -> dict:
    """One GET request. Returns parsed JSON. Also prints the rate-limit
    headers so we can SEE how much of our daily budget each call uses."""
    url = f"https://{HOST}{path}"
    req = urllib.request.Request(url, headers={"x-apisports-key": API_KEY})
    with urllib.request.urlopen(req) as resp:
        # These headers tell us our remaining daily quota — worth watching.
        remaining = resp.headers.get("x-ratelimit-requests-remaining", "?")
        limit = resp.headers.get("x-ratelimit-requests-limit", "?")
        print(f"    [quota: {remaining}/{limit} requests left today]")
        return json.loads(resp.read())


def main() -> None:
    if not API_KEY:
        sys.exit(
            "Set API_FOOTBALL_KEY first.\n"
            "  1. Sign up at https://www.api-football.com/ (free, no card)\n"
            "  2. Add to .env:  API_FOOTBALL_KEY=your_key_here"
        )

    # --- Q1: does the free tier know about the World Cup? ------------------
    # League 1 is the World Cup in API-Football's IDs; season is the year.
    print("Q1: Looking up World Cup coverage ...")
    league = api_get("/leagues?id=1&season=2026")
    if not league.get("response"):
        print("  World Cup 2026 not found on this tier/season. Trying 2022 as a fallback probe ...")
        season = 2022
    else:
        print(f"  Found: {league['response'][0]['league']['name']} — coverage listed.")
        season = 2026

    # --- Q2: get a finished match, then ask for its lineup ----------------
    print(f"\nQ2: Finding a finished World Cup {season} match ...")
    fixtures = api_get(f"/fixtures?league=1&season={season}")
    finished = [f for f in fixtures.get("response", [])
                if f["fixture"]["status"]["short"] == "FT"]
    if not finished:
        print("  No finished matches found to probe. Try a season with completed games.")
        return

    fx = finished[-1]
    fid = fx["fixture"]["id"]
    home = fx["teams"]["home"]["name"]
    away = fx["teams"]["away"]["name"]
    print(f"  Probing fixture {fid}: {home} vs {away}")

    print("\n  Requesting lineups for that fixture ...")
    lineups = api_get(f"/fixtures/lineups?fixture={fid}")
    resp = lineups.get("response", [])

    print("\n=== LINEUP VERDICT ===")
    if not resp:
        print("  EMPTY — free tier does NOT return lineups for this match.")
        print("  -> The pitch view is NOT feasible on API-Football free either.")
        return

    team0 = resp[0]
    formation = team0.get("formation")
    players = team0.get("startXI", [])
    print(f"  PRESENT — {home} formation: {formation}, {len(players)} starters returned.")

    # The crucial detail for a PITCH view: do we get positions / grid coords?
    if players:
        sample = players[0].get("player", {})
        keys = list(sample.keys())
        has_grid = "grid" in sample     # "grid" = row:col on the pitch, ideal for placing
        has_pos = "pos" in sample
        print(f"  Player fields: {keys}")
        print(f"  Has position ('pos'): {has_pos}   Has pitch grid ('grid'): {has_grid}")
        print("\n  Sample starters:")
        for p in players[:4]:
            pl = p.get("player", {})
            print(f"    {pl.get('pos','?')}  grid={pl.get('grid','?')}  {pl.get('name','?')}")

    print("\n=== WHAT THIS MEANS ===")
    print("  If PRESENT with 'grid': we can build a TRUE pitch view with players")
    print("     at real positions. Worth migrating to API-Football.")
    print("  If PRESENT without 'grid': we can place players by 'pos' lines")
    print("     (GK/DEF/MID/FWD) — still a real lineup, slightly less precise.")
    print("  If EMPTY: lineups aren't free here; stick with squad-by-position view.")


if __name__ == "__main__":
    main()
