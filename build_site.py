#!/usr/bin/env python3
"""Render docs/index.html from schools.json, data/season.json, and data/massey.json.

Also copies pages/montlake.html to docs/montlake/index.html and adds the site
tab bar and analytics tag to it."""
import html
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
SCHOOLS = json.loads((BASE / "schools.json").read_text())
SEASON = json.loads((BASE / "data" / "season.json").read_text())
MASSEY = json.loads((BASE / "data" / "massey.json").read_text())
OUT = BASE / "docs" / "index.html"
MONTLAKE_SRC = BASE / "pages" / "montlake.html"
MONTLAKE_OUT = BASE / "docs" / "montlake" / "index.html"
EASTERN = ZoneInfo("America/New_York")
CENTRAL = ZoneInfo("America/Chicago")
BY_SLUG = {s["slug"]: s for s in SCHOOLS}
BROTHERS = json.loads((BASE / "content" / "brothers.json").read_text())
# One order for the whole page: Massey rank across all divisions, best first.
ORDERED = sorted(SCHOOLS, key=lambda x: MASSEY["teams"].get(x["slug"], {}).get("overall_rank", 9999))
NOW = datetime.now(timezone.utc)


def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def parse(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def kickoff_text(game):
    dt = parse(game["date"]).astimezone(EASTERN)
    if game.get("time_tbd"):
        return dt.strftime("%a %b %-d") + ", time TBA"
    return dt.strftime("%a %b %-d, %-I:%M %p ET")


def time_tag(game, fmt="full"):
    dt = parse(game["date"])
    label = kickoff_text(game) if fmt == "full" else dt.astimezone(EASTERN).strftime("%-I:%M %p ET")
    tbd = " data-tbd=\"1\"" if game.get("time_tbd") else ""
    return f'<time datetime="{esc(dt.isoformat())}" data-fmt="{fmt}"{tbd}>{esc(label)}</time>'


def signed(n):
    return f"+{n}" if n > 0 else str(n)


def fmt_num(value, digits=2):
    if value in (None, "NA", ""):
        return "–"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return esc(value)


def pct(value):
    if value in (None, "NA", ""):
        return "–"
    return f"{float(value) * 100:.0f}%"


def opponent_label(game):
    prefix = "vs " if game["home"] else "at "
    if game.get("neutral"):
        prefix = "vs "
    rank = f'<span class="rk">#{game["opponent"]["rank"]}</span> ' if game["opponent"].get("rank") else ""
    return f'{prefix}{rank}{esc(game["opponent"]["short"])}'


def result_text(game):
    if game["result"]:
        return f'{game["result"]} {game["pf"]}-{game["pa"]}'
    if game["state"] == "in":
        return f'{game["pf"] or 0}-{game["pa"] or 0}, {esc(game["status"])}'
    return ""


def tv_chips(game):
    nets = game.get("broadcasts") or []
    if not nets:
        return '<span class="chip tbd">TV TBA</span>'
    return "".join(f'<span class="chip">{esc(n)}</span>' for n in nets)


# ---------------------------------------------------------------- rankings helpers

def poll_badges(slug):
    school = BY_SLUG[slug]
    polls = SEASON.get("polls", {})
    badges = []

    def badge(label, rank, rv, have_poll=True):
        if not have_poll:
            return  # the poll itself is missing this run; say nothing rather than "NR"
        if rank:
            badges.append(f'<span class="badge"><b>#{rank}</b> {esc(label)}</span>')
        elif rv:
            badges.append(f'<span class="badge rv">RV {esc(label)}</span>')
        else:
            badges.append(f'<span class="badge nr">NR {esc(label)}</span>')

    if school["division"] == "FBS":
        for key, label in (("AP Poll", "AP"), ("AFCA Coaches Poll", "Coaches")):
            p = polls.get(key, {})
            badge(label, p.get("ranks", {}).get(slug), p.get("receiving_votes", {}).get(slug), bool(p.get("ranks")))
        cfp = next((p for k, p in polls.items() if "CFP" in k or "Playoff" in (p.get("name") or "")), None)
        if cfp:
            badge("CFP", cfp.get("ranks", {}).get(slug), None)
    else:
        d3 = SEASON.get("d3football", {})
        r = d3.get("ranks", {}).get(slug)
        badge("D3football.com", r["rank"] if r else None, d3.get("receiving_votes", {}).get(slug), bool(d3.get("label")))
        p = polls.get("AFCA Div III", {})
        badge("AFCA D3", p.get("ranks", {}).get(slug), p.get("receiving_votes", {}).get(slug), bool(p.get("ranks")))
    return "".join(badges)


def massey_line(slug):
    m = MASSEY["teams"].get(slug)
    if not m:
        return ""
    div = "FBS" if m["division"] == "FBS" else "D3"
    return (f'<span class="badge massey"><b>#{m["div_rank"]}</b> Massey {div}</span>'
            f'<span class="badge massey"><b>#{m["overall_rank"]}</b> Massey all divisions</span>')


def hansen_badge(slug):
    h = SEASON.get("hansen", {}).get("teams", {}).get(slug, {})
    pred = h.get("predictive")
    if not pred:
        return ""
    return (f'<a class="badge hansen" href="https://hansenratings.com/ratings/predictive/2026/" title="Hansen Ratings predictive rank" target="_blank" rel="noopener">'
            f'<b>#{pred["Rank"]}</b> Hansen</a>')


# ---------------------------------------------------------------- sections

def featured_games():
    """One game per team for This week: in progress, final within 36 hours, or upcoming within 8 days."""
    rows = []
    for school in ORDERED:
        team = SEASON["teams"].get(school["slug"])
        if not team:
            continue
        for g in team["games"]:
            dt = parse(g["date"])
            if g["state"] == "in":
                rows.append((school, g))
            elif g["state"] == "pre" and dt <= NOW + timedelta(days=8):
                rows.append((school, g))
            elif g["state"] == "post" and dt >= NOW - timedelta(hours=36):
                rows.append((school, g))
    # One card per team: the game in progress, else the final from the last 36 hours, else the next game.
    rank = {"in": 0, "post": 1, "pre": 2}
    best = {}
    for school, g in rows:
        current = best.get(school["slug"])
        if current is None or (rank[g["state"]], g["date"]) < (rank[current[1]["state"]], current[1]["date"]):
            best[school["slug"]] = (school, g)
    return sorted(best.values(), key=lambda r: r[1]["date"])


def game_card(school, g):
    opp = g["opponent"]
    opp_logo = f'<img src="{esc(opp["logo"])}" alt="">' if opp.get("logo") else '<span class="nologo"></span>'
    where = "Home" if g["home"] else "Away"
    if g.get("neutral"):
        where = "Neutral site"
    venue = ", ".join(x for x in (g.get("venue"), g.get("city")) if x)
    live = g["state"] == "in"
    final = g["state"] == "post"
    status_class = "live" if live else "final" if final else "pre"
    score = f'{g["pf"] if g["pf"] is not None else 0}<span class="dash">-</span>{g["pa"] if g["pa"] is not None else 0}' if (live or final) else ""
    status = esc(g["status"]) if live else (f'Final · {g["result"]}' if final else "")
    countdown = f'<span class="count" data-kick="{esc(parse(g["date"]).isoformat())}"></span>' if g["state"] == "pre" and not g.get("time_tbd") else ""
    rank = f'<span class="rk">#{opp["rank"]}</span> ' if opp.get("rank") else ""
    feed = g.get("live_feed") or {}
    feed_attrs = f' data-feed="{esc(feed["url"])}" data-feed-type="{esc(feed["type"])}"' if feed.get("url") else ""
    stats_links = [f'<a href="https://www.espn.com/college-football/game/_/gameId/{esc(g["id"])}" target="_blank" rel="noopener">ESPN</a>']
    if g.get("live_stats"):
        stats_links.insert(0, f'<a href="{esc(g["live_stats"])}" target="_blank" rel="noopener">Live stats</a>')
    return f'''<article class="game {status_class}" data-game="{esc(g["id"])}" data-group="{esc(g["group"])}" data-date="{esc(g["date"])}" data-home="{1 if g["home"] else 0}"{feed_attrs} style="--team:var(--c-{school["slug"]})">
<header><img src="{esc(school["logo"])}" alt=""><div><div class="who">{esc(school["name"])} <span class="muted">{esc(school["mascot"])}</span></div><div class="what">{"vs" if g["home"] or g.get("neutral") else "at"} {rank}{esc(opp["name"])}</div></div>{opp_logo}</header>
<div class="body">
<div class="scoreline"><span class="score">{score}</span><span class="status">{status}</span></div>
<div class="situation"></div>
<dl>
<dt>Kickoff</dt><dd>{time_tag(g)} {countdown}</dd>
<dt>Watch</dt><dd>{tv_chips(g)}</dd>
<dt>Where</dt><dd>{esc(where)}{" · " + esc(venue) if venue else ""}</dd>
<dt>Stats</dt><dd>{" · ".join(stats_links)}</dd>
{odds_rows(school, g)}
</dl>
</div></article>'''


def odds_rows(school, g):
    odds = g.get("odds") or {}
    if g["state"] == "post" or not odds:
        return ""
    rows = []
    line = odds.get("line")
    if line:
        ml = ""
        if line.get("home_ml") is not None and line.get("away_ml") is not None:
            mine = line["home_ml"] if g["home"] else line["away_ml"]
            ml = f', {esc(school["name"])} {"+" if mine > 0 else ""}{mine} moneyline'
        rows.append(f'<dt>Line</dt><dd>{esc(line["details"])}, over/under {esc(line["over_under"])}{ml} <span class="src">{esc(line["provider"])}</span></dd>')
    prob = odds.get("win_prob")
    proj = odds.get("projection")
    if prob:
        extra = f', projected {proj["mine"]}-{proj["opp"]}' if proj else ""
        src = esc(prob["source"])
        if "Hansen" in prob["source"]:
            week = SEASON.get("hansen_week") or "/projections/2026/"
            href = "https://hansenratings.com" + week if week.startswith("/") else week
            src = f'<a href="{href}" target="_blank" rel="noopener">{src}</a>'
        rows.append(f'<dt>Win odds</dt><dd>{esc(school["name"])} {prob["pct"]:g}%{extra} <span class="src">{src}</span></dd>')
    return "".join(rows)


def platforms_section():
    path = BASE / "content" / "platforms.json"
    if not path.exists():
        return ""
    used = set()
    for team in SEASON["teams"].values():
        for g in team["games"]:
            used.update(g.get("broadcasts") or [])
    cards = []
    for p in json.loads(path.read_text()):
        names = [p["name"]] + p.get("also", [])
        on_schedule = any(n in used for n in names)
        tag = '<span class="chip free">Free</span>' if p["free"] else ('<span class="chip paid">Subscription</span>' if p["free"] is False else '<span class="chip">Price not published</span>')
        sched = '<span class="chip">On a schedule now</span>' if on_schedule else ""
        also = f' <span class="muted">({esc(", ".join(p["also"]))})</span>' if p.get("also") else ""
        note = f'<p class="small">{esc(p["note"])}</p>' if p.get("note") else ""
        if p.get("local"):
            parts = [f"{esc(st)} in the {esc(m)} area" for m, st in p["local"].items()]
            stations = " and ".join(parts) if len(parts) <= 2 else ", ".join(parts[:-1]) + ", and " + parts[-1]
            note += f'<p class="small"><b>Local stations:</b> {stations}.</p>'
        cards.append(f'<article class="platform"><h3><a href="{esc(p["url"])}" target="_blank" rel="noopener">{esc(p["name"])}</a>{also}</h3><div class="chips">{tag}<span class="chip">{esc(p["kind"])}</span>{sched}</div><p><b>Teams:</b> {esc(p["teams"])}</p><p>{esc(p["access"])}</p>{note}</article>')
    return '<div class="platforms">' + "".join(cards) + "</div>"


def this_week():
    cards = [game_card(s, g) for s, g in featured_games()]
    if not cards:
        return '<p class="muted">No games in the next week.</p>'
    return '<div class="games">' + "\n".join(cards) + "</div>"


def last_and_next(team):
    played = [g for g in team["games"] if g["result"]]
    upcoming = [g for g in team["games"] if g["state"] != "post"]
    last = played[-1] if played else None
    nxt = upcoming[0] if upcoming else None
    parts = []
    if last:
        parts.append(f'<dt>Last</dt><dd>{result_text(last)} {opponent_label(last)}</dd>')
    if nxt:
        parts.append(f'<dt>Next</dt><dd>{opponent_label(nxt)}, {time_tag(nxt)}</dd>')
    return "".join(parts)


def conference_line(school, team):
    """ESPN's standing text for Division I; a conference record computed from results for Division III."""
    members = school.get("conference_members")
    if not members:
        return team.get("standing") or ""
    w = l = t = 0
    for g in team.get("games", []):
        if g.get("state") != "post" or g["opponent"].get("short") not in members:
            continue
        w += g.get("result") == "W"
        l += g.get("result") == "L"
        t += g.get("result") == "T"
    rec = f"{w}-{l}" + (f"-{t}" if t else "")
    return f'{rec} {school["conference"]}'


def team_card(school):
    team = SEASON["teams"].get(school["slug"])
    if not team:
        return f'<article class="team"><header style="background:{esc(school["color"])}"><img src="{esc(school["logo"])}" alt=""><div class="who">{esc(school["name"])}</div></header><div class="body"><p class="muted">Data unavailable.</p></div></article>'
    avg = team["diff"] / team["played"] if team["played"] else 0
    record = team["record"] or f'{team["wins"]}-{team["losses"]}' + (f'-{team["ties"]}' if team["ties"] else "")
    return f'''<article class="team" id="team-{school["slug"]}" style="--team:var(--c-{school["slug"]})">
<header style="background:{esc(school["color"])};color:{esc(school["text"])}"><img src="{esc(school["logo"])}" alt="{esc(school["name"])} logo"><div><div class="who">{esc(school["name"])} {esc(school["mascot"])}</div><div class="what">{esc(school["division_label"])} · {esc(school["conference"])} · {esc(school["city"])}</div></div><span class="alum">{esc(" and ".join(school.get("alumni", [])))}</span></header>
<div class="body">
<div class="record"><span class="big">{esc(record)}</span><span class="standing">{esc(conference_line(school, team))}</span></div>
<div class="badges">{poll_badges(school["slug"])}{massey_line(school["slug"])}{hansen_badge(school["slug"])}</div>
<dl>
<dt>Points</dt><dd>{team["pf"]} for, {team["pa"]} against</dd>
<dt>Margin</dt><dd><b class="{ "pos" if team["diff"] > 0 else "neg" if team["diff"] < 0 else ""}">{signed(team["diff"])}</b> total, {signed(round(avg, 1))} per game</dd>
{last_and_next(team)}
</dl>
<p class="meta"><a href="{esc(school["schedule_url"])}" target="_blank" rel="noopener">Official schedule</a> · <a href="#sched-{school["slug"]}" class="tablink" data-tab="{school["slug"]}">Full schedule below</a></p>
</div></article>'''


def ratings_table():
    polls = SEASON.get("polls", {})
    d3 = SEASON.get("d3football", {})
    hansen = SEASON.get("hansen", {}).get("teams", {})
    head = ("<tr><th>Team</th><th>Record</th><th>Poll</th><th>Massey rating</th><th>Massey rank in division</th><th>Massey rank all divisions</th>"
            "<th>Massey power</th><th>Massey offense</th><th>Massey defense</th><th>Massey SOS</th><th>Massey expected W-L</th><th>Points for</th><th>Points against</th><th>Margin</th></tr>")
    rows = []
    ordered = ORDERED
    for s in ordered:
        team = SEASON["teams"].get(s["slug"], {})
        m = MASSEY["teams"].get(s["slug"], {})
        if s["division"] == "FBS":
            ap = polls.get("AP Poll", {}).get("ranks", {}).get(s["slug"])
            co = polls.get("AFCA Coaches Poll", {}).get("ranks", {}).get(s["slug"])
            poll = f'AP {"#" + str(ap) if ap else "NR"}, Coaches {"#" + str(co) if co else "NR"}'
        else:
            r = d3.get("ranks", {}).get(s["slug"])
            rv = d3.get("receiving_votes", {}).get(s["slug"])
            poll = f'D3football.com #{r["rank"]}' if r else (f"D3football.com RV ({rv})" if rv else "D3football.com NR")
        div_label = "FBS" if m.get("division") == "FBS" else "D3"
        rows.append(
            f'<tr><td class="lead"><img src="{esc(s["logo"])}" alt=""> {esc(s["name"])}</td><td>{esc(team.get("record"))}</td><td>{esc(poll)}</td>'
            f'<td>{fmt_num(m.get("rating"))}</td><td>#{m.get("div_rank")} of {MASSEY["division_sizes"].get(m.get("division"), "")} {div_label}</td><td>#{m.get("overall_rank")} of {MASSEY["division_sizes"].get("all")}</td>'
            f'<td>#{m.get("pwr_rank")} ({fmt_num(m.get("pwr"))})</td><td>#{m.get("off_rank")} ({fmt_num(m.get("off"))})</td><td>#{m.get("def_rank")} ({fmt_num(m.get("def"))})</td><td>#{m.get("sos_rank")} ({fmt_num(m.get("sos"))})</td>'
            f'<td>{fmt_num(m.get("exp_w"), 1)}-{fmt_num(m.get("exp_l"), 1)}</td><td>{team.get("pf")}</td><td>{team.get("pa")}</td><td class="{ "pos" if team.get("diff", 0) > 0 else "neg" if team.get("diff", 0) < 0 else ""}">{signed(team.get("diff", 0))}</td></tr>')
    return f'<div class="tablewrap"><table class="ratings"><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table></div>'


def hansen_table():
    hansen = SEASON.get("hansen", {})
    teams = hansen.get("teams", {})
    if not teams:
        return ""
    head = ("<tr><th>Team</th><th>Predictive rank</th><th>Rating</th><th>Adj. offense</th><th>Adj. defense</th><th>Elo</th><th>Résumé rank</th><th>SOS rank</th>"
            "<th>Projected record</th><th>Projected NPI</th><th>Playoff odds</th><th>Pool A (auto bid)</th><th>Pool C (at large)</th></tr>")
    rows = []
    ordered = sorted(SCHOOLS, key=lambda x: (teams.get(x["slug"], {}).get("predictive") or {}).get("Rank", 9999))
    for s in ordered:
        h = teams.get(s["slug"])
        if not h:
            continue
        p, r, sos, sim = h.get("predictive", {}), h.get("resume", {}), h.get("sos", {}), h.get("simulation", {})
        rows.append(
            f'<tr><td class="lead"><img src="{esc(s["logo"])}" alt=""> {esc(s["name"])}</td><td>#{p.get("Rank")} (prev #{p.get("Prev")})</td><td>{fmt_num(p.get("Rating"), 1)}</td>'
            f'<td>{fmt_num(p.get("AdjO"), 1)}</td><td>{fmt_num(p.get("AdjD"), 1)}</td><td>{fmt_num(p.get("Elo"), 0)}</td><td>#{r.get("Rank")}</td><td>#{sos.get("Rank")}</td>'
            f'<td>{fmt_num(sim.get("W"), 1)}-{fmt_num(sim.get("L"), 1)}</td><td>{fmt_num(sim.get("NPI"), 1)} (#{fmt_num(sim.get("Rank"), 0)})</td>'
            f'<td>{pct(sim.get("Playoff"))}</td><td>{pct(sim.get("Pool A"))}</td><td>{pct(sim.get("Pool C"))}</td></tr>')
    return f'<div class="tablewrap"><table class="ratings"><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table></div>'


def players_section():
    blocks = []
    for s in ORDERED:
        team = SEASON["teams"].get(s["slug"], {})
        players = team.get("players") or []
        if not players:
            continue
        cards = []
        for p in players:
            if p.get("headshot"):
                face = f'<img class="face" src="{esc(p["headshot"])}" alt="">'
            else:
                initials = "".join(w[0] for w in (p.get("name") or "?").split()[:2])
                face = f'<span class="face initials" style="background:{esc(s["color"])};color:{esc(s["text"])}">{esc(initials)}</span>'
            sub = " · ".join(x for x in (p.get("position"), f'#{p["jersey"]}' if p.get("jersey") else None, p.get("year")) if x)
            cards.append(f'<div class="player">{face}<div><span class="label">{esc(p["label"])}</span><div class="pname">{esc(p["name"])}</div><div class="psub">{esc(sub)}</div><div class="pline">{esc(p["line"])}</div></div></div>')
        blocks.append(f'<div class="teamplayers" style="--team:var(--c-{s["slug"]})"><h3><img src="{esc(s["logo"])}" alt=""> {esc(s["name"])} {esc(s["mascot"])}</h3><div class="players">{"".join(cards)}</div></div>')
    return "\n".join(blocks)


def schedule_table(school, team):
    rows = []
    for g in team["games"]:
        res = result_text(g)
        cls = "w" if g["result"] == "W" else "l" if g["result"] == "L" else "live" if g["state"] == "in" else ""
        when = time_tag(g) if g["state"] != "post" else parse(g["date"]).astimezone(EASTERN).strftime("%a %b %-d")
        site = "Neutral" if g.get("neutral") else ("Home" if g["home"] else "Away")
        rows.append(f'<tr class="{cls}" data-game="{esc(g["id"])}" data-group="{esc(g["group"])}"><td class="lead">{g["week"] or ""}</td><td>{when}</td><td class="opp">{opponent_label(g)}</td><td>{esc(site)}</td><td class="tv">{tv_chips(g) if g["state"] != "post" else esc(", ".join(g.get("broadcasts") or []))}</td><td class="res">{res}</td></tr>')
    return f'<div class="tablewrap"><table class="sched"><thead><tr><th>Wk</th><th>Date</th><th>Opponent</th><th>Site</th><th>TV</th><th>Result</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def schedules():
    tabs = ['<button class="tab active" data-tab="all">All five</button>'] + [f'<button class="tab" data-tab="{s["slug"]}" style="--team:var(--c-{s["slug"]})">{esc(s["name"])}</button>' for s in ORDERED]
    panes = []
    all_rows = []
    for s in ORDERED:
        team = SEASON["teams"].get(s["slug"])
        if not team:
            continue
        panes.append(f'<div class="pane" id="sched-{s["slug"]}" data-pane="{s["slug"]}" hidden>{schedule_table(s, team)}</div>')
        for g in team["games"]:
            all_rows.append((g["date"], s, g))
    rows = []
    for _, s, g in sorted(all_rows, key=lambda r: r[0]):
        res = result_text(g)
        cls = "w" if g["result"] == "W" else "l" if g["result"] == "L" else "live" if g["state"] == "in" else ""
        when = time_tag(g) if g["state"] != "post" else parse(g["date"]).astimezone(EASTERN).strftime("%a %b %-d")
        rows.append(f'<tr class="{cls}" data-game="{esc(g["id"])}" data-group="{esc(g["group"])}"><td class="lead"><img src="{esc(s["logo"])}" alt=""> {esc(s["name"])}</td><td>{when}</td><td class="opp">{opponent_label(g)}</td><td class="tv">{tv_chips(g) if g["state"] != "post" else esc(", ".join(g.get("broadcasts") or []))}</td><td class="res">{res}</td></tr>')
    all_pane = f'<div class="pane" id="sched-all" data-pane="all"><div class="tablewrap"><table class="sched"><thead><tr><th>Team</th><th>Date</th><th>Opponent</th><th>TV</th><th>Result</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></div>'
    return f'<div class="tabs">{"".join(tabs)}</div>{all_pane}{"".join(panes)}'


def margin_chart():
    series = []
    max_games = 1
    lo, hi = 0, 0
    for s in SCHOOLS:
        team = SEASON["teams"].get(s["slug"])
        if not team:
            continue
        cum, pts = 0, [(0, 0)]
        for i, g in enumerate([g for g in team["games"] if g["result"]], 1):
            cum += g["pf"] - g["pa"]
            pts.append((i, cum))
            lo, hi = min(lo, cum), max(hi, cum)
        max_games = max(max_games, len(pts) - 1)
        series.append((s, pts))
    W, H, PL, PR, PT, PB = 720, 300, 44, 16, 16, 34
    span = (hi - lo) or 1
    def x(i):
        return PL + (W - PL - PR) * i / max(max_games, 1)
    def y(v):
        return PT + (H - PT - PB) * (hi - v) / span
    parts = [f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="Cumulative point margin by game">']
    step = max(10, round(span / 6 / 10) * 10)
    v = (lo // step) * step
    while v <= hi:
        parts.append(f'<line x1="{PL}" x2="{W-PR}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid{" zero" if v == 0 else ""}"/><text x="{PL-6}" y="{y(v)+4:.1f}" class="lab" text-anchor="end">{signed(int(v))}</text>')
        v += step
    for i in range(0, max_games + 1):
        parts.append(f'<text x="{x(i):.1f}" y="{H-12}" class="lab" text-anchor="middle">{i if i else ""}</text>')
    parts.append(f'<text x="{(PL+W-PR)/2:.1f}" y="{H-1}" class="lab" text-anchor="middle">Games played</text>')
    for s, pts in series:
        d = " ".join(f'{"M" if i == 0 else "L"}{x(i):.1f},{y(v):.1f}' for i, v in pts)
        parts.append(f'<path d="{d}" class="line" style="stroke:var(--c-{s["slug"]})"/>')
        li, lv = pts[-1]
        parts.append(f'<circle cx="{x(li):.1f}" cy="{y(lv):.1f}" r="4" style="fill:var(--c-{s["slug"]})"/>')
    parts.append("</svg>")
    legend = "".join(f'<span class="lg" style="--team:var(--c-{s["slug"]})"><i></i>{esc(s["name"])} {signed(pts[-1][1])}</span>' for s, pts in series)
    return "".join(parts) + f'<div class="legend">{legend}</div>'


# ---------------------------------------------------------------- site tabs

GOATCOUNTER = '<script data-goatcounter="https://almamatersaturday.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>'

# The tab bar sits on two pages with different token names, so every color
# names the Alma Mater Saturday token first and the Montlake token second.
NAV_CSS = r"""
.sitenav{background:var(--surface2,var(--paper-2,#f2f2f2))}
.sitenav-in{max-width:var(--sn-max);margin:0 auto;padding:8px var(--sn-pad);display:flex;flex-wrap:wrap;gap:6px}
.sn{font-family:"Barlow Condensed","Avenir Next Condensed","Arial Narrow",sans-serif;font-size:1rem;font-weight:600;line-height:1.5;text-decoration:none;color:var(--ink,#1e2229);background:var(--surface,var(--paper,#fff));border:1px solid var(--line,#d8d5cb);border-radius:999px;padding:6px 14px}
.sn:hover{border-color:var(--ink,#1e2229)}
.sn:focus-visible{outline:2px solid var(--accent,var(--hawk-blue,#1f5fbf));outline-offset:2px}
.sn[aria-current="page"]{background:var(--ink,#1e2229);color:var(--surface,var(--paper,#fff));border-color:transparent;font-weight:700}
"""

PAGES = [("index", "Alma Mater Saturday"), ("montlake", "Montlake &amp; Lumen")]


def site_nav(active):
    """Return the tab bar for the page named `active`, with links relative to that page."""
    up = "../" if active != "index" else ""
    links = []
    for slug, label in PAGES:
        href = up if slug == "index" else f"{up}{slug}/"
        href = href or "./"
        current = ' aria-current="page"' if slug == active else ""
        links.append(f'<a class="sn" href="{href}"{current}>{label}</a>')
    return f'<nav class="sitenav" aria-label="Pages"><div class="sitenav-in">{"".join(links)}</div></nav>'


def build_montlake():
    """Publish the hand-edited Montlake page with the tab bar and analytics tag."""
    src = MONTLAKE_SRC.read_text()
    for marker in ("</head>", "<!--SITENAV-->"):
        if src.count(marker) != 1:
            raise SystemExit(f"{MONTLAKE_SRC}: expected one {marker}")
    head = f'<link rel="icon" href="../assets/washington.png">\n{GOATCOUNTER}\n<style>:root{{--sn-max:760px;--sn-pad:18px}}{NAV_CSS}</style>\n</head>'
    page = src.replace("</head>", head).replace("<!--SITENAV-->", site_nav("montlake"))
    MONTLAKE_OUT.parent.mkdir(parents=True, exist_ok=True)
    MONTLAKE_OUT.write_text(page)
    print(f"wrote {MONTLAKE_OUT} ({len(page)} bytes)")


# ---------------------------------------------------------------- page

CSS = r"""
:root{color-scheme:light;--bg:#f4f3ef;--surface:#ffffff;--surface2:#ecebe5;--line:#d8d5cb;--ink:#1e2229;--muted:#616873;--faint:#8c939d;--link:#1f4e79;--pos:#2e8b57;--neg:#c0504d;--live:#d6323c;--accent:#1f5fbf;--chip:#e9e7df;--on-team:#ffffff;
--c-washington:#4b2e83;--c-indiana:#990000;--c-calvin:#8c2131;--c-hope:#c45114;--c-wheaton:#00407e}
:root[data-theme="dark"]{color-scheme:dark;--bg:#15181d;--surface:#1d2128;--surface2:#252a32;--line:#363c46;--ink:#e7e9ec;--muted:#a7adb7;--faint:#7d848f;--link:#8ab8e6;--pos:#5fc08a;--neg:#e2807c;--accent:#7fb0ff;--chip:#2e343d;--on-team:#15181d;
--c-washington:#b7a0e6;--c-indiana:#ff8a8a;--c-calvin:#f0a3ad;--c-hope:#ffa26b;--c-wheaton:#8fbdf2}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--bg:#15181d;--surface:#1d2128;--surface2:#252a32;--line:#363c46;--ink:#e7e9ec;--muted:#a7adb7;--faint:#7d848f;--link:#8ab8e6;--pos:#5fc08a;--neg:#e2807c;--accent:#7fb0ff;--chip:#2e343d;--on-team:#15181d;
--c-washington:#b7a0e6;--c-indiana:#ff8a8a;--c-calvin:#f0a3ad;--c-hope:#ffa26b;--c-wheaton:#8fbdf2}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 "Barlow",-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
a{color:var(--link)}img{max-width:100%}
main{max-width:1080px;margin:0 auto;padding:20px 16px 64px}
h1,h2,h3,.big,.score,.tab{font-family:"Barlow Condensed","Avenir Next Condensed","Arial Narrow",sans-serif}
h1{font-size:2.6rem;line-height:1;margin:.1em 0 .1em;letter-spacing:.01em}h2{font-size:1.6rem;margin:2.2em 0 .5em;padding-bottom:.2em;border-bottom:1px solid var(--line)}h3{font-size:1.25rem;margin:1.2em 0 .5em;display:flex;align-items:center;gap:8px}h3 img{height:26px;width:26px;object-fit:contain}
.top{display:flex;flex-direction:column;align-items:flex-start;gap:14px}.sub{color:var(--muted);margin:0 0 .4em;max-width:760px}
.muted{color:var(--muted)}.small{font-size:.9rem;color:var(--muted)}.pos{color:var(--pos)}.neg{color:var(--neg)}
button{font:inherit;cursor:pointer}
.controls{display:flex;gap:16px;align-items:flex-start}.ctl{display:flex;flex-direction:column;gap:4px}.seg{display:inline-flex;align-items:stretch;border:1px solid var(--line);border-radius:999px;overflow:hidden;background:var(--surface)}.seglabel{font-size:.72rem;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);padding-left:2px}.tz,.th{border:0;background:transparent;color:var(--muted);padding:9px 14px;font:inherit;font-size:.95rem;cursor:pointer;min-width:44px}.tz+.tz,.th+.th{border-left:1px solid var(--line)}.tz.active,.th.active{background:var(--accent);color:#fff;font-weight:700}.tz.active::before,.th.active::before{content:"\2713\00a0"}:root[data-theme="dark"] .tz.active,:root[data-theme="dark"] .th.active{color:#15181d}@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .tz.active,:root:not([data-theme="light"]) .th.active{color:#15181d}}@media (max-width:640px){.controls{width:100%;flex-wrap:wrap;gap:10px 16px}}.alum{margin-left:auto;align-self:flex-start;font-size:.75rem;font-weight:600;letter-spacing:.04em;text-transform:uppercase;border:1px solid currentColor;border-radius:999px;padding:2px 8px;opacity:.9;white-space:nowrap}
.livepill{display:none;align-items:center;gap:6px;font-size:.85rem;font-weight:600;color:var(--live)}.livepill i{width:8px;height:8px;border-radius:50%;background:var(--live);animation:pulse 1.4s infinite}body.has-live .livepill{display:inline-flex}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.games{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.game,.team{background:var(--surface);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.game header,.team header{display:flex;align-items:center;gap:12px;padding:12px 14px}
.game header{border-bottom:1px solid var(--line)}.game header img,.game header .nologo{width:40px;height:40px;object-fit:contain;flex:none}.game header div{flex:1;min-width:0}
.who{font-weight:700;line-height:1.2}.what{font-size:.9rem;color:var(--muted)}.team header .what{color:inherit;opacity:.85}
.team header img{width:52px;height:52px;object-fit:contain;flex:none;background:rgba(255,255,255,.92);border-radius:10px;padding:4px}
.body{padding:12px 14px 14px}
.scoreline{display:flex;align-items:baseline;justify-content:space-between;gap:10px;min-height:1.2em;margin-bottom:6px}.score{font-size:2rem;font-weight:700;line-height:1}.dash{color:var(--faint);padding:0 .1em}.status{font-weight:600;color:var(--muted)}
.game.live .status{color:var(--live)}.game.live .scoreline .status::before{content:"";display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--live);margin-right:6px;animation:pulse 1.4s infinite}
dl{display:grid;grid-template-columns:max-content 1fr;gap:4px 12px;margin:0;font-size:.95rem}dt{color:var(--muted)}dd{margin:0}
.situation{display:none;margin:0 0 10px;padding:8px 10px;border-radius:10px;background:var(--surface2);font-size:.9rem;line-height:1.35}.situation.on{display:block}.situation .poss{font-weight:700;color:var(--ink)}.situation .poss.mine{color:var(--team)}.situation .poss::before{content:"";display:inline-block;width:10px;height:7px;border-radius:50%;background:currentColor;margin-right:5px;vertical-align:1px}.situation .dd{font-weight:600}.situation .half{font-weight:600}.situation .last{color:var(--muted);margin-top:3px}
.chip{display:inline-block;background:var(--chip);border-radius:6px;padding:1px 7px;font-size:.85rem;margin:1px 4px 1px 0;white-space:nowrap}.chip.tbd{color:var(--muted)}
.count{color:var(--muted);font-size:.9rem}
.teams{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.record{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:6px}.big{font-size:2.4rem;font-weight:700;line-height:1;color:var(--team)}.standing{color:var(--muted)}
.badges{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 10px}.badge{font-size:.8rem;border:1px solid var(--line);border-radius:6px;padding:2px 7px;background:var(--surface2)}.badge b{color:var(--team)}a.badge{color:inherit;text-decoration:none}a.badge:hover{border-color:var(--team)}.sitelink{font-size:.8rem;font-weight:600;border:1px solid var(--team);border-radius:999px;padding:3px 10px;text-decoration:none;color:var(--team);white-space:nowrap;margin-left:auto}.sitelink:hover{background:var(--team);color:var(--on-team)}.badge.rv,.badge.nr{color:var(--muted)}
.rk{font-size:.8em;color:var(--muted);font-weight:600}
.meta{font-size:.9rem;color:var(--muted);margin:10px 0 0}
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:.93rem}th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:center;white-space:nowrap}th{background:var(--surface2);font-weight:600;font-size:.82rem;text-transform:uppercase;letter-spacing:.03em;color:var(--muted)}
tbody tr:last-child td{border-bottom:0}td.lead,td:first-child,th:first-child{text-align:left}td.lead img{height:20px;width:20px;object-fit:contain;vertical-align:-4px;margin-right:4px}
tr.w td.res{color:var(--pos);font-weight:600}tr.l td.res{color:var(--neg);font-weight:600}tr.live td.res{color:var(--live);font-weight:600}td.tv{white-space:normal;min-width:120px}
.tabs{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}.tab{border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:999px;padding:6px 14px;font-size:1rem}.tab.active{background:var(--team,var(--ink));color:var(--on-team);border-color:transparent;font-weight:700}
.teamplayers{margin-bottom:8px}.players{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px}
.player{display:flex;gap:12px;align-items:center;min-width:0;background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:10px 12px}.player .label{display:block;font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;color:var(--team);font-weight:700}
.face{width:48px;height:48px;border-radius:50%;object-fit:cover;background:var(--surface2);flex:none}.initials{display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:1rem}
.player>div{min-width:0}.pname{font-weight:700;line-height:1.2}.psub{font-size:.82rem;color:var(--muted)}.pline{font-size:.9rem;margin-top:2px}
.chart{width:100%;height:auto;background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:6px}.chart .grid{stroke:var(--line);stroke-width:1}.chart .grid.zero{stroke:var(--faint);stroke-width:1.5}.chart .lab{fill:var(--muted);font-size:11px}.chart .line{fill:none;stroke-width:2.5;stroke-linejoin:round}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;margin-top:8px;font-size:.9rem}.lg i{display:inline-block;width:14px;height:4px;background:var(--team);margin-right:6px;vertical-align:middle;border-radius:2px}
.src{font-size:.78rem;color:var(--muted);margin-left:4px}.chip.free{background:var(--pos);color:#fff}.chip.paid{background:var(--neg);color:#fff}
.platforms{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}.platform{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:12px 14px}.platform h3{margin:0 0 6px;font-size:1.2rem}.platform p{margin:.4em 0;font-size:.93rem}.platform .chips{margin-bottom:6px}
.more{margin-top:3em;padding:16px 18px;border:1px solid var(--line);border-radius:12px;background:var(--surface)}.more h2{margin:0 0 .4em;border:0;padding:0;font-size:1.2rem}.more p{margin:0}
footer{margin-top:28px;font-size:.85rem;color:var(--muted);line-height:1.6}
@media (max-width:640px){h1{font-size:2.1rem}.score{font-size:1.7rem}.big{font-size:2rem}main{padding-top:14px}}
thead th[aria-sort]{cursor:pointer;user-select:none}thead th[aria-sort]::after{content:"";display:inline-block;width:.9em;color:var(--faint,var(--muted))}thead th[aria-sort="ascending"]::after{content:"\25B4"}thead th[aria-sort="descending"]::after{content:"\25BE"}
h3.spaced{margin-top:1.6em}
"""

JS = r"""
(function(){
const root=document.documentElement;
const saved=(()=>{try{return localStorage.getItem('ams-theme')}catch(e){return null}})();
if(saved==='dark'||saved==='light')root.setAttribute('data-theme',saved);
function isDark(){const t=root.getAttribute('data-theme');return t==='dark'||(!t&&matchMedia('(prefers-color-scheme:dark)').matches)}
function paintTheme(){const dark=isDark();document.querySelectorAll('.th').forEach(b=>b.classList.toggle('active',(b.dataset.theme==='dark')===dark));document.querySelectorAll('meta[name=theme-color]').forEach(m=>{m.removeAttribute('media');m.content=dark?'#15181d':'#f4f3ef'});}
document.querySelectorAll('.th').forEach(b=>b.addEventListener('click',()=>{root.setAttribute('data-theme',b.dataset.theme);try{localStorage.setItem('ams-theme',b.dataset.theme)}catch(e){}paintTheme();}));
matchMedia('(prefers-color-scheme:dark)').addEventListener('change',paintTheme);
paintTheme();

// Kickoff times in the chosen time zone: Eastern, Central, or the device's own.
const deviceTz=Intl.DateTimeFormat().resolvedOptions().timeZone||'America/New_York';
const tzNames={'America/New_York':'Eastern time','America/Chicago':'Central time'};
let tzChoice=(()=>{try{return localStorage.getItem('ams-tz')}catch(e){return null}})()||'local';
function zone(){return tzChoice==='local'?deviceTz:tzChoice}
function renderTimes(){
  const z=zone();
  document.querySelectorAll('time[datetime]').forEach(t=>{
    if(t.dataset.tbd)return;
    const d=new Date(t.getAttribute('datetime'));
    const opts=t.dataset.fmt==='full'?{weekday:'short',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short',timeZone:z}:{hour:'numeric',minute:'2-digit',timeZoneName:'short',timeZone:z};
    t.textContent=new Intl.DateTimeFormat('en-US',opts).format(d);
  });
  document.querySelectorAll('.tz').forEach(b=>b.classList.toggle('active',b.dataset.tz===tzChoice));
  const note=document.getElementById('tznote');
  if(note)note.textContent='Kickoff times are in '+(tzChoice==='local'?"your device's time zone ("+deviceTz.replace(/_/g,' ')+")":tzNames[tzChoice])+'.';
}
document.querySelectorAll('.tz').forEach(b=>b.addEventListener('click',()=>{tzChoice=b.dataset.tz;try{localStorage.setItem('ams-tz',tzChoice)}catch(e){}renderTimes();}));
renderTimes();

// Countdowns.
function tick(){
  const now=Date.now();
  document.querySelectorAll('.count[data-kick]').forEach(el=>{
    const ms=new Date(el.dataset.kick)-now;
    if(ms<=0){el.textContent='';return}
    const m=Math.floor(ms/60000),d=Math.floor(m/1440),h=Math.floor((m%1440)/60),mm=m%60;
    el.textContent='in '+(d?d+'d ':'')+(d||h?h+'h ':'')+(d?'':mm+'m');
  });
}
tick();setInterval(tick,60000);

// Live scores: ESPN for every game, plus the stat crew's own feed (Sidearm or PrestoSports)
// for the ball, down and distance, and the last play when ESPN has none (Division III).
const API='https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard';
const cards=[...document.querySelectorAll('.game[data-game]')];
function etParts(iso){const p=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',year:'numeric',month:'numeric',day:'numeric'}).formatToParts(new Date(iso));const g=k=>p.find(x=>x.type===k).value;return {y:g('year'),m:g('month'),d:g('day')};}
function etDate(iso){const t=etParts(iso);return t.y+t.m.padStart(2,'0')+t.d.padStart(2,'0');}
function mdy(iso){const t=etParts(iso);return t.m+'/'+t.d+'/'+t.y;}
function inWindow(c,now){const t=new Date(c.dataset.date).getTime();return c.classList.contains('live')||(t-now<30*60000&&now-t<5*3600000);}
function windowOpen(){const now=Date.now();return cards.some(c=>inWindow(c,now));}
function escHtml(t){return String(t).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function ordinal(n){return ['','1st','2nd','3rd','4th'][n]||(n>4?'OT'+(n>5?n-4:''):'');}
// Sidearm writes players as "Last,First" and tacklers as "(A,B;C,D)"; readers want "First Last".
function fixNames(t){return String(t||'').replace(/((?:(?:de|van|von|der|den|la|le|del|da|di|du) )*[A-Z][\w'\-]*(?:, ?(?:Jr|Sr|II|III|IV)\.?)?),([A-Z][\w'\-.]*)/g,'$2 $1').replace(/;(?=\S)/g,'; ');}
// Feeds mark the side of the field as H/V (home/visitor) or by the crew's team id; show the team's name instead.
function sideName(prefix,home,away){const p=String(prefix||'');const u=p.toUpperCase();if(u===String(home.id||'').toUpperCase()||/^(H|HOME)$/.test(u))return home.name;if(u===String(away.id||'').toUpperCase()||/^(V|VIS|VISITOR|A|AWAY)$/.test(u))return away.name;return p;}
function fixSpots(t,home,away){return String(t||'').replace(/\b(H|V|HOME|VIS|VISITOR)(\d{1,2})\b/g,(m,a,b)=>sideName(a,home,away)+' '+(+b));}
function fmtClock(sec){sec=Math.max(0,+sec||0);return Math.floor(sec/60)+':'+String(sec%60).padStart(2,'0');}
function setScore(el,mine,other,statusText){
  el.querySelector('.score').innerHTML=mine+'<span class="dash">-</span>'+other;
  el.querySelector('.status').textContent=statusText;
  document.querySelectorAll('tr[data-game="'+el.dataset.game+'"] td.res').forEach(td=>{td.textContent=mine+'-'+other+', '+statusText;td.parentElement.classList.add('live');});
}
function showSituation(el,s){
  const box=el.querySelector('.situation');if(!box)return;
  if(!s){box.classList.remove('on');box.textContent='';return;}
  const parts=[];
  if(s.half)parts.push('<span class="half">'+escHtml(s.half)+' gets the ball to start the second half</span>');
  if(s.poss&&!s.half){const me=el.querySelector('.who').firstChild.textContent.trim().toLowerCase(),who=s.poss.toLowerCase();const mine=me.startsWith(who)||who.startsWith(me);parts.push('<span class="poss'+(mine?' mine':'')+'">'+escHtml(s.poss)+' ball</span>');}
  const dd=s.half?'':[s.dd,s.spot].filter(Boolean).join(' at ');
  if(dd)parts.push('<span class="dd">'+escHtml(dd)+'</span>');
  let h=parts.length?'<div>'+parts.join(' · ')+'</div>':'';
  if(s.last)h+='<div class="last">Last play: '+escHtml(s.last)+'</div>';
  if(!h){box.classList.remove('on');box.textContent='';return;}
  box.innerHTML=h;box.classList.add('on');
}
function espnSituation(comp,mine,other){
  const s=comp.situation||{};
  if(!s.downDistanceText&&!s.lastPlay)return null;
  const poss=s.possession===mine.team.id?mine:s.possession===other.team.id?other:null;
  return {poss:poss?poss.team.shortDisplayName:null,dd:s.shortDownDistanceText||(s.downDistanceText||'').split(' at ')[0],spot:s.possessionText||'',last:s.lastPlay&&s.lastPlay.text||''};
}
// Who gets the ball after halftime: the team that kicked off to start the game. Looked up once per game.
const openers=new Map();
function isHalftime(period,clock){return period===2&&/^0?0:00$/.test(clock);}
function opener(key,load){if(!openers.has(key))openers.set(key,load().catch(()=>null));return openers.get(key);}
// ESPN: the game summary lists every drive; the first kickoff's start.team is the kicking team.
function espnOpener(eventId){return opener('espn'+eventId,async()=>{
  const r=await fetch('https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event='+eventId,{cache:'no-store'});
  const j=await r.json();const drives=((j.drives||{}).previous||[]);
  for(const d of drives)for(const p of d.plays||[]){if(/kickoff/i.test((p.type||{}).text||'')&&p.start&&p.start.team)return String(p.start.team.id);}
  return null;});}
// Sidearm: game.json?detail=full carries the whole play list, oldest first; the first kickoff names the kicking side.
function sidearmOpener(url){return opener(url,async()=>{
  const r=await fetch(url+'?detail=full',{cache:'no-store'});const j=await r.json();
  const ko=(j.Plays||[]).find(p=>p.Type==='Kickoff');return ko?ko.Team:null;});}
// PrestoSports: the first kickoff play in the first quarter; hasball is the kicking team's id.
function prestoOpener(x){const q=x.querySelector('qtr[number="1"]');const ko=q&&q.querySelector('play[type="K"]');return ko?ko.getAttribute('hasball'):null;}
// The school feeds. Sidearm: sidearmstats.com/<client>/football/game.json. PrestoSports: data.prestolivestats.com/xml/<site>/events/<event>.xml.
async function feedState(el){
  const url=el.dataset.feed,type=el.dataset.feedType;if(!url)return null;
  const r=await fetch(url,{cache:'no-store'});if(!r.ok)return null;
  const day=mdy(el.dataset.date);
  if(type==='sidearm'){
    const g=(await r.json()).Game;
    if(!g||!g.HasStarted||g.Date!==day)return null;
    const last=(g.LastPlays||[])[0];
    let side=last?last.Team:null;
    // The feed names the team that ran the last play; a punt, kickoff, or turnover hands the ball over.
    if(last&&(last.Turnover||/punt|kickoff/i.test((last.Type||'')+' '+(last.Narrative||''))))side=side==='HomeTeam'?'VisitingTeam':'HomeTeam';
    const m=/^(\d+)(?:st|nd|rd|th) and (\d+|goal) on the ([A-Za-z]+)(\d+)/i.exec(g.Context||'');
    const H={id:g.HomeTeam.Id,name:g.HomeTeam.Name},V={id:g.VisitingTeam.Id,name:g.VisitingTeam.Name};
    const period=+g.Period||0,clock=fmtClock(g.ClockSeconds);
    const kicked=isHalftime(period,clock)?await sidearmOpener(url):null;
    return {complete:!!g.IsComplete,home:+g.HomeTeam.Score||0,away:+g.VisitingTeam.Score||0,period,clock,half:kicked==='HomeTeam'?H.name:kicked==='VisitingTeam'?V.name:null,
      poss:side==='HomeTeam'?H.name:side==='VisitingTeam'?V.name:null,
      dd:m?ordinal(+m[1])+' & '+(/goal/i.test(m[2])?'Goal':m[2]):fixSpots(g.Context||'',H,V),spot:m?sideName(m[3],H,V)+' '+(+m[4]):'',last:last?fixSpots(fixNames(last.Narrative),H,V):''};
  }
  if(type==='presto'){
    const x=new DOMParser().parseFromString(await r.text(),'application/xml');
    const venue=x.querySelector('venue'),st=x.querySelector('status'),dt=x.querySelector('downtogo');
    if(!venue||!st||venue.getAttribute('date')!==day||!x.querySelector('play'))return null;
    const teams={};x.querySelectorAll('team').forEach(t=>{const ls=t.querySelector('linescore');teams[t.getAttribute('vh')]={name:t.getAttribute('name'),id:t.getAttribute('id'),score:+(ls&&ls.getAttribute('score'))||0};});
    const hb=dt?dt.getAttribute('hasball'):null;
    const spotRaw=dt?dt.getAttribute('spot')||'':'';const sm=/^([A-Za-z]+)(\d+)$/.exec(spotRaw);
    const H={id:teams.H&&teams.H.id,name:teams.H?teams.H.name:'Home'},V={id:teams.V&&teams.V.id,name:teams.V?teams.V.name:'Visitor'};
    const down=dt?+dt.getAttribute('down')||0:0,togo=dt?dt.getAttribute('togo'):'';
    const period=+st.getAttribute('period')||0,clock=(dt&&dt.getAttribute('clock'))||st.getAttribute('clock')||'';
    const kicked=isHalftime(period,clock)?prestoOpener(x):null;
    const kicker=kicked?Object.values(teams).find(t=>t.id===kicked):null;
    return {complete:st.getAttribute('complete')==='Y',home:teams.H?teams.H.score:0,away:teams.V?teams.V.score:0,period,clock,half:kicker?kicker.name:null,
      poss:hb&&teams[hb]?teams[hb].name:null,dd:down?ordinal(down)+' & '+(togo==='0'?'Goal':togo):'',spot:sm?sideName(sm[1],H,V)+' '+(+sm[2]):spotRaw,
      last:fixSpots(fixNames((dt&&dt.getAttribute('lastplay')||'').replace(/,?\s*clock \d+:\d+\.?$/,'')),H,V)};
  }
  return null;
}
async function applyFeed(el){
  let f=null;try{f=await feedState(el);}catch(e){}
  if(!f||f.complete)return false;
  const home=el.dataset.home==='1';
  const status=isHalftime(f.period,f.clock)?'Halftime':f.clock+' - '+ordinal(f.period);
  setScore(el,home?f.home:f.away,home?f.away:f.home,status);
  el.classList.add('live');el.classList.remove('pre');
  showSituation(el,f);
  return true;
}
async function refresh(){
  if(!cards.length)return;
  const keys=new Set();
  const now=Date.now();
  cards.forEach(c=>{if(inWindow(c,now))keys.add(c.dataset.group+'|'+etDate(c.dataset.date));});
  if(!keys.size){document.body.classList.remove('has-live');return;}
  let anyLive=false;
  const shown=new Set();
  const halfJobs=[];
  for(const key of keys){
    const [group,date]=key.split('|');
    try{
      const r=await fetch(API+'?groups='+group+'&dates='+date+'&limit=400',{cache:'no-store'});
      const j=await r.json();
      (j.events||[]).forEach(ev=>{
        const el=document.querySelector('.game[data-game="'+ev.id+'"]');
        if(!el)return;
        const comp=ev.competitions[0];const st=comp.status;const state=st.type.state;
        const teamName=el.querySelector('.who').firstChild.textContent.trim();
        const mine=comp.competitors.find(c=>c.team.location===teamName||c.team.shortDisplayName===teamName||c.team.displayName.startsWith(teamName))||comp.competitors[0];
        const other=comp.competitors.find(c=>c!==mine);
        const score=el.querySelector('.score'),status=el.querySelector('.status');
        if(state==='in'||state==='post'){
          score.innerHTML=(mine.score||0)+'<span class="dash">-</span>'+(other.score||0);
          const win=state==='post'?(+mine.score>+other.score?'W':+mine.score<+other.score?'L':'T'):'';
          status.textContent=state==='post'?('Final · '+win):st.type.shortDetail;
        }
        el.classList.toggle('live',state==='in');el.classList.toggle('final',state==='post');el.classList.toggle('pre',state==='pre');
        if(state==='in')anyLive=true;
        if(state==='in'&&st.type.name==='STATUS_HALFTIME'){
          shown.add(el);
          halfJobs.push(espnOpener(ev.id).then(id=>{const t=id===mine.team.id?mine:id===other.team.id?other:null;showSituation(el,{half:t?t.team.shortDisplayName:null,last:comp.situation&&comp.situation.lastPlay&&comp.situation.lastPlay.text||''});}));
        }else{
          const sit=state==='in'?espnSituation(comp,mine,other):null;
          if(sit){showSituation(el,sit);shown.add(el);}
        }
        document.querySelectorAll('tr[data-game="'+ev.id+'"] td.res').forEach(td=>{if(state!=='pre'){td.textContent=(state==='post'?(+mine.score>+other.score?'W ':+mine.score<+other.score?'L ':'T ')+mine.score+'-'+other.score:(mine.score||0)+'-'+(other.score||0)+', '+st.type.shortDetail);td.parentElement.classList.toggle('live',state==='in');}});
      });
    }catch(e){}
  }
  await Promise.all(halfJobs);
  // The stat crew's feed fills in what ESPN leaves out and is usually a play or two ahead of it.
  const pending=cards.filter(c=>c.dataset.feed&&!c.classList.contains('final')&&!shown.has(c)&&inWindow(c,now));
  await Promise.all(pending.map(async c=>{if(await applyFeed(c)){anyLive=true;shown.add(c);}}));
  cards.forEach(c=>{if(!shown.has(c))showSituation(c,null);});
  document.body.classList.toggle('has-live',anyLive);
  const stamp=document.getElementById('livestamp');
  if(stamp)stamp.textContent='Live scores checked '+new Intl.DateTimeFormat('en-US',{hour:'numeric',minute:'2-digit',timeZoneName:'short',timeZone:zone()}).format(new Date());
}
refresh();
setInterval(()=>{if(windowOpen())refresh();},60000);

// Schedule tabs.
const tabs=[...document.querySelectorAll('.tab')],panes=[...document.querySelectorAll('.pane')];
function show(name){tabs.forEach(t=>t.classList.toggle('active',t.dataset.tab===name));panes.forEach(p=>p.hidden=p.dataset.pane!==name);}
tabs.forEach(t=>t.addEventListener('click',()=>show(t.dataset.tab)));
document.querySelectorAll('.tablink').forEach(a=>a.addEventListener('click',()=>show(a.dataset.tab)));
})();
// Sortable tables: click a header to sort by that column; click again to reverse.
(function(){
function cellKey(td){if(!td)return '';const t=td.querySelector('time[datetime]');const raw=td.dataset.sort!==undefined?td.dataset.sort:t?t.getAttribute('datetime'):td.textContent.trim();const n=parseFloat(String(raw).replace(/[,%#$]/g,''));return isNaN(n)||!/^[-+#$]?[\d.,]+%?$/.test(String(raw).replace(/\s/g,''))?String(raw).toLowerCase():n;}
document.querySelectorAll('table').forEach(t=>{
  const head=t.tHead,body=t.tBodies[0];if(!head||!body||body.rows.length<2)return;
  const ths=[...head.rows[head.rows.length-1].cells];
  ths.forEach((th,i)=>{th.setAttribute('aria-sort','none');th.setAttribute('role','button');th.tabIndex=0;
    const go=()=>{const dir=th.getAttribute('aria-sort')==='ascending'?'descending':'ascending';ths.forEach(h=>h.setAttribute('aria-sort','none'));th.setAttribute('aria-sort',dir);
      const rows=[...body.rows];rows.sort((a,b)=>{const x=cellKey(a.cells[i]),y=cellKey(b.cells[i]);const r=typeof x==='number'&&typeof y==='number'?x-y:typeof x==='number'?-1:typeof y==='number'?1:String(x).localeCompare(String(y));return dir==='ascending'?r:-r;});
      rows.forEach(r=>body.appendChild(r));};
    th.addEventListener('click',go);th.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();go();}});});
});
})();
"""


def main():
    built = datetime.now(CENTRAL).strftime("%Y-%m-%d %-I:%M %p")
    fetched = datetime.fromisoformat(SEASON["fetched_at"]).strftime("%Y-%m-%d %-I:%M %p")
    polls = SEASON.get("polls", {})
    ap_week = polls.get("AP Poll", {}).get("week")
    d3 = SEASON.get("d3football", {})
    massey_through = MASSEY.get("through", "")
    hansen_fetched = SEASON.get("hansen", {}).get("fetched", "")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="darkreader-lock">
<meta name="theme-color" content="#f4f3ef" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#15181d" media="(prefers-color-scheme: dark)">
<title>Alma Mater Saturday</title>
<meta name="description" content="Washington, Indiana, Calvin, Hope, and Wheaton (IL) football on one page: records, rankings, Massey and Hansen ratings, kickoff times and TV, top players, and live scores.">
<link rel="icon" href="assets/hope.png">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=Barlow:wght@400;600;700&display=swap" rel="stylesheet">
{GOATCOUNTER}
<style>:root{{--sn-max:1080px;--sn-pad:16px}}{NAV_CSS}{CSS}</style></head><body>
{site_nav("index")}
<main>
<div class="top"><div><h1>Alma Mater Saturday</h1>
<p class="sub">Three brothers went to five schools. Chris went to Calvin. Scott went to Hope and Washington. Matt went to Wheaton and Indiana. This page follows all five football teams: records, rankings, ratings, kickoff times, where to watch, top players, and live scores on game days.</p>
<span class="livepill"><i></i>Games in progress</span></div><div class="controls"><div class="ctl"><span class="seglabel" id="lbl-times">Times</span><div class="seg" role="group" aria-labelledby="lbl-times"><button type="button" class="tz" data-tz="America/New_York">Eastern</button><button type="button" class="tz" data-tz="America/Chicago">Central</button><button type="button" class="tz" data-tz="local">Device</button></div></div><div class="ctl"><span class="seglabel" id="lbl-theme">Theme</span><div class="seg" role="group" aria-labelledby="lbl-theme"><button type="button" class="th" data-theme="light">Light</button><button type="button" class="th" data-theme="dark">Dark</button></div></div></div></div>

<h2 id="week">This week</h2>
<p class="small"><span id="tznote">Kickoff times are in your device's time zone.</span> Use the Eastern, Central, and Device buttons at the top to switch.</p>
<p class="small">Scores refresh every minute while a game is in progress. During a game, each card shows who has the ball, the down and distance, and the last play. At halftime it shows which team gets the ball to start the second half.</p>
<p class="small">ESPN supplies that for Washington and Indiana. For the Division III games it comes from the home team's live stats feed, so it appears only when the home team publishes one. <span id="livestamp"></span></p>
{this_week()}

<h2 id="teams">The five</h2>
<div class="teams">
{"".join(team_card(s) for s in ORDERED)}
</div>

<h2 id="ratings">Rankings and ratings</h2>
<p class="small">Sorted by Massey rank across all divisions. Polls: AP and Coaches for the Division I teams{f" (week {ap_week})" if ap_week else ""}, D3football.com Top 25 for the Division III teams{f" ({d3.get('label')}, through {d3.get('through')})" if d3.get("label") else ""}. Massey appears twice for each team: rank inside its own division, and rank across all {MASSEY["division_sizes"].get("all")} college teams Massey rates. Massey's ratings run through games of {esc(massey_through)}.</p>
{ratings_table()}

<h3 class="spaced" id="hansen"><a href="https://hansenratings.com/" target="_blank" rel="noopener">Hansen Ratings</a> (Division III) <a class="sitelink" href="https://hansenratings.com/" target="_blank" rel="noopener">hansenratings.com &rarr;</a></h3>
<p class="small">Ratings, projections, and simulation results come from <a href="https://hansenratings.com/" target="_blank" rel="noopener">hansenratings.com</a>, which covers Division III only. The table lists predictive rank and rating, adjusted offense and defense, Elo, résumé rank, and schedule strength. It also lists the season simulation's projected record, NPI, and playoff odds. Pool A is the conference automatic bid and Pool C is the at-large bid. Rows are sorted by predictive rank.</p>
{hansen_table()}

<h2 id="margins">Point margin through the season</h2>
<p class="small">Each line is points for minus points against, added up game by game.</p>
{margin_chart()}

<h2 id="watch">Where to watch</h2>
<p class="small">Every network and stream that appears on one of the five schedules this season, with what you need to watch it. Subscription prices are the published 2026-27 prices and can change.</p>
{platforms_section()}

<h2 id="players">Top players</h2>
<p class="small">Season leaders in passing, rushing, receiving, tackles, sacks, and interceptions. Division I numbers come from ESPN. Division III numbers come from each school's official statistics page.</p>
{players_section()}

<h2 id="schedules">Schedules and results</h2>
<p class="small">Opponent ranks come from the AP poll for Division I games and the D3football.com Top 25 for Division III games.</p>
{schedules()}

<section class="more">
<h2>More Division III numbers</h2>
<p>Three of the five schools play Division III. The person behind this page also runs <a href="https://thed3statlab.com/" target="_blank" rel="noopener">The D3 Stat Lab</a>. It publishes NPI rankings, season simulations with tournament odds, composite ratings, and conference rankings for Division III women's basketball.</p>
</section>
<footer>Built {esc(built)} Central. Schedules, scores, records, TV listings, and Division I player statistics from <a href="https://www.espn.com/college-football/" target="_blank" rel="noopener">ESPN</a>, fetched {esc(fetched)} Central. Division III player statistics from the schools' official statistics pages. Polls from ESPN (AP, AFCA Coaches, AFCA Division III) and <a href="https://d3football.com/top25/index" target="_blank" rel="noopener">D3football.com</a>. Ratings from <a href="https://masseyratings.com/cf/ratings" target="_blank" rel="noopener">Massey Ratings</a> (through {esc(massey_through)}, updated each week) and <a href="https://hansenratings.com/" target="_blank" rel="noopener">Hansen Ratings</a> (fetched {esc(hansen_fetched[:16].replace("T", " "))}). This page is not affiliated with any of the schools, their conferences, or the NCAA. Logos belong to their schools.</footer>
</main>
<script>{JS}</script>
</body></html>
"""
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(page)
    print(f"wrote {OUT} ({len(page)} bytes)")
    build_montlake()


if __name__ == "__main__":
    main()
