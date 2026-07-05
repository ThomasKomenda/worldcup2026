"""
extract_values.py — pulls player market values from the transfermarkt-datasets
project and saves them as site/data/values.json.

This is the SLOW data rhythm: the source dataset refreshes weekly, so this
script runs weekly (see .github/workflows/update_values.yml). The fast
3-hourly build then joins these values onto squads.

The clever bit: we never download the whole database. DuckDB can run SQL
directly against a CSV file sitting on the internet — it fetches only what
the query needs.
"""

import json
import os
import sys

import duckdb  # installed by the workflow: pip install duckdb

# Load a local .env file if python-dotenv is installed (for local testing).
# In GitHub Actions there's no .env and the package isn't installed — the key
# comes from repository secrets — so we import defensively and move on.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# The transfermarkt-datasets project publishes each table as a public CSV.
PLAYERS_CSV = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/players.csv.gz"

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "site", "data", "values.json")

# Your first real SQL query. Read it aloud: "from the players table, keep
# name, nationality, club and market value, for players active recently
# who have a known market value."
QUERY = f"""
    SELECT
        name,
        country_of_citizenship AS nationality,
        current_club_name      AS club,
        market_value_in_eur    AS value_eur
    FROM read_csv_auto('{PLAYERS_CSV}')
    WHERE market_value_in_eur IS NOT NULL
      AND last_season >= 2024
"""


def main() -> None:
    con = duckdb.connect()
    # httpfs is DuckDB's extension for reading files over the internet.
    con.execute("INSTALL httpfs; LOAD httpfs;")

    print("Querying remote players table (this fetches a few MB) ...")
    try:
        rows = con.execute(QUERY).fetchall()
    except Exception as err:
        # Defensive habit: community datasets can rename columns. If that
        # happens, print what IS there so the fix is obvious from the log.
        print(f"Query failed: {err}")
        cols = con.execute(
            f"SELECT * FROM read_csv_auto('{PLAYERS_CSV}') LIMIT 0"
        ).description
        print("Available columns:", [c[0] for c in cols])
        sys.exit(1)

    players = [
        {"name": r[0], "nationality": r[1], "club": r[2], "value_eur": int(r[3])}
        for r in rows
        if r[0]
    ]

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"source": "transfermarkt-datasets (CC0)", "players": players},
                  f, ensure_ascii=False)

    print(f"Wrote {len(players)} player valuations to {os.path.abspath(OUTPUT_FILE)}")


if __name__ == "__main__":
    main()
