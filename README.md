# Alma Mater Saturday

One page for the football teams of the five schools that three brothers attended. Washington and Indiana play Division I FBS. Calvin, Hope, and Wheaton (IL) play Division III. Live at https://www.almamatersaturday.com.

## What the page shows

- This week: each team's next game. The card shows the kickoff in Eastern, Central, or the device's time zone (switch at the top of the page), the TV network or stream, the venue, and a countdown. It links to the school's live stats page and the ESPN game page. While the game is on, it shows the live score, who has the ball, down and distance, and the last play.
- Team cards: record, conference standing, poll positions, and Massey rank inside the division and across all divisions. Also Hansen rank (D3), points for and against, margin, last result, and next game.
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
| `fetch_data.py` | Pulls ESPN schedules, records, polls, and leaders, plus the D3football.com Top 25, Hansen Ratings, and school stats pages. Writes `data/season.json` |
| `data/massey.json` | Massey ratings, refreshed by hand (see below) |
| `tools/massey_extract.js` | Browser snippet that produces the Massey JSON |
| `build_site.py` | Renders `docs/index.html` |
| `docs/` | The published site (GitHub Pages), with `CNAME` and `assets/` |
| `.github/workflows/update.yml` | Scheduled fetch, build, commit |

## Data sources

- ESPN public site API: team schedules (scores, status, broadcasts, venues), team records and standings, and rankings (AP, AFCA Coaches, CFP when published, AFCA Division III). It also gives season leaders for the FBS teams. ESPN covers the
  Division III teams' schedules and scores but not their player statistics.
- School Sidearm statistics pages for the Division III leaders
  (`/sports/football/stats`, the Individual tables).
- School schedule pages (`/sports/football/schedule`) for each game's live
  stats link. Both Sidearm page generations label the link
  "Live stats for Football vs X on <date>", which the fetcher matches to the
  ESPN game by date.
- D3football.com Top 25 at `https://d3football.com/top25/index`.
- Hansen Ratings: predictive, résumé, schedule strength, and simulation pages
  for the current season. The data is embedded in each page as JSON.
- Massey Ratings: `https://masseyratings.com/cf/ratings` (all divisions).
  Massey serves a browser challenge to scripted requests, so you refresh the
  data by hand.

## Refreshing the D3football.com poll (Mondays, if the fetch fails)

d3football.com serves a browser challenge to scripted requests, so the live
fetch often fails. When it does, `fetch_data.py` reads `data/d3football.json`
instead and never blanks the poll. To refresh that file:

1. Open https://d3football.com/top25/index in a browser.
2. Run `tools/d3football_extract.js` in the console. It copies the JSON to the
   clipboard.
3. Paste it over `data/d3football.json`, then commit and push.

When the live fetch does succeed, it rewrites `data/d3football.json` itself.

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

The page itself polls from the browser once a minute while any of the five games is within 30 minutes of kickoff or in progress. Scores do not wait for a rebuild. The scheduled workflow runs every 20 minutes on Saturdays and
four times a day otherwise to refresh records, polls, and ratings.

Two kinds of source feed the in-game card:

- ESPN's scoreboard endpoint gives the score and clock for every game. For FBS games it also gives the `situation` block: possession, down and distance, field position, and the last play. ESPN publishes no `situation` for
  Division III games.
- The home team's live stats feed covers the Division III games.
  `fetch_data.py` reads each school's schedule page, takes the live stats link for each game, and derives the feed behind it:
  - Sidearm live stats (`<host>/sidearmstats/football/summary`, or the older
    `sidearmstats.com/<client>/football/`) read
    `https://sidearmstats.com/<client>/football/game.json`. The client name
    comes from `window.client_shortname` on the live stats page.
  - PrestoSports StatView (`prestolivestats.com/<site>/<event>`) reads
    `https://data.prestolivestats.com/xml/<site>/events/<event>.xml`.
  - StatBroadcast (Washington and Indiana) has no readable feed, so those
    games show the link only and ESPN supplies the situation.

  Both feeds allow cross-origin requests. The page uses a feed only when its game date matches the card. It ignores the feed until the feed shows the game in progress, and hands back to ESPN once the feed marks the game complete. Sidearm does not name the team in possession. The page infers it from the last play and flips it after a punt, kickoff, or turnover.

At halftime the card names the team that gets the ball to start the second
half: the team that kicked off to start the game. The page reads that once per game from the play list. ESPN's game summary
(`.../summary?event=<id>`) lists every drive, and the first kickoff's
`start.team` is the kicking team. Sidearm's `game.json?detail=full` adds the
full `Plays` list, oldest first. Presto's XML already holds every play, and
the first `type="K"` play in quarter 1 names the kicking team in `hasball`.

Each game in `data/season.json` carries `live_stats` (the link) and
`live_feed` (`{"type": "sidearm" | "presto", "url": ...}` or null). If a
schedule page fails to load, the games keep the previous run's values.

## Running locally

```bash
python3 fetch_data.py && python3 build_site.py
python3 -m http.server 8766 --directory docs   # then open http://localhost:8766
```

Both scripts use only the standard library.
