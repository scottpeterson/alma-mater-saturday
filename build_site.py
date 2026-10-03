#!/usr/bin/env python3
"""Render docs/index.html from schools.json, data/season.json, and data/massey.json."""
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
EASTERN = ZoneInfo("America/New_York")
CENTRAL = ZoneInfo("America/Chicago")
BY_SLUG = {s["slug"]: s for s in SCHOOLS}
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

    def badge(label, rank, rv):
        if rank:
            badges.append(f'<span class="badge"><b>#{rank}</b> {esc(label)}</span>')
        elif rv:
            badges.append(f'<span class="badge rv">RV {esc(label)}</span>')
        else:
            badges.append(f'<span class="badge nr">NR {esc(label)}</span>')

    if school["division"] == "FBS":
        for key, label in (("AP Poll", "AP"), ("AFCA Coaches Poll", "Coaches")):
            p = polls.get(key, {})
            badge(label, p.get("ranks", {}).get(slug), p.get("receiving_votes", {}).get(slug))
        cfp = next((p for k, p in polls.items() if "CFP" in k or "Playoff" in (p.get("name") or "")), None)
        if cfp:
            badge("CFP", cfp.get("ranks", {}).get(slug), None)
    else:
        d3 = SEASON.get("d3football", {})
        r = d3.get("ranks", {}).get(slug)
        badge("D3football.com", r["rank"] if r else None, d3.get("receiving_votes", {}).get(slug))
        p = polls.get("AFCA Div III", {})
        badge("AFCA D3", p.get("ranks", {}).get(slug), p.get("receiving_votes", {}).get(slug))
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
    return (f'<a class="badge hansen" href="https://hansenratings.com/ratings/predictive/2026/" title="Hansen Ratings predictive rank">'
            f'<b>#{pred["Rank"]}</b> Hansen</a>')


# ---------------------------------------------------------------- sections

def featured_games():
    """Games to show in This week: live, upcoming within 8 days, or final within 36 hours."""
    rows = []
    for school in SCHOOLS:
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
    # one upcoming game per team at most, plus any live or recent final
    seen = set()
    out = []
    for school, g in sorted(rows, key=lambda r: r[1]["date"]):
        key = (school["slug"], g["state"] == "pre")
        if g["state"] == "pre" and key in seen:
            continue
        seen.add(key)
        out.append((school, g))
    return out


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
    return f'''<article class="game {status_class}" data-game="{esc(g["id"])}" data-group="{esc(g["group"])}" data-date="{esc(g["date"])}" style="--team:var(--c-{school["slug"]})">
<header><img src="{esc(school["logo"])}" alt=""><div><div class="who">{esc(school["name"])} <span class="muted">{esc(school["mascot"])}</span></div><div class="what">{"vs" if g["home"] or g.get("neutral") else "at"} {rank}{esc(opp["name"])}</div></div>{opp_logo}</header>
<div class="body">
<div class="scoreline"><span class="score">{score}</span><span class="status">{status}</span></div>
<dl>
<dt>Kickoff</dt><dd>{time_tag(g)} {countdown}</dd>
<dt>Watch</dt><dd>{tv_chips(g)}</dd>
<dt>Where</dt><dd>{esc(where)}{" · " + esc(venue) if venue else ""}</dd>
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
            src = f'<a href="{href}">{src}</a>'
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
        cards.append(f'<article class="platform"><h3><a href="{esc(p["url"])}">{esc(p["name"])}</a>{also}</h3><div class="chips">{tag}<span class="chip">{esc(p["kind"])}</span>{sched}</div><p><b>Teams:</b> {esc(p["teams"])}</p><p>{esc(p["access"])}</p>{note}</article>')
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


def team_card(school):
    team = SEASON["teams"].get(school["slug"])
    if not team:
        return f'<article class="team"><header style="background:{esc(school["color"])}"><img src="{esc(school["logo"])}" alt=""><div class="who">{esc(school["name"])}</div></header><div class="body"><p class="muted">Data unavailable.</p></div></article>'
    avg = team["diff"] / team["played"] if team["played"] else 0
    record = team["record"] or f'{team["wins"]}-{team["losses"]}' + (f'-{team["ties"]}' if team["ties"] else "")
    return f'''<article class="team" id="team-{school["slug"]}" style="--team:var(--c-{school["slug"]})">
