#!/usr/bin/env python3
"""Pull everything the site needs except Massey into data/season.json.

Sources, all public and unauthenticated:
  ESPN team schedule     site.api.espn.com/.../teams/<id>/schedule   (games, scores, TV)
  ESPN team summary      site.api.espn.com/.../teams/<id>            (record, standing)
  ESPN rankings          site.api.espn.com/.../rankings              (AP, Coaches, CFP, AFCA D3)
  ESPN season leaders    sports.core.api.espn.com/.../teams/<id>/leaders  (FBS top players)
  School stats pages     <school>/sports/football/stats              (D3 top players, Sidearm)
  D3football.com         d3football.com/top25/index                  (D3football.com Top 25)
  Hansen Ratings         hansenratings.com/ratings/... and /simulation (D3 ratings, odds)

Massey ratings are refreshed by hand into data/massey.json (see README) because
masseyratings.com sits behind a browser challenge.
"""
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
SCHOOLS = json.loads((BASE / "schools.json").read_text())
ESPN = "https://site.api.espn.com/apis/site/v2/sports/football/college-football"
CORE = "https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/seasons/2026/types/2"
HANSEN = "https://hansenratings.com"
SEASON = 2026
CENTRAL = ZoneInfo("America/Chicago")
UA = {"User-Agent": "Mozilla/5.0 (almamatersaturday.com schedule page)",
      "Accept": "text/html,application/json;q=0.9,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"}
TAG = re.compile(r"<[^>]+>")


def now():
    return datetime.now(CENTRAL)


def get(url, as_json=True, timeout=40):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    return json.loads(body) if as_json else body.decode("utf-8", "replace")


def text(fragment):
    return html.unescape(TAG.sub(" ", fragment)).strip()


def score_of(competitor):
    score = competitor.get("score")
    if isinstance(score, dict):
        score = score.get("value", score.get("displayValue"))
    if score in (None, ""):
        return None
    try:
        return int(float(score))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- ESPN games

def team_games(school):
    sched = get(f"{ESPN}/teams/{school['espn_id']}/schedule")
    games = []
    for event in sched.get("events", []):
        comp = event["competitions"][0]
        me = next(c for c in comp["competitors"] if c["team"]["id"] == school["espn_id"])
        opp = next(c for c in comp["competitors"] if c["team"]["id"] != school["espn_id"])
        status = comp["status"]["type"]
        pf, pa = score_of(me), score_of(opp)
        result = None
        if status["state"] == "post" and pf is not None and pa is not None:
            result = "W" if pf > pa else "L" if pf < pa else "T"
        rank = opp.get("curatedRank", {}).get("current")
        venue = comp.get("venue", {}) or {}
        addr = venue.get("address", {}) or {}
        logos = opp["team"].get("logos") or []
        games.append({
            "id": event["id"],
            "week": event.get("week", {}).get("number"),
            "date": event["date"],
            "time_tbd": comp.get("timeValid") is False,
            "home": me["homeAway"] == "home",
            "neutral": bool(comp.get("neutralSite")),
            "opponent": {
                "name": opp["team"].get("displayName"),
                "short": opp["team"].get("shortDisplayName") or opp["team"].get("location"),
                "espn_id": opp["team"]["id"],
                "logo": logos[0]["href"] if logos else None,
                "rank": rank if isinstance(rank, int) and rank <= 25 else None,
            },
            "venue": venue.get("fullName"),
            "city": ", ".join(x for x in (addr.get("city"), addr.get("state")) if x),
            "broadcasts": [b.get("media", {}).get("shortName") for b in comp.get("broadcasts", []) if b.get("media", {}).get("shortName")],
            "state": status["state"],
            "status": status.get("shortDetail"),
            "pf": pf,
            "pa": pa,
            "result": result,
            "clock": comp["status"].get("displayClock"),
            "period": comp["status"].get("period"),
            "group": school["espn_group"],
        })
    games.sort(key=lambda g: g["date"])
    return games


