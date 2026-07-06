# World Cup 2026 Fixtures Site

A static website that displays World Cup 2026 fixtures, results, group
standings, and a knockout bracket, alongside squad market values sourced from
public datasets. The site renders match times in each visitor's local timezone
and updates automatically on a schedule without requiring a running server.

## Purpose

The application presents tournament data in a single-page interface with four
primary views: upcoming fixtures, completed results, a tournament section
(group tables plus a projected knockout bracket), and per-team filtering. Each
match exposes a detail panel showing both squads arranged by position, a
squad-value comparison, and a value-based mismatch indicator. All data is
pre-generated into static JSON files, so the deployed site performs no
server-side computation at request time.

## Architecture

The system follows a scheduled-rebuild model. Data generation happens ahead of
time in scheduled jobs; the deployed site serves only static assets.

```
football-data.org API ─────┐
                           ├─> scripts/build_data.py (every 3h) ─> site/data/*.json ─┐
transfermarkt dataset ─────┘         joins market values                             │
   (via extract_values.py, weekly)                                                    │
                                                                                      v
                                                            site/index.html reads JSON
                                                                      │
                                                            GitHub Pages (static host)
                                                                      │
                                                                 visitor browsers
```

Two GitHub Actions workflows drive the pipeline:

- `.github/workflows/build.yml` runs `build_data.py` every three hours and on
  each push, then deploys the `site/` directory to GitHub Pages.
- `.github/workflows/update_values.yml` runs `extract_values.py` weekly and
  commits the regenerated `values.json` back to the repository.

The two data sources refresh at different cadences because they change at
different rates. Fixtures and results change frequently during the tournament
and are fetched every three hours. Player market values change slowly and are
regenerated weekly. `build_data.py` consumes the `values.json` produced by
`extract_values.py`; if that file is absent, squads render without values.

## Components

### Frontend

`site/index.html` is a self-contained single-page application (HTML, CSS, and
JavaScript in one file, with no external runtime dependencies). It fetches the
generated JSON files and renders all views client-side. Fonts use the system
font stack, so no external font service is contacted.

### Data files (`site/data/`)

These are generated artifacts, not hand-edited:

- `matches.json`: fixtures and results with status, stage, and scores.
- `squads.json`: per-team squads with positions, clubs, market values, and
  crest URLs.
- `standings.json`: group tables.
- `values.json`: raw player market values from the Transfermarkt dataset.

### Scripts (`scripts/`)

- `build_data.py`: fetches matches, standings, and squads from
  football-data.org, joins market values by normalized name matching, and
  writes `matches.json`, `squads.json`, and `standings.json`. Runs every three
  hours.
- `extract_values.py`: queries the Transfermarkt dataset for player market
  values and writes `values.json`. Runs weekly.
- `probe_*.py`: standalone diagnostic scripts used to evaluate candidate data
  sources during development. They are not part of the production pipeline and
  can be removed without affecting the site.

### Configuration

- `.gitignore`: excludes secrets (`.env`), the virtual environment (`venv/`),
  and generated caches from version control.
- `.env.example`: template listing the required environment variables.
- `requirements.txt`: Python dependencies for local script execution.

## Setup

1. Register for a football-data.org API key at
   https://www.football-data.org/client/register (free tier).

2. Create a public GitHub repository and add the project files.

3. Add the API key as a repository secret named `FOOTBALL_DATA_API_KEY` under
   Settings → Secrets and variables → Actions. The key is read from the
   environment at runtime and never appears in source.

4. Enable GitHub Pages under Settings → Pages, with Source set to
   GitHub Actions.

5. Trigger the build from the Actions tab (`Build and deploy World Cup site` →
   Run workflow), then open `https://<username>.github.io/<repo>/`.

The site rebuilds every three hours thereafter.

## Local development

```bash
# Install dependencies
pip install -r requirements.txt

# Create a local .env from the template and add the API key
cp .env.example .env

# Generate data (scripts load .env automatically)
python scripts/build_data.py

# Serve the site (browsers block file:// fetches, so a local server is required)
cd site && python -m http.server   # http://localhost:8000
```

Without an API key, the site falls back to bundled sample data and displays a
notice, allowing frontend development independent of the API. `.env` is
gitignored and stays local; in GitHub Actions the key is supplied via
repository secrets, and `python-dotenv` is a no-op when no `.env` is present.

## Squad view and lineup data

The match detail renders a pitch view showing each team's highest-value squad
players by position line (goalkeeper, defence, midfield, attack). It is
labelled as squad data rather than a confirmed lineup, because no free data
source provides complete verified starting elevens for the 2026 tournament.
The following sources were evaluated:

- football-data.org free tier: no lineup data (paid add-on only).
- API-Football free tier: provides lineups with grid coordinates, but the
  current season is gated behind a paid plan.
- TheSportsDB free tier: covers 2026 matches, but lineup records are
  incomplete.
- transfermarkt-datasets: includes 2026 fixtures, but the `game_lineups` table
  is not yet populated for the tournament.

Upgrade paths for real starting elevens:

1. API-Football Pro plan, which exposes 2026 lineups with grid coordinates.
2. The Transfermarkt `game_lineups` table, if it becomes populated for the
   2026 tournament in a future refresh, which would allow a real-lineup pitch
   view at no cost.

## Data sources and licensing

- Fixtures, results, standings, and squads: football-data.org (API).
- Player market values: transfermarkt-datasets (CC0), published as CSV and
  queried directly with DuckDB.