<header style="background:{esc(school["color"])};color:{esc(school["text"])}"><img src="{esc(school["logo"])}" alt="{esc(school["name"])} logo"><div><div class="who">{esc(school["name"])} {esc(school["mascot"])}</div><div class="what">{esc(school["division_label"])} · {esc(school["conference"])} · {esc(school["city"])}</div></div></header>
<div class="body">
<div class="record"><span class="big">{esc(record)}</span><span class="standing">{esc(team.get("standing") or "")}</span></div>
<div class="badges">{poll_badges(school["slug"])}{massey_line(school["slug"])}{hansen_badge(school["slug"])}</div>
<dl>
<dt>Points</dt><dd>{team["pf"]} for, {team["pa"]} against</dd>
<dt>Margin</dt><dd><b class="{ "pos" if team["diff"] > 0 else "neg" if team["diff"] < 0 else ""}">{signed(team["diff"])}</b> total, {signed(round(avg, 1))} per game</dd>
{last_and_next(team)}
</dl>
<p class="meta"><a href="{esc(school["schedule_url"])}">Official schedule</a> · <a href="#sched-{school["slug"]}" class="tablink" data-tab="{school["slug"]}">Full schedule below</a></p>
</div></article>'''


def ratings_table():
    polls = SEASON.get("polls", {})
    d3 = SEASON.get("d3football", {})
    hansen = SEASON.get("hansen", {}).get("teams", {})
    head = ("<tr><th>Team</th><th>Record</th><th>Poll</th><th>Massey rating</th><th>Massey rank in division</th><th>Massey rank all divisions</th>"
            "<th>Massey power</th><th>Massey offense</th><th>Massey defense</th><th>Massey SOS</th><th>Massey expected W-L</th><th>Points for</th><th>Points against</th><th>Margin</th></tr>")
    rows = []
    ordered = sorted(SCHOOLS, key=lambda x: MASSEY["teams"].get(x["slug"], {}).get("overall_rank", 9999))
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
    for s in SCHOOLS:
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
    tabs = ['<button class="tab active" data-tab="all">All five</button>'] + [f'<button class="tab" data-tab="{s["slug"]}" style="--team:var(--c-{s["slug"]})">{esc(s["name"])}</button>' for s in SCHOOLS]
    panes = []
    all_rows = []
    for s in SCHOOLS:
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


# ---------------------------------------------------------------- page

CSS = r"""
:root{--bg:#f4f3ef;--surface:#ffffff;--surface2:#ecebe5;--line:#d8d5cb;--ink:#1e2229;--muted:#616873;--faint:#8c939d;--link:#1f4e79;--pos:#2e8b57;--neg:#c0504d;--live:#d6323c;--chip:#e9e7df;--on-team:#ffffff;
--c-washington:#4b2e83;--c-indiana:#990000;--c-calvin:#8c2131;--c-hope:#c45114;--c-wheaton:#00407e}
:root[data-theme="dark"]{--bg:#15181d;--surface:#1d2128;--surface2:#252a32;--line:#363c46;--ink:#e7e9ec;--muted:#a7adb7;--faint:#7d848f;--link:#8ab8e6;--pos:#5fc08a;--neg:#e2807c;--chip:#2e343d;--on-team:#15181d;
--c-washington:#b7a0e6;--c-indiana:#ff8a8a;--c-calvin:#f0a3ad;--c-hope:#ffa26b;--c-wheaton:#8fbdf2}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#15181d;--surface:#1d2128;--surface2:#252a32;--line:#363c46;--ink:#e7e9ec;--muted:#a7adb7;--faint:#7d848f;--link:#8ab8e6;--pos:#5fc08a;--neg:#e2807c;--chip:#2e343d;--on-team:#15181d;
--c-washington:#b7a0e6;--c-indiana:#ff8a8a;--c-calvin:#f0a3ad;--c-hope:#ffa26b;--c-wheaton:#8fbdf2}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 "Barlow",-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
a{color:var(--link)}img{max-width:100%}
main{max-width:1080px;margin:0 auto;padding:20px 16px 64px}
h1,h2,h3,.big,.score,.tab{font-family:"Barlow Condensed","Avenir Next Condensed","Arial Narrow",sans-serif}
h1{font-size:2.6rem;line-height:1;margin:.1em 0 .1em;letter-spacing:.01em}h2{font-size:1.6rem;margin:2.2em 0 .5em;padding-bottom:.2em;border-bottom:1px solid var(--line)}h3{font-size:1.25rem;margin:1.2em 0 .5em;display:flex;align-items:center;gap:8px}h3 img{height:26px;width:26px;object-fit:contain}
.top{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap}.sub{color:var(--muted);margin:0 0 .4em;max-width:760px}
.muted{color:var(--muted)}.small{font-size:.9rem;color:var(--muted)}.pos{color:var(--pos)}.neg{color:var(--neg)}
button{font:inherit;cursor:pointer}
.toggle{border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:999px;padding:6px 12px;font-size:.9rem}
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
"""

JS = r"""
(function(){
const root=document.documentElement;
const saved=(()=>{try{return localStorage.getItem('ams-theme')}catch(e){return null}})();
if(saved==='dark'||saved==='light')root.setAttribute('data-theme',saved);
const btn=document.getElementById('theme');
function label(){const dark=root.getAttribute('data-theme')==='dark'||(!root.getAttribute('data-theme')&&matchMedia('(prefers-color-scheme:dark)').matches);btn.textContent=dark?'Light mode':'Dark mode';}
btn.addEventListener('click',()=>{const dark=root.getAttribute('data-theme')==='dark'||(!root.getAttribute('data-theme')&&matchMedia('(prefers-color-scheme:dark)').matches);const next=dark?'light':'dark';root.setAttribute('data-theme',next);try{localStorage.setItem('ams-theme',next)}catch(e){}label();});
label();

// Show kickoff times in the viewer's time zone.
const tz=Intl.DateTimeFormat().resolvedOptions().timeZone;
if(tz&&tz!=='America/New_York'){
  document.querySelectorAll('time[datetime]').forEach(t=>{
    if(t.dataset.tbd)return;
    const d=new Date(t.getAttribute('datetime'));
    const opts=t.dataset.fmt==='full'?{weekday:'short',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short'}:{hour:'numeric',minute:'2-digit',timeZoneName:'short'};
    t.textContent=new Intl.DateTimeFormat(undefined,opts).format(d).replace(',',',');
  });
}

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

// Live scores straight from ESPN while games are on.
const API='https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard';
const cards=[...document.querySelectorAll('.game[data-game]')];
function etDate(iso){const d=new Date(iso);const p=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(d);const g=k=>p.find(x=>x.type===k).value;return g('year')+g('month')+g('day');}
function windowOpen(){
  const now=Date.now();
  return cards.some(c=>{const t=new Date(c.dataset.date).getTime();return c.classList.contains('live')||(t-now<30*60000&&now-t<5*3600000);});
}
async function refresh(){
  if(!cards.length)return;
  const keys=new Set();
  const now=Date.now();
  cards.forEach(c=>{const t=new Date(c.dataset.date).getTime();if(c.classList.contains('live')||(t-now<30*60000&&now-t<5*3600000))keys.add(c.dataset.group+'|'+etDate(c.dataset.date));});
  if(!keys.size){document.body.classList.remove('has-live');return;}
  let anyLive=false;
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
        document.querySelectorAll('tr[data-game="'+ev.id+'"] td.res').forEach(td=>{if(state!=='pre'){td.textContent=(state==='post'?(+mine.score>+other.score?'W ':+mine.score<+other.score?'L ':'T ')+mine.score+'-'+other.score:(mine.score||0)+'-'+(other.score||0)+', '+st.type.shortDetail);td.parentElement.classList.toggle('live',state==='in');}});
      });
    }catch(e){}
  }
  document.body.classList.toggle('has-live',anyLive);
  const stamp=document.getElementById('livestamp');
  if(stamp)stamp.textContent='Live scores checked '+new Date().toLocaleTimeString([], {hour:'numeric',minute:'2-digit'});
}
refresh();
setInterval(()=>{if(windowOpen())refresh();},60000);

// Schedule tabs.
const tabs=[...document.querySelectorAll('.tab')],panes=[...document.querySelectorAll('.pane')];
function show(name){tabs.forEach(t=>t.classList.toggle('active',t.dataset.tab===name));panes.forEach(p=>p.hidden=p.dataset.pane!==name);}
tabs.forEach(t=>t.addEventListener('click',()=>show(t.dataset.tab)));
document.querySelectorAll('.tablink').forEach(a=>a.addEventListener('click',()=>show(a.dataset.tab)));
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
<title>Alma Mater Saturday</title>
<meta name="description" content="Washington, Indiana, Calvin, Hope, and Wheaton (IL) football on one page: records, rankings, Massey and Hansen ratings, kickoff times and TV, top players, and live scores.">
<link rel="icon" href="assets/hope.png">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=Barlow:wght@400;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><main>
<div class="top"><div><h1>Alma Mater Saturday</h1>
<p class="sub">Five schools, three brothers, one page. Washington, Indiana, Calvin, Hope, and Wheaton (IL) football: records, rankings, ratings, kickoff times and where to watch, top players, and live scores on game days.</p>
<span class="livepill"><i></i>Games in progress</span></div><button id="theme" class="toggle" type="button">Dark mode</button></div>

<h2 id="week">This week</h2>
<p class="small">Kickoff times show in your time zone. Scores update every minute while a game is on. <span id="livestamp"></span></p>
{this_week()}

<h2 id="teams">The five</h2>
<div class="teams">
{"".join(team_card(s) for s in SCHOOLS)}
</div>

<h2 id="ratings">Rankings and ratings</h2>
<p class="small">Sorted by Massey rank across all divisions. Polls: AP and Coaches for the Division I teams{f" (week {ap_week})" if ap_week else ""}, D3football.com Top 25 for the Division III teams{f" ({d3.get('label')}, through {d3.get('through')})" if d3.get("label") else ""}. Massey ratings are shown two ways: rank inside the team's own division and rank across all {MASSEY["division_sizes"].get("all")} college teams Massey rates, through games of {esc(massey_through)}.</p>
{ratings_table()}

<h3 style="margin-top:1.6em" id="hansen"><a href="https://hansenratings.com/">Hansen Ratings</a> (Division III) <a class="sitelink" href="https://hansenratings.com/">hansenratings.com &rarr;</a></h3>
<p class="small">Ratings, projections, and simulation results from <a href="https://hansenratings.com/">hansenratings.com</a>, which covers Division III only. Predictive rank and rating, adjusted offense and defense, Elo, résumé rank, schedule strength, and the season simulation's projected record, NPI, and playoff odds. Pool A is the automatic bid, Pool C the at-large bid. Sorted by predictive rank.</p>
{hansen_table()}

<h2 id="margins">Point margin through the season</h2>
<p class="small">Cumulative points for minus points against after each game played.</p>
{margin_chart()}

<h2 id="watch">Where to watch</h2>
<p class="small">Every network or stream that appears on one of the five schedules this season, what it is, and whether it costs anything. Subscription prices are the ones published for 2026-27 and can change.</p>
{platforms_section()}

<h2 id="players">Top players</h2>
<p class="small">Season leaders in passing, rushing, receiving, tackles, sacks, and interceptions. Division I numbers come from ESPN; Division III numbers come from each school's official statistics page.</p>
{players_section()}

<h2 id="schedules">Schedules and results</h2>
{schedules()}

<section class="more">
<h2>More Division III numbers</h2>
<p>Three of these five schools play Division III, where the author also runs <a href="https://thed3statlab.com/">The D3 Stat Lab</a>: NPI rankings, season simulations with tournament odds, composite ratings, and conference rankings for Division III women's basketball.</p>
</section>
<footer>Built {esc(built)} Central. Schedules, scores, records, TV listings, and Division I player statistics from <a href="https://www.espn.com/college-football/">ESPN</a>, fetched {esc(fetched)} Central. Division III player statistics from the schools' official statistics pages. Polls from ESPN (AP, AFCA Coaches, AFCA Division III) and <a href="https://d3football.com/top25/index">D3football.com</a>. Ratings from <a href="https://masseyratings.com/cf/ratings">Massey Ratings</a> (through {esc(massey_through)}, refreshed by hand each week) and <a href="https://hansenratings.com/">Hansen Ratings</a> (fetched {esc(hansen_fetched[:16].replace("T", " "))}). Not affiliated with any of the schools, their conferences, or the NCAA. Logos belong to their schools.</footer>
</main>
<script>{JS}</script>
</body></html>
"""
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(page)
    print(f"wrote {OUT} ({len(page)} bytes)")


if __name__ == "__main__":
    main()