def team_summary(school):
    team = get(f"{ESPN}/teams/{school['espn_id']}")["team"]
    items = team.get("record", {}).get("items", [])
    overall = next((i.get("summary") for i in items if i.get("type") == "total"), items[0].get("summary") if items else None)
    conf = next((i.get("summary") for i in items if i.get("type") in ("vsconf", "conference")), None)
    return {"record": overall, "conf_record": conf, "standing": team.get("standingSummary")}


# ---------------------------------------------------------------- polls

def polls():
    data = get(f"{ESPN}/rankings")
    ids = {s["espn_id"]: s["slug"] for s in SCHOOLS}
    out = {}
    for poll in data.get("rankings", []):
        name = poll.get("shortName") or poll.get("name")
        out[name] = {
            "name": poll.get("name"),
            "week": poll.get("occurrence", {}).get("number"),
            "date": poll.get("date"),
            "ranks": {ids[r["team"]["id"]]: r["current"] for r in poll.get("ranks", []) if r["team"]["id"] in ids},
            "receiving_votes": {ids[r["team"]["id"]]: r.get("points") for r in poll.get("others", []) if r["team"]["id"] in ids},
        }
    return out


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def d3football_week_urls():
    """Candidate poll pages, best guess first: the index redirect target, then weeks around the calendar estimate."""
    urls = []
    try:
        opener = urllib.request.build_opener(NoRedirect)
        opener.open(urllib.request.Request("https://d3football.com/top25/index", headers=UA), timeout=40)
    except urllib.error.HTTPError as exc:
        loc = exc.headers.get("Location") if exc.code in (301, 302, 303, 307, 308) else None
        if loc:
            urls.append(loc if loc.startswith("http") else "https://d3football.com" + loc)
    except (urllib.error.URLError, TimeoutError):
        pass
    today = now().date()
    # Week 1 poll follows the first Saturday of September; one poll per week after that.
    first_poll = date(today.year, 9, 7)
    est = max(1, (today - first_poll).days // 7 + 1)
    for n in (est + 1, est, est - 1, est - 2):
        if n >= 1:
            urls.append(f"https://d3football.com/top25/{today.year}/week{n}")
    seen, ordered = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            ordered.append(u)
    return ordered


def d3football_top25():
    page, last = None, None
    for url in d3football_week_urls():
        try:
            candidate = get(url, as_json=False)
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            continue
        flat = html.unescape(re.sub(r"\s+", " ", TAG.sub(" ", candidate)))
        if "Rank School" in flat and "receiving votes" in flat:
            page = candidate
            break
    if page is None:
        raise ValueError(f"no poll page parsed ({last})")
    page = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    body_text = html.unescape(re.sub(r"\s+", " ", TAG.sub(" ", page)))
    parsed = d3football_parse(body_text)
    (DATA / "d3football.json").write_text(json.dumps({"source": "https://d3football.com/top25/index", "refreshed": now().isoformat(timespec="seconds"), **parsed}, indent=1))
    return d3football_map(parsed)


def d3football_parse(body_text):
    title = re.search(r"D3football\.com Top 25, (\d{4} Week \d+|\d{4} preseason|\d{4} final)", body_text)
    through = re.search(r"Through games of ([A-Z][a-z]+\.? \d+, \d{4})", body_text)
    body = body_text[body_text.find("Rank School"):]
    end = body.find("The D3football.com Top 25 is voted")
    body = body[:end] if end > 0 else body
    ranked = {}
    pattern = re.compile(r"(\d{1,2}) ([A-Z][^()]*?(?: \([A-Z][a-z.]+\))?)(?: \((\d+)\))? (\d+-\d+(?:-\d+)?) (\d+) (\d+|NR|RV)")
    for m in pattern.finditer(body):
        ranked[m.group(2).strip()] = {"rank": int(m.group(1)), "record": m.group(4), "points": int(m.group(5)), "prev": m.group(6)}
    rv = {}
    m = re.search(r"Others receiving votes: (.*?)\.(?: |$)", body)
    if m:
        for item in m.group(1).split(";"):
            mm = re.match(r"(.+?) (\d+)$", item.strip())
            if mm:
                rv[mm.group(1).strip()] = int(mm.group(2))
    return {"label": title.group(1) if title else None, "through": through.group(1) if through else None, "ranked": ranked, "receiving_votes": rv}


def d3football_map(parsed):
    """Pick the five schools out of a full poll table."""
    out = {"label": parsed.get("label"), "through": parsed.get("through"), "ranks": {}, "receiving_votes": {}}
    for s in SCHOOLS:
        key = s.get("d3football_key")
        if key and key in parsed.get("ranked", {}):
            out["ranks"][s["slug"]] = parsed["ranked"][key]
        elif key and key in parsed.get("receiving_votes", {}):
            out["receiving_votes"][s["slug"]] = parsed["receiving_votes"][key]
    return out


def d3football_file():
    """The hand-refreshed copy (tools/d3football_extract.js), used when the live site serves its browser challenge."""
    path = DATA / "d3football.json"
    if not path.exists():
        raise ValueError("no data/d3football.json")
    parsed = json.loads(path.read_text())
    out = d3football_map(parsed)
    out["refreshed"] = parsed.get("refreshed")
    return out


# ---------------------------------------------------------------- Hansen Ratings (D3)

def hansen_table(path):
    page = get(f"{HANSEN}{path}", as_json=False)
    for m in re.finditer(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', page, flags=re.S):
        blob = json.loads(m.group(1))
        found = _find_columns(blob)
        if found:
            return found
    raise ValueError(f"no data table on {path}")


def _find_columns(obj):
    if isinstance(obj, dict):
        if "Team" in obj and isinstance(obj["Team"], list):
            return obj
        for v in obj.values():
            r = _find_columns(v)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find_columns(v)
            if r:
                return r
    return None


def hansen():
    keys = {s["hansen_key"]: s["slug"] for s in SCHOOLS if s.get("hansen_key")}
    pages = {
        "predictive": f"/ratings/predictive/{SEASON}/",
        "resume": f"/ratings/resume/{SEASON}/",
        "sos": f"/ratings/schedule-strength/{SEASON}/",
        "simulation": f"/simulation/{SEASON}/",
    }
    out = {"fetched": now().isoformat(timespec="seconds"), "teams": {slug: {} for slug in keys.values()}}
    for name, path in pages.items():
        cols = hansen_table(path)
        n = len(cols["Team"])
        out[f"{name}_count"] = n
        for i, team in enumerate(cols["Team"]):
            if team in keys:
                out["teams"][keys[team]][name] = {c: cols[c][i] for c in cols if c not in (".rownames", "Team")}
    return out


# ---------------------------------------------------------------- odds and win probability

def espn_odds(game, school):
    """DraftKings line and ESPN's matchup predictor for an FBS game, or None."""
    gid = game["id"]
    out = {}
    try:
        odds = get(f"https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/events/{gid}/competitions/{gid}/odds")
        item = next((o for o in odds.get("items", []) if o.get("details")), None)
        if item:
            out["line"] = {
                "provider": (item.get("provider") or {}).get("name"),
                "details": item.get("details"),
                "over_under": item.get("overUnder"),
                "home_ml": (item.get("homeTeamOdds") or {}).get("moneyLine"),
                "away_ml": (item.get("awayTeamOdds") or {}).get("moneyLine"),
            }
    except (urllib.error.URLError, ValueError, TimeoutError):
        pass
    try:
        pred = get(f"https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/events/{gid}/competitions/{gid}/predictor")
        side = pred.get("homeTeam" if game["home"] else "awayTeam") or {}
        prob = next((st.get("value") for st in side.get("statistics", []) if st.get("name") == "gameProjection"), None)
        if prob is not None:
            out["win_prob"] = {"source": "ESPN matchup predictor", "pct": round(float(prob), 1)}
    except (urllib.error.URLError, ValueError, TimeoutError):
        pass
    return out or None


def hansen_projections():
    """This week's Hansen game projections, keyed by (home, away) Hansen team names."""
    page = get(f"{HANSEN}/projections/{SEASON}/", as_json=False)
    m = re.search(r'url=(/projections/\d{4}/[^"]+)"', page)
    week_path = m.group(1) if m else f"/projections/{SEASON}/"
    page = get(f"{HANSEN}{week_path}", as_json=False)
    cols = None
    for mm in re.finditer(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', page, flags=re.S):
        cols = _find_key(json.loads(mm.group(1)), "H Win%")
        if cols:
            break
    if not cols:
        return {}, week_path
    out = {}
    for i, home in enumerate(cols["Home"]):
        out[(home, cols["Away"][i])] = {c: cols[c][i] for c in cols if c != ".rownames"}
    return out, week_path


def _find_key(obj, key):
    if isinstance(obj, dict):
        if key in obj and isinstance(obj[key], list):
            return obj
        for v in obj.values():
            r = _find_key(v, key)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find_key(v, key)
            if r:
                return r
    return None


def hansen_odds(game, school, projections):
    mine = school["hansen_key"]
    for (home, away), row in projections.items():
        if mine not in (home, away):
            continue
        opp_short = game["opponent"]["short"].lower().split()[0]
        other = away if home == mine else home
        if opp_short not in other.lower():
            continue
        i_am_home = home == mine
        my_pct = row["H Win%"] if i_am_home else row["A Win%"]
        my_score = row["H Score"] if i_am_home else row["A Score"]
        opp_score = row["A Score"] if i_am_home else row["H Score"]
        return {"win_prob": {"source": "Hansen Ratings", "pct": round(float(my_pct) * 100, 1)},
                "projection": {"source": "Hansen Ratings", "mine": round(float(my_score)), "opp": round(float(opp_score)), "total": round(float(row["Total"]), 1)}}
    return None


# ---------------------------------------------------------------- top players

def _stat_line(parts):
    return ", ".join(p for p in parts if p)


def espn_leaders(school):
    data = get(f"{CORE}/teams/{school['espn_id']}/leaders")
    cats = {c["name"]: c for c in data.get("categories", [])}
    wanted = [
        ("passingYards", "Passing", "passingLeader"),
        ("rushingYards", "Rushing", "rushingLeader"),
        ("receivingYards", "Receiving", "receivingLeader"),
        ("totalTackles", "Tackles", None),
        ("sacks", "Sacks", None),
        ("interceptions", "Interceptions", None),
    ]
    players = []
    cache = {}
    for cat, label, summary_cat in wanted:
        leaders = cats.get(cat, {}).get("leaders") or []
        if not leaders:
            continue
        top = leaders[0]
        ref = top["athlete"]["$ref"]
        if ref not in cache:
            cache[ref] = get(ref)
        ath = cache[ref]
        line = top.get("displayValue", "")
        if summary_cat and cats.get(summary_cat, {}).get("leaders"):
            match = next((l for l in cats[summary_cat]["leaders"] if l["athlete"]["$ref"] == ref), None)
            if match:
                line = match.get("displayValue", line)
        if cat == "totalTackles":
            line = f"{line} tackles"
        elif cat == "sacks":
            line = f"{line} sacks"
        elif cat == "interceptions":
            line = f"{line} INT"
        players.append({
            "label": label,
            "name": ath.get("displayName"),
            "position": (ath.get("position") or {}).get("abbreviation"),
            "jersey": ath.get("jersey"),
            "year": class_year((ath.get("experience") or {}).get("displayValue")),
            "headshot": (ath.get("headshot") or {}).get("href"),
            "line": line,
        })
    return players


def _sidearm_rows(page, section_id):
    m = re.search(r'<section[^>]*id="' + section_id + r'".*?</section>', page, flags=re.S)
    if not m:
        return [], []
    table = re.search(r"<table.*?</table>", m.group(0), flags=re.S)
    if not table:
        return [], []
    heads = [text(h) for h in re.findall(r"<thead.*?</thead>", table.group(0), flags=re.S)[0:1] and re.findall(r"<th[^>]*>(.*?)</th>", re.findall(r"<thead.*?</thead>", table.group(0), flags=re.S)[0], flags=re.S)]
    body = re.findall(r"<tbody.*?</tbody>", table.group(0), flags=re.S)
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body[0] if body else "", flags=re.S):
        cells = [text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)]
        if len(cells) >= len(heads) - 1:
            rows.append(dict(zip(heads, cells)))
    return heads, rows


YEARS = {"fr": "Freshman", "so": "Sophomore", "jr": "Junior", "sr": "Senior", "gr": "Graduate", "gs": "Graduate",
         "r-fr": "Redshirt Freshman", "r-so": "Redshirt Sophomore", "r-jr": "Redshirt Junior", "r-sr": "Redshirt Senior",
         "rs-fr": "Redshirt Freshman", "rs-so": "Redshirt Sophomore", "rs-jr": "Redshirt Junior", "rs-sr": "Redshirt Senior",
         "5th": "Fifth Year", "6th": "Sixth Year", "freshman": "Freshman", "sophomore": "Sophomore", "junior": "Junior", "senior": "Senior",
         "redshirt freshman": "Redshirt Freshman", "redshirt sophomore": "Redshirt Sophomore", "redshirt junior": "Redshirt Junior", "redshirt senior": "Redshirt Senior"}


def class_year(raw):
    if not raw:
        return None
    key = raw.strip().rstrip(".").lower().replace("r.-", "r-").replace("rs.-", "r-")
    return YEARS.get(key, raw.strip())


def _player_name(raw):
    first_line = raw.split("\n")[0].strip()
    first_line = re.sub(r"^\d+\s+", "", first_line)
    if "," in first_line:
        last, first = [p.strip() for p in first_line.split(",", 1)]
        return f"{first} {last}"
    return first_line


def _num(value):
    try:
        return float(str(value).split("-")[0].replace(",", "").replace("%", ""))
    except ValueError:
        return 0.0


def sidearm_roster(url):
    """Jersey number and name -> position, class year, headshot from a Sidearm roster page."""
    page = get(url, as_json=False)
    by_number, by_name = {}, {}
    for block in re.split(r'<li[^>]*class="sidearm-roster-player[ "]', page)[1:]:
        name = re.search(r"<h3>\s*<a[^>]*>(.*?)</a>", block, flags=re.S)
        if not name:
            continue
        number = re.search(r'sidearm-roster-player-jersey-number">\s*([^<]*?)\s*<', block)
        pos = re.search(r'sidearm-roster-player-position-long-short hide-on-medium">\s*([^<]*?)\s*<', block)
        if not pos:  # some schools put the abbreviation straight in the bold span
            pos = re.search(r'sidearm-roster-player-position">\s*<span class="text-bold">\s*([^<]*?)\s*<', block)
        year = re.search(r'sidearm-roster-player-academic-year[^"]*">\s*([^<]*?)\s*<', block)
        img = re.search(r'sidearm-roster-player-image.*?<img[^>]*?(?:data-src|src)="([^"]+)"', block, flags=re.S)
        info = {
            "name": text(name.group(1)),
            "position": pos.group(1).strip() if pos else None,
            "year": class_year(year.group(1)) if year else None,
            "headshot": re.sub(r"width=\d+", "width=200", urllib.parse.urljoin(url, img.group(1))) if img and "no-photo" not in img.group(1) else None,
        }
        if number and number.group(1).strip():
            by_number[number.group(1).strip()] = info
        by_name[info["name"].lower()] = info
    return by_number, by_name


def with_roster(players, roster):
    by_number, by_name = roster
    for p in players:
        info = by_number.get(str(p.get("jersey")))
        if info and p["name"].split()[-1].lower() not in info["name"].lower():
            info = None
        if not info:
            info = by_name.get(p["name"].lower())
        if info:
            p.update({k: v for k, v in info.items() if k != "name"})
    return players


def sidearm_leaders(school):
    page = get(school["stats_url"], as_json=False)
    players = []
    _, passing = _sidearm_rows(page, "individual-offense-passing")
    passing = [r for r in passing if r.get("Player") and r["Player"] not in ("Total", "Opponents", "Team")]
    if passing:
        p = max(passing, key=lambda r: _num(r.get("YDS")))
        players.append({"label": "Passing", "name": _player_name(p["Player"]), "jersey": p.get("#"),
                        "line": _stat_line([f"{p.get('COMP')}/{p.get('ATT')}", f"{p.get('YDS')} yds", f"{p.get('TD')} TD", f"{p.get('INT')} INT", f"{p.get('Rating')} rating"])})
    _, rushing = _sidearm_rows(page, "individual-offense-rushing")
    rushing = [r for r in rushing if r.get("Player") and r["Player"] not in ("Total", "Opponents", "Team")]
    if rushing:
        p = max(rushing, key=lambda r: _num(r.get("Net")))
        players.append({"label": "Rushing", "name": _player_name(p["Player"]), "jersey": p.get("#"),
                        "line": _stat_line([f"{p.get('ATT')} car", f"{p.get('Net')} yds", f"{p.get('TD')} TD", f"{p.get('AVG')} avg"])})
    _, receiving = _sidearm_rows(page, "individual-offense-receiving")
    receiving = [r for r in receiving if r.get("Player") and r["Player"] not in ("Total", "Opponents", "Team")]
    if receiving:
        p = max(receiving, key=lambda r: _num(r.get("YDS")))
        players.append({"label": "Receiving", "name": _player_name(p["Player"]), "jersey": p.get("#"),
                        "line": _stat_line([f"{p.get('NO')} rec", f"{p.get('YDS')} yds", f"{p.get('TD')} TD", f"{p.get('AVG')} avg"])})
    _, defense = _sidearm_rows(page, "individual-defense")
    defense = [r for r in defense if r.get("Player") and r["Player"] not in ("Total", "Opponents", "Team")]
    if defense:
        p = max(defense, key=lambda r: _num(r.get("TOT")))
        players.append({"label": "Tackles", "name": _player_name(p["Player"]), "jersey": p.get("#"),
                        "line": _stat_line([f"{p.get('TOT')} tackles", f"{p.get('TFL-YDS', '').split('-')[0]} TFL" if p.get("TFL-YDS") else None, f"{p.get('Sacks-YDS', '').split('-')[0]} sacks" if p.get("Sacks-YDS") else None])})
        s = max(defense, key=lambda r: _num(r.get("Sacks-YDS")))
        if _num(s.get("Sacks-YDS")) > 0:
            players.append({"label": "Sacks", "name": _player_name(s["Player"]), "jersey": s.get("#"),
                            "line": _stat_line([f"{s.get('Sacks-YDS').split('-')[0]} sacks", f"{s.get('TFL-YDS', '').split('-')[0]} TFL" if s.get("TFL-YDS") else None, f"{s.get('TOT')} tackles"])})
        i = max(defense, key=lambda r: _num(r.get("INT")))
        if _num(i.get("INT")) > 0:
            players.append({"label": "Interceptions", "name": _player_name(i["Player"]), "jersey": i.get("#"),
                            "line": _stat_line([f"{i.get('INT')} INT", f"{i.get('BU')} PBU" if i.get("BU") else None, f"{i.get('TOT')} tackles"])})
    roster_url = school.get("roster_url") or school["stats_url"].rsplit("/", 1)[0] + "/roster"
    try:
        players = with_roster(players, sidearm_roster(roster_url))
    except (urllib.error.URLError, TimeoutError):
        pass
    return players


def top_players(school):
    if school["division"] == "FBS":
        return espn_leaders(school)
    return sidearm_leaders(school)


# ---------------------------------------------------------------- main

def main():
    DATA.mkdir(exist_ok=True)
    out = {"fetched_at": now().isoformat(timespec="seconds"), "season": SEASON, "teams": {}, "polls": {}, "d3football": {}, "hansen": {}, "errors": [], "stale": {}}
    previous = {}
    if (DATA / "season.json").exists():
        try:
            previous = json.loads((DATA / "season.json").read_text())
        except ValueError:
            previous = {}

    def carry(key, value):
        """Keep the last good copy of a source that failed this run, and say so."""
        old = previous.get(key)
        if old:
            out[key] = old
            out["stale"][key] = previous.get("stale", {}).get(key) or previous.get("fetched_at")
        else:
            out[key] = value
    for school in SCHOOLS:
        slug = school["slug"]
        try:
            games = team_games(school)
            summary = team_summary(school)
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as exc:
            out["errors"].append(f"{school['name']} schedule: {exc}")
            if previous.get("teams", {}).get(slug):
                out["teams"][slug] = previous["teams"][slug]
                out["stale"][slug] = previous.get("stale", {}).get(slug) or previous.get("fetched_at")
            continue
        played = [g for g in games if g["result"]]
        pf = sum(g["pf"] for g in played)
        pa = sum(g["pa"] for g in played)
        out["teams"][slug] = {
            **summary, "games": games, "played": len(played), "pf": pf, "pa": pa, "diff": pf - pa,
            "wins": sum(1 for g in played if g["result"] == "W"),
            "losses": sum(1 for g in played if g["result"] == "L"),
            "ties": sum(1 for g in played if g["result"] == "T"),
            "players": [],
        }
        upcoming = [g for g in games if g["state"] != "post"][:2]
        for g in upcoming:
            try:
                g["odds"] = espn_odds(g, school) if school["division"] == "FBS" else None
            except (urllib.error.URLError, ValueError, TimeoutError):
                g["odds"] = None
        try:
            out["teams"][slug]["players"] = top_players(school)
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError, IndexError) as exc:
            out["errors"].append(f"{school['name']} players: {exc}")
            out["teams"][slug]["players"] = previous.get("teams", {}).get(slug, {}).get("players", [])
    try:
        projections, week_path = hansen_projections()
        out["hansen_week"] = week_path
        for school in SCHOOLS:
            if not school.get("hansen_key") or school["slug"] not in out["teams"]:
                continue
            for g in [g for g in out["teams"][school["slug"]]["games"] if g["state"] != "post"][:2]:
                g["odds"] = hansen_odds(g, school, projections)
    except (urllib.error.URLError, ValueError, TimeoutError) as exc:
        out["errors"].append(f"hansen projections: {exc}")
    for name, fn in (("polls", polls), ("d3football", d3football_top25), ("hansen", hansen)):
        try:
            out[name] = fn()
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as exc:
            if name == "d3football":
                try:
                    out[name] = d3football_file()
                    continue
                except (ValueError, KeyError):
                    pass
            out["errors"].append(f"{name}: {exc}")
            carry(name, {})
    if previous.get("hansen_week") and not out.get("hansen_week"):
        out["hansen_week"] = previous["hansen_week"]
    (DATA / "season.json").write_text(json.dumps(out, indent=1))
    teams = ", ".join(f"{k} {v['record']} ({len(v['players'])} players)" for k, v in out["teams"].items())
    print(f"[{now():%Y-%m-%d %H:%M}] wrote data/season.json: {teams}")
    if out["errors"]:
        print("errors:", *out["errors"], sep="\n  ", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
