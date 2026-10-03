# Alma Mater Saturday

One page for the football teams of the five schools three brothers attended:
Washington and Indiana (Division I FBS), and Calvin, Hope, and Wheaton (IL)
(Division III). Live at https://www.almamatersaturday.com.

## What the page shows

- This week: each team's next game with kickoff in Eastern, Central, or the
  device's time zone (switch at the top of the page),
  TV or stream, venue, a countdown, and live score while the game is on.
- Team cards: record, conference standing, poll positions, Massey rank inside
  the division and across all divisions, Hansen rank (D3), points for and
  against, margin, last result, next game.
- Rankings and ratings table, a Hansen Ratings table for the D3 teams, and a
  cumulative point-margin chart.
- Top players: season leaders in passing, rushing, receiving, tackles, sacks,
  and interceptions.
- Full schedules and results, one tab per team plus a combined view.

## Files

| File | Purpose |
|------|---------|
| `schools.json` | The five schools: ESPN ids, colors, logos, stats page, Hansen name, alumni, conference members |
| `content/brothers.json` | Who went where, home TV market, time zone |
| `content/platforms.json` | Every network and stream on the schedules, with access notes and local stations |
| `fetch_data.py` | Pulls ESPN schedules, records, polls, and leaders; D3football.com Top 25; Hansen Ratings; school stats pages. Writes `data/season.json` |
| `data/massey.json` | Massey ratings, refreshed by hand (see below) |
| `tools/massey_extract.js` | Browser snippet that produces the Massey JSON |
| `build_site.py` | Renders `docs/index.html` |
| `docs/` | The published site (GitHub Pages), with `CNAME` and `assets/` |
| `.github/workflows/update.yml` | Scheduled fetch, build, commit |

## Data sources

- ESPN public site API: team schedules (scores, status, broadcasts, venues),
  team records and standings, rankings (AP, AFCA Coaches, CFP when published,
  AFCA Division III), and season leaders for the FBS teams. ESPN covers the
  Division III teams' schedules and scores but not their player statistics.
- School Sidearm statistics pages for the Division III leaders
  (`/sports/football/stats`, the Individual tables).
- D3football.com Top 25 at `https://d3football.com/top25/index`.
- Hansen Ratings: predictive, résumé, schedule strength, and simulation pages
  for the current season. The data is embedded in each page as JSON.
- Massey Ratings: `https://masseyratings.com/cf/ratings` (all divisions).
  Massey serves a browser challenge to scripted requests, so you refresh the
  data by hand.

## Refreshing Massey (weekly, after the Sunday update)

1. Open https://masseyratings.com/cf/ratings in Chrome.
2. Run `tools/massey_extract.js` in the browser console.
3. Paste the `teams` object into `data/massey.json`, update `through`,
   `refreshed`, and `division_sizes`, then commit and push. The next scheduled
   run rebuilds the page, or run the workflow by hand:
   `gh workflow run update.yml`.

The snippet derives each division rank from the team's position among its own
division in the all-division table. Massey's per-division pages order teams by the same
rating.

## Live scores

The page itself calls ESPN's scoreboard endpoint from the browser once a
minute while any of the five games is within 30 minutes of kickoff or in
progress, so scores do not wait for a rebuild. The scheduled workflow runs
every 20 minutes on Saturdays and four times a day otherwise to refresh
records, polls, and ratings.

## Running locally

```bash
python3 fetch_data.py && python3 build_site.py
python3 -m http.server 8766 --directory docs   # then open http://localhost:8766
```

Both scripts use only the standard library.
