# World Cup 2026 fixtures site

A static website that shows upcoming World Cup matches (next 2 days) in the
visitor's local time, plus recent results. Rebuilt automatically every 3 hours
by GitHub Actions — no server required.

## Architecture (Option B: static site, rebuilt on a schedule)

```
GitHub Actions (every 3h)
  └─ scripts/build_data.py  ──calls──>  football-data.org API
        └─ writes site/data/matches.json
              └─ site/ deployed to GitHub Pages
                    └─ visitors' browsers just read static files
```

## Day-one setup

1. **Create a GitHub account** at github.com (free), if you don't have one.

2. **Get a football-data.org API key**: register at
   https://www.football-data.org/client/register — the key arrives by email
   immediately. Free tier, no credit card.

3. **Create a new repository** on GitHub (public, e.g. `worldcup-2026`),
   then upload this project's files. Easiest without Git experience:
   repo page → "uploading an existing file" → drag the whole folder in.
   (Learning Git on the command line is worth it soon, but don't let it
   block day one.)

4. **Add your API key as a secret**: repo → Settings → Secrets and variables
   → Actions → "New repository secret". Name: `FOOTBALL_DATA_API_KEY`,
   value: your key. This is why the key never appears in the code.

5. **Enable GitHub Pages**: repo → Settings → Pages → under "Build and
   deployment", set Source to **GitHub Actions**.

6. **Run it**: repo → Actions tab → "Build and deploy World Cup site" →
   "Run workflow". Watch it go green, then open
   `https://<your-username>.github.io/<repo-name>/`.

From then on it rebuilds itself every 3 hours.

## Running locally

```bash
# fetch real data (replace with your key):
FOOTBALL_DATA_API_KEY=your_key python scripts/build_data.py

# serve the site (browsers block file:// fetches, so use a tiny server):
cd site
python -m http.server
# then open http://localhost:8000
```

Without an API key the site still works — it shows the bundled sample data
and a notice, so you can develop the frontend independently of the API.
(Engineers call this decoupling; it's why the sample file exists.)

## Roadmap (phase 2)

- Match detail view: squads, players' clubs, market values
- Data source: transfermarkt-datasets DuckDB file → `site/data/players.json`
- Host city / stadium enrichment
