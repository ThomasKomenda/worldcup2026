"""
Diagnostic script: checks whether the transfermarkt-datasets game_lineups
table contains complete starting elevens with usable positions for the 2026
World Cup.

Queries the table via DuckDB using plain fetchall(), requiring only the duckdb
package. Not part of the production pipeline.
"""

import duckdb

BASE = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data"
LINEUPS = f"{BASE}/game_lineups.csv.gz"
GAMES = f"{BASE}/games.csv.gz"
WC = "FIWC"
R = "ignore_errors=true"


def main() -> None:
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")

    print("Loading World Cup game IDs ...")
    wc_games = con.execute(f"""
        SELECT game_id, date, home_club_name, away_club_name
        FROM read_csv_auto('{GAMES}', {R})
        WHERE competition_id = '{WC}'
    """).fetchall()
    # dict: game_id -> (date, home, away)
    games_by_id = {r[0]: (r[1], r[2], r[3]) for r in wc_games}
    wc_ids = list(games_by_id.keys())
    print(f"  {len(wc_ids)} World Cup games in the games table")
    if not wc_ids:
        print("  No WC games found. Stopping.")
        return

    print("\nChecking which WC games have lineup rows (scans the table) ...")
    id_list = ",".join(str(i) for i in wc_ids)
    lineup_counts = con.execute(f"""
        SELECT game_id, COUNT(*) AS n
        FROM read_csv_auto('{LINEUPS}', {R})
        WHERE game_id IN ({id_list})
        GROUP BY game_id
        ORDER BY n DESC
    """).fetchall()

    if not lineup_counts:
        print("\n  ZERO World Cup games have lineup rows in the dataset yet.")
        print("  -> Fixtures are in, but game_lineups doesn't cover this tournament yet.")
        return

    print(f"\n  {len(lineup_counts)} World Cup games HAVE lineup data. Most rows first:")
    for gid, n in lineup_counts[:10]:
        date, home, away = games_by_id.get(gid, ("?", "?", "?"))
        print(f"    game_id={gid}  {date}  {home} vs {away}  ({n} rows)")

    # Inspect the most complete match.
    best = lineup_counts[0][0]
    date, home, away = games_by_id[best]
    print(f"\nInspecting game_id={best}: {home} vs {away}  ({date})")
    rows = con.execute(f"""
        SELECT club_id, type, position, number, player_name, team_captain
        FROM read_csv_auto('{LINEUPS}', {R})
        WHERE game_id = {best}
        ORDER BY club_id, type
    """).fetchall()

    types = sorted(set(str(r[1]) for r in rows))
    positions = sorted(set(str(r[2]) for r in rows if r[2] is not None))
    print("  'type' values:", types)
    print("  positions seen:", positions)

    # group by club_id
    clubs = {}
    for club_id, typ, pos, num, name, cap in rows:
        clubs.setdefault(club_id, []).append((typ, pos, num, name, cap))

    for club_id, plist in clubs.items():
        starters = [p for p in plist if "start" in str(p[0]).lower()]
        print(f"\n  Club {club_id}: {len(plist)} rows, {len(starters)} starters")
        for typ, pos, num, name, cap in starters[:11]:
            c = " (C)" if str(cap) in ("1", "True", "true") else ""
            print(f"    {str(pos):16s} #{num}  {name}{c}")

    print("\nVERDICT: ~11 starters/team with positions => pitch view buildable free.")


if __name__ == "__main__":
    main()
