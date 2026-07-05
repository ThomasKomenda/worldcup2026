"""
probe_thesportsdb.py — check whether TheSportsDB's FREE tier can deliver
World Cup 2026 lineups, AND whether that data is actually correct.

TheSportsDB is crowd-sourced (Wikipedia-style), so two things are uncertain:
  (a) COVERAGE — does the free tier even let us find 2026 WC matches and
      their lineups? (the free tier caps many endpoints hard)
  (b) ACCURACY — is the lineup data complete and correct, or partial/stale?

This probe prints raw results so you can EYEBALL them against a trusted
source (FIFA.com, ESPN, Wikipedia) — because a probe only tells you what
the API returned, not whether it's right. Validation is your job.

No signup needed: TheSportsDB's public free key is the string "123".

Run:  python scripts/probe_thesportsdb.py
"""

import json
import urllib.request
import urllib.parse

# The public free key. Documented, intended for testing.
KEY = "123"
BASE = f"https://www.thesportsdb.com/api/v1/json/{KEY}"

# TheSportsDB's league ID for the FIFA World Cup (from their frontend URLs).
WC_LEAGUE_ID = "4429"


def get(path: str) -> dict:
    url = f"{BASE}/{path}"
    print(f"  GET {url}")
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"    request failed: {e}")
        return {}


def main() -> None:
    print("=" * 70)
    print("STEP 1 — Can the free tier even FIND World Cup 2026 matches?")
    print("=" * 70)
    # Try to pull the 2026 season schedule for the World Cup league.
    season = get(f"eventsseason.php?id={WC_LEAGUE_ID}&s=2026")
    events = season.get("events") if season else None

    if not events:
        print("\n  No 2026 events returned. Trying the 2022 season as a coverage check ...")
        season = get(f"eventsseason.php?id={WC_LEAGUE_ID}&s=2022")
        events = season.get("events") if season else None
        which = "2022"
    else:
        which = "2026"

    if not events:
        print("\n  VERDICT: free tier could not return World Cup events for either")
        print("  season. Finding match IDs is the blocker; lineups are moot.")
        return

    print(f"\n  Found {len(events)} events for the {which} World Cup.")
    print("  Sample matches (EYEBALL these against a real fixture list):")
    for e in events[:5]:
        print(f"    id={e.get('idEvent')}  {e.get('strEvent')}  "
              f"({e.get('dateEvent')})  score: {e.get('intHomeScore')}-{e.get('intAwayScore')}")

    # Pick a finished match to test lineups on.
    finished = [e for e in events if e.get("intHomeScore") not in (None, "")]
    target = finished[-1] if finished else events[0]
    eid = target.get("idEvent")

    print("\n" + "=" * 70)
    print(f"STEP 2 — Does that match have LINEUP data on the free tier?")
    print("=" * 70)
    print(f"  Testing match: {target.get('strEvent')} (id={eid})")
    lineup = get(f"lookuplineup.php?id={eid}")
    rows = lineup.get("lineup") if lineup else None

    print("\n=== LINEUP VERDICT ===")
    if not rows:
        print("  EMPTY — no lineup data for this match on the free tier.")
        print("  -> Crowd-sourced gap. Pitch view NOT reliably feasible here.")
    else:
        # Count how many have a position — a pitch view needs positions.
        with_pos = [r for r in rows if r.get("strPosition")]
        print(f"  PRESENT — {len(rows)} player rows, {len(with_pos)} with a position.")
        print("\n  Sample (EYEBALL against the real starting XI for this match):")
        for r in rows[:6]:
            print(f"    {r.get('strPosition','?'):3s}  {r.get('strPlayer','?')}  "
                  f"[{r.get('strHome','?')}]")
        print("\n  Fields available:", list(rows[0].keys()))

    print("\n" + "=" * 70)
    print("NEXT: VALIDATE the printed data against a trusted source before")
    print("trusting it — FIFA.com, ESPN, or Wikipedia for this exact match.")
    print("Crowd-sourced != correct. Check completeness AND accuracy.")
    print("=" * 70)


if __name__ == "__main__":
    main()
