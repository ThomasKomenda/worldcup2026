"""
Extracts player market values from the transfermarkt-datasets project and
writes them to site/data/values.json.

Runs weekly (see .github/workflows/update_values.yml), matching the weekly
refresh cadence of the source dataset. build_data.py then joins these values
onto squads during its three-hourly run.

The query runs directly against a remote gzipped CSV via DuckDB's httpfs
extension. Only the columns and rows the query selects are transferred; the
full dataset is never downloaded.
"""

import json
import os
import sys

import duckdb  # installed by the workflow: pip install duckdb

# Load a local .env file when python-dotenv is available. In GitHub Actions
# the package is absent and credentials come from repository secrets, so the
# import is guarded.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# The transfermarkt-datasets project publishes each table as a public CSV.
PLAYERS_CSV = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/players.csv.gz"

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "site", "data", "values.json")

# Select name, nationality, club, and market value for players active in
# recent seasons that have a known market value.
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
    # httpfs enables DuckDB to read files over HTTP.
    con.execute("INSTALL httpfs; LOAD httpfs;")

    print("Querying remote players table...")
    try:
        rows = con.execute(QUERY).fetchall()
    except Exception as err:
        # Community datasets may rename columns between refreshes. On query
        # failure, print the available columns so the schema change is
        # visible in the workflow log.
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
