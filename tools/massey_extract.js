// Weekly Massey refresh. Open https://masseyratings.com/cf/ratings in Chrome,
// run this in the console (or through Claude in Chrome), and paste the JSON
// it prints into data/massey.json under "teams", then update "through" and
// "refreshed". Division ranks come from the team's position among its own
// division in this all-division table.
const t = [...document.querySelectorAll('table')].sort((a, b) => b.rows.length - a.rows.length)[0];
const rows = [...t.rows].slice(1).map(r => [...r.cells].map(c => c.innerText.trim().split('\n').map(x => x.trim())));
const parsed = rows.filter(r => r.length >= 12).map(r => ({
  team: r[0][0], division: r[0][1], rec: r[1][0],
  overall_rank: +r[3][0], rating: +r[3][1], pwr_rank: +r[4][0], pwr: +r[4][1],
  off_rank: +r[5][0], off: +r[5][1], def_rank: +r[6][0], def: +r[6][1],
  sos_rank: +r[8][0], sos: +r[8][1], exp_w: +r[10][0], exp_l: +r[11][0],
}));
const count = {}; for (const p of [...parsed].sort((a, b) => a.overall_rank - b.overall_rank)) { count[p.division] = (count[p.division] || 0) + 1; p.div_rank = count[p.division]; }
const pc = {}; for (const p of [...parsed].sort((a, b) => a.pwr_rank - b.pwr_rank)) { pc[p.division] = (pc[p.division] || 0) + 1; p.div_pwr_rank = pc[p.division]; }
const keys = { Washington: 'washington', Indiana: 'indiana', Hope: 'hope', Calvin: 'calvin', 'Wheaton IL': 'wheaton' };
const out = {}; for (const p of parsed) if (keys[p.team]) { const { team, rec, ...rest } = p; out[keys[team]] = rest; }
({ through: (document.body.innerText.match(/Using games thru ([^\n]+)/) || [])[1], division_sizes: { ...count, all: parsed.length }, teams: out });
