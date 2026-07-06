# World Cup 2026 fixtures site

A static website that shows upcoming World Cup matches (next 2 days) in the
visitor's local time, plus recent results. Rebuilt automatically every 3 hours
by GitHub Actions.

## Architecture static site, rebuilt on a schedule)

```
GitHub Actions (every 3h)
  └─ scripts/build_data.py  ──calls──>  football-data.org API
        └─ writes site/data/matches.json
              └─ site/ deployed to GitHub Pages
                    └─ visitors' browsers just read static files
```


- **Weekly** (`update_values.yml`): queries the transfermarkt-datasets
  players table remotely with DuckDB SQL and commits `site/data/values.json`.
  Run it manually once (Actions tab) so values exist immediately.
- **Every 3 hours** (`build.yml`): fetches matches AND each team's squad
  from football-data.org (politely, 7s between calls to respect the
  10 req/min limit), joins market values onto players by normalized name
  (accent-stripping + word-order-independent matching, nationality as a
  tiebreaker), and writes `squads.json`.

Clicking any match on the site opens the squad panel: players sorted by
market value, their clubs, and each team's total squad value. Unmatched
players show "—".
