// Run in the browser console on https://d3football.com/top25/index (or the current week page).
// Copies the D3football.com Top 25 as JSON for data/d3football.json.
(() => {
  const flat = document.body.innerText.replace(/\s+/g, " ");
  const title = (flat.match(/D3football\.com Top 25, (\d{4} Week \d+|\d{4} preseason|\d{4} final)/) || [])[1] || null;
  const through = (flat.match(/Through games of ([A-Z][a-z]+\.? \d+, \d{4})/) || [])[1] || null;
  let body = flat.slice(flat.indexOf("Rank School"));
  const end = body.indexOf("The D3football.com Top 25 is voted");
  if (end > 0) body = body.slice(0, end);
  const ranked = {};
  const re = /(\d{1,2}) ([A-Z][^()]*?(?: \([A-Z][a-z.]+\))?)(?: \((\d+)\))? (\d+-\d+(?:-\d+)?) (\d+) (\d+|NR|RV)/g;
  let m;
  while ((m = re.exec(body))) ranked[m[2].trim()] = { rank: +m[1], record: m[4], points: +m[5], prev: m[6] };
  const rv = {};
  const o = body.match(/Others receiving votes: (.*?)\.(?: |$)/);
  if (o) o[1].split(";").forEach(item => { const mm = item.trim().match(/(.+?) (\d+)$/); if (mm) rv[mm[1].trim()] = +mm[2]; });
  const out = { source: location.href, refreshed: new Date().toISOString(), label: title, through, ranked, receiving_votes: rv };
  const json = JSON.stringify(out, null, 1);
  if (navigator.clipboard) navigator.clipboard.writeText(json).catch(() => {});
  console.log(json);
  return out;
})();
