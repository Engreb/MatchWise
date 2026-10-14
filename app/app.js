/* Matchwise app: renders predictions produced by the Python engine (engine/). All
   probabilities come from app/data/*.json; this file only formats and displays them. */
'use strict';

const TZ = 'Europe/London';
const state = { league: 'all', q: '', selected: null, histLeague: 'all', view: 'blend', predict: { league: 'epl', home: '', away: '' } };
const cache = {};

/* ---------- data ---------- */
async function getJSON(name) {
  if (!cache[name]) {
    cache[name] = fetch(`data/${name}.json`, { cache: 'no-cache' }).then(r => {
      if (!r.ok) throw new Error(`${name}: ${r.status}`);
      return r.json();
    }).catch(e => { delete cache[name]; throw e; });
  }
  return cache[name];
}
const league = key => getJSON(`league-${key}`);
function pair(L, home, away) {
  const v = L.pairs[`${home}|${away}`];
  return v ? parsePayload(v) : null;
}
function parsePayload(v) {
  const [lam, mu, H, D, A, o05, o15, o25, o35, o45, btts, ...grid] = v;
  const n = Math.round(Math.sqrt(grid.length));
  const cells = [];
  for (let x = 0; x < n; x++) for (let y = 0; y < n; y++) cells.push([x, y, grid[x * n + y]]);
  const top = cells.slice().sort((a, b) => b[2] - a[2]);
  return { lam, mu, H, D, A, over: { 0.5: o05, 1.5: o15, 2.5: o25, 3.5: o35, 4.5: o45 }, btts, grid, n, top };
}

/* ---------- formatting ---------- */
const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pct = (p, d = 0) => (p * 100).toFixed(d) + '%';
const fair = p => p > 0 ? (1 / p).toFixed(2) : '—';
const dt = s => new Date(s.length === 10 ? s + 'T12:00:00Z' : s);
const hasTime = s => s.length > 10;
const fmtTime = s => hasTime(s) ? dt(s).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: TZ }) : 'TBC';
const fmtDay = s => dt(s).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', timeZone: TZ });
const fmtShort = s => dt(s).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', timeZone: TZ });
const fmtDate = s => dt(s).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: TZ });
const topIdx = p => p.indexOf(Math.max(...p));
const ord = n => n + (['th', 'st', 'nd', 'rd'][(n % 100 > 10 && n % 100 < 14) ? 0 : (n % 10 < 4 ? n % 10 : 0)] || 'th');
const matchHref = (lg, h, a) => `#/match/${lg}/${encodeURIComponent(h)}/${encodeURIComponent(a)}`;

/* ---------- icons ---------- */
const svg = (d, extra = '') => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" ${extra}>${d}</svg>`;
const I = {
  fixtures: svg('<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M3 9h18M8 2v4M16 2v4"/>'),
  predict: svg('<circle cx="12" cy="12" r="9"/><path d="M12 7l4 3-1.5 5h-5L8 10z"/>'),
  history: svg('<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/>'),
  accuracy: svg('<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>'),
  chev: svg('<path d="M9 6l6 6-6 6"/>', 'class="chev"'),
  back: svg('<path d="M15 6l-6 6 6 6"/>'),
  search: svg('<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>'),
  info: svg('<circle cx="12" cy="12" r="9"/><path d="M12 8h.01M11 12h1v5h1"/>'),
};
const NAV = [['fixtures', 'Fixtures'], ['predict', 'Predict a match'], ['history', 'This season'], ['accuracy', 'Model accuracy']];
const NAV_SHORT = { fixtures: 'Fixtures', predict: 'Predict', history: 'Season', accuracy: 'Accuracy' };

function statusBadge(meta) {
  return meta.status === 'validated'
    ? `<a href="#/accuracy" class="badge ok"><span class="dot"></span>Tested on past seasons</a>`
    : `<a href="#/accuracy" class="badge warn"><span class="dot"></span>Not yet validated</a>`;
}
const errorBox = e => `<div class="card empty"><h3>Couldn't load predictions</h3><p class="sub">${esc(e.message || e)}. Run <code>python -m matchwise update</code> in the engine folder, then reload.</p><button class="btn" onclick="location.reload()">Reload</button></div>`;

/* ---------- routing ---------- */
async function route() {
  const parts = location.hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent);
  const page = parts[0] || 'fixtures';
  const active = page === 'match' ? (state.from || 'fixtures') : page;
  const nav = short => NAV.map(([k, label]) => `<a href="#/${k}" ${k === active ? 'aria-current="page"' : ''}>${I[k]}<span>${short ? NAV_SHORT[k] : label}</span></a>`).join('');
  document.getElementById('nav').innerHTML = nav(false);
  document.getElementById('tabbar').innerHTML = nav(true);
  const main = document.getElementById('main');
  main.innerHTML = `<div class="content"><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div></div>`;
  try {
    const meta = await getJSON('fixtures');
    renderFreshness(meta);
    let html, title;
    if (page === 'match') { html = await matchPage(meta, parts[1], parts[2], parts[3]); title = `${parts[2]} vs ${parts[3]}`; }
    else if (page === 'predict') { html = await predictPage(meta); title = 'Predict a match'; state.from = 'predict'; }
    else if (page === 'history') { html = await historyPage(meta); title = 'This season'; }
    else if (page === 'accuracy') { html = await accuracyPage(meta); title = 'Model accuracy'; }
    else { html = await fixturesPage(meta); title = 'Fixtures'; state.from = 'fixtures'; }
    main.innerHTML = html;
    document.title = `${title} · Matchwise`;
    bind();
  } catch (e) {
    console.error(e);
    main.innerHTML = `<div class="content">${errorBox(e)}</div>`;
  }
}
window.addEventListener('hashchange', () => { route(); window.scrollTo(0, 0); });

function renderFreshness(meta) {
  const ageDays = (Date.now() - new Date(meta.generated_at)) / 864e5;
  const through = meta.leagues.map(l => l.data_through).sort().pop();
  document.getElementById('freshness').innerHTML = `
    ${ageDays > 8 ? '<span class="badge warn" style="margin-bottom:8px"><span class="dot"></span>Data may be out of date</span>' : ''}
    <div>Updated ${fmtDate(meta.generated_at)}</div><div>Results to ${fmtDate(through)}</div>
    <div style="margin-top:4px">Source: football-data.co.uk</div>`;
}

/* ---------- fixtures ---------- */
function x12(p, idx) {
  return `<div class="x12 num">${['1', 'X', '2'].map((l, k) => `<span class="${k === idx ? 'top' : ''}"><small>${l}</small>${pct(p[k])}</span>`).join('')}</div>`;
}
async function fixturesPage(meta) {
  const leagues = {};
  await Promise.all(meta.leagues.map(async l => { leagues[l.key] = await league(l.key); }));
  const fx = meta.fixtures.map((f, i) => {
    const model = f.assessable ? pair(leagues[f.league], f.home, f.away) : null;
    return { ...f, id: 'f' + i, model, pr: f.blend ? parsePayload(f.blend) : model };
  });
  state.fx = fx; state.leagues = leagues;
  if (!state.selected && fx.length) state.selected = fx[0].id;
  const chips = [['all', 'All leagues'], ...meta.leagues.map(l => [l.key, l.name])]
    .map(([k, l]) => `<button class="chip" data-league="${k}" aria-pressed="${state.league === k}">${esc(l)}</button>`).join('');
  return `<div class="content">
    <div class="page-head"><div><h1>Fixtures</h1><p class="sub">Predictions for the next 10 days. Times shown in UK time. Bookmaker odds appear a few days before each match.</p></div>${statusBadge(meta)}</div>
    ${fx.length ? `<div class="with-panel"><div>
        <div class="toolbar"><div class="chips" role="group" aria-label="Filter by league">${chips}</div>
          <label class="search">${I.search}<input type="search" placeholder="Search teams" aria-label="Search teams" value="${esc(state.q)}" data-search></label></div>
        <div id="fixlist">${fixturesList()}</div>
      </div><aside class="panel" aria-label="Selected match" id="panel">${quickPanel()}</aside></div>`
    : `<div class="card empty">
        <h3>No upcoming fixtures found</h3>
        <p class="sub" style="max-width:520px;margin:6px auto 16px">The fixture schedule couldn't be loaded, or every match has already kicked off. Run the update again to refresh it. You can still predict any match.</p>
        <a class="btn primary" href="#/predict">Predict any match</a>
      </div>`}
  </div>`;
}
function filtered() {
  const q = state.q.trim().toLowerCase();
  return state.fx.filter(f => (state.league === 'all' || f.league === state.league) && (!q || `${f.home} ${f.away}`.toLowerCase().includes(q)));
}
function fixturesList() {
  const list = filtered();
  if (!list.length) return `<div class="card empty"><h3>No fixtures match</h3><p class="sub">Try another league or clear the search.</p><button class="btn" data-reset>Clear filters</button></div>`;
  const days = {};
  list.forEach(f => (days[fmtDay(f.kickoff)] ||= []).push(f));
  return Object.entries(days).map(([day, fs]) => `
    <div class="day-label">${day}</div>
    <div class="list" role="listbox" aria-label="Fixtures on ${day}">
      <div class="list-head" aria-hidden="true"><span>Kick-off</span><span>Match</span><span style="text-align:center">Home · Draw · Away</span><span class="r">Over 2.5</span><span class="r">BTTS</span><span class="r">Likely</span><span></span></div>
      ${fs.map(f => {
        const lgName = state.leagues[f.league].name;
        if (!f.pr) return `<div class="row" aria-disabled="true"><span class="time num">${fmtTime(f.kickoff)}</span><span class="teams"><div>${esc(f.home)}</div><div>${esc(f.away)}</div></span><span class="meta" style="grid-column:span 5">Unable to assess: team not recognised</span></div>`;
        const p = [f.pr.H, f.pr.D, f.pr.A];
        return `<button class="row" role="option" data-fix="${f.id}" aria-selected="${f.id === state.selected}">
          <span class="time num">${fmtTime(f.kickoff)}</span>
          <span class="teams"><div>${esc(f.home)}</div><div>${esc(f.away)}</div><div class="lg">${state.league === 'all' ? esc(lgName) + (f.blend ? ' · ' : '') : ''}${f.blend ? 'Odds-adjusted' : ''}</div></span>
          ${x12(p, topIdx(p))}
          <span class="r num hide-m">${pct(f.pr.over[2.5])}</span>
          <span class="r num hide-m">${pct(f.pr.btts)}</span>
          <span class="r num hide-m">${f.pr.top[0][0]}–${f.pr.top[0][1]}</span>
          <span class="hide-m">${I.chev}</span>
        </button>`;
      }).join('')}
    </div>`).join('');
}
function quickPanel() {
  const f = state.fx.find(x => x.id === state.selected && x.pr) || state.fx.find(x => x.pr);
  if (!f) return '';
  const p = f.pr, probs = [p.H, p.D, p.A], t = topIdx(probs);
  return `<div class="card card-pad">
    <div class="meta">${esc(state.leagues[f.league].name)} · ${fmtShort(f.kickoff)} ${fmtTime(f.kickoff)}</div>
    <h2 style="margin:6px 0 ${f.blend ? 6 : 14}px">${esc(f.home)} <span style="color:var(--text-tertiary);font-weight:400">vs</span> ${esc(f.away)}</h2>
    ${f.blend ? `<p class="meta" style="margin:0 0 12px">Model combined with bookmakers' pre-match odds. Model alone: ${pct(f.model.H)} · ${pct(f.model.D)} · ${pct(f.model.A)}</p>` : ''}
    <div class="pbar" aria-hidden="true">${probs.map((v, k) => `<i class="${k === t ? 'top' : ''}" style="width:${v * 100}%"></i>`).join('')}</div>
    <div style="display:flex;justify-content:space-between;margin:8px 0 16px" class="num">
      <span><b>${pct(p.H)}</b> <span class="meta">home</span></span><span><b>${pct(p.D)}</b> <span class="meta">draw</span></span><span><b>${pct(p.A)}</b> <span class="meta">away</span></span>
    </div>
    <div class="kv"><span>Predicted goals</span><span class="num">${p.lam.toFixed(2)} – ${p.mu.toFixed(2)}</span></div>
    <div class="kv"><span>Over 2.5 goals</span><span class="num">${pct(p.over[2.5])}</span></div>
    <div class="kv"><span>Both teams score</span><span class="num">${pct(p.btts)}</span></div>
    <div class="kv"><span>Most likely score</span><span class="num">${p.top[0][0]}–${p.top[0][1]} (${pct(p.top[0][2])})</span></div>
    ${f.market ? `<div class="kv"><span>Bookmakers (home/draw/away)</span><span class="num">${f.market.map(v => pct(v)).join(' · ')}</span></div>` : ''}
    <a class="btn primary block" style="margin-top:16px" href="${matchHref(f.league, f.home, f.away)}">View full analysis</a>
  </div>`;
}

/* ---------- match ---------- */
function strengthBar(v, lo, hi) {
  const w = Math.max(4, Math.min(100, ((v - lo) / (hi - lo || 1)) * 100));
  return `<div class="track"><i style="width:${w}%"></i></div>`;
}
async function matchPage(meta, lgKey, home, away) {
  const backTo = state.from === 'predict' ? ['#/predict', 'Predict a match'] : ['#/fixtures', 'Fixtures'];
  const back = `<a class="back" href="${backTo[0]}">${I.back}${backTo[1]}</a>`;
  const lgMeta = meta.leagues.find(l => l.key === lgKey);
  if (!lgMeta) return `<div class="content">${back}<div class="card empty"><h3>Unknown league</h3></div></div>`;
  const L = await league(lgKey);
  const modelP = pair(L, home, away);
  const fx0 = meta.fixtures.find(f => f.league === lgKey && f.home === home && f.away === away);
  const canBlend = !!(fx0 && fx0.blend);
  const p = canBlend && state.view === 'blend' ? parsePayload(fx0.blend) : modelP;
  if (!p) return `<div class="content">${back}<div class="card empty"><h3>Unable to assess this match</h3><p class="sub">One of the teams isn't in the current ${esc(L.name)} model.</p></div></div>`;
  const fx = fx0;
  const T = Object.fromEntries(L.teams.map(t => [t.name, t]));
  const th = T[home], ta = T[away], n = L.teams.length;
  const probs = [p.H, p.D, p.A], t = topIdx(probs);
  const outcome = (k, label) => `<div class="outcome ${k === t ? 'top' : ''}"><div class="lbl" title="${esc(label)}">${esc(label)}</div><div class="val num">${pct(probs[k])}</div><div class="meta num">Fair odds ${fair(probs[k])}</div></div>`;
  const mrow = (sel, v) => `<tr><td>${sel}</td><td class="r num"><span class="mini-bar"><i style="width:${v * 100}%"></i></span>${pct(v, 1)}</td><td class="r num">${fair(v)}</td></tr>`;

  const max = p.top[0][2];
  let sg = `<div class="h"></div>` + [...Array(p.n).keys()].map(y => `<div class="h">${y}</div>`).join('');
  for (let x = 0; x < p.n; x++) {
    sg += `<div class="h">${x}</div>`;
    for (let y = 0; y < p.n; y++) {
      const v = p.grid[x * p.n + y], a = (v / max) * 0.85;
      sg += `<div class="c num" style="background:rgba(49,87,225,${a.toFixed(3)});color:${a > .5 ? '#fff' : 'var(--text-primary)'}" title="${esc(home)} ${x}–${y} ${esc(away)}: ${pct(v, 1)}">${(v * 100).toFixed(1)}</div>`;
    }
  }

  const why = [
    `<b>${esc(home)}</b> rate ${ord(th.rank_attack)} for attack and ${ord(th.rank_defence)} for defence out of ${n} ${esc(L.name)} teams.`,
    `<b>${esc(away)}</b> rate ${ord(ta.rank_attack)} for attack and ${ord(ta.rank_defence)} for defence.`,
    `Playing at home is worth about <b>${L.model.home_effect_pct}%</b> more goals in the ${esc(L.name)}, based on recent seasons.`,
    ...(canBlend && state.view === 'blend' ? [`Adjusted with bookmakers' pre-match odds: home/draw/away is ${Math.round(meta.config.blend.w_1x2 * 100)}% bookmakers and goals markets are ${Math.round(meta.config.blend.w_o25 * 100)}% bookmakers, with the rest from the model. These weights were chosen on past seasons.`] : []),
    `Together that gives predicted goals of <b>${p.lam.toFixed(2)}</b> for ${esc(home)} and <b>${p.mu.toFixed(2)}</b> for ${esc(away)}. Every probability on this page comes from that score distribution.`,
  ];
  [th, ta].forEach(tm => {
    if (tm.limited) why.push(`<span class="limited">${esc(tm.name)} have little recent ${esc(L.name)} data${tm.promoted_prior ? ', so their rating started from the level of last season\'s relegated sides and updates as results come in' : ''}. Treat this prediction with extra caution.</span>`);
  });

  let market = '';
  if (fx && fx.market) {
    const lbl = [home + ' win', 'Draw', away + ' win'];
    market = `<div class="card section"><div class="card-head"><h3>Model vs bookmakers</h3><span class="meta">Bookmaker figures have the margin removed</span></div>
      <table><thead><tr><th>Outcome</th><th class="r">Model only</th><th class="r">Bookmakers</th><th class="r hide-m-cell">Average odds</th>${fx.odds_skybet ? '<th class="r hide-m-cell">Sky Bet</th>' : ''}</tr></thead><tbody>
      ${[0, 1, 2].map(k => `<tr><td>${esc(lbl[k])}</td><td class="r num">${pct([modelP.H, modelP.D, modelP.A][k], 1)}</td><td class="r num">${pct(fx.market[k], 1)}</td><td class="r num hide-m-cell">${fx.odds_avg ? fx.odds_avg[k].toFixed(2) : '—'}</td>${fx.odds_skybet ? `<td class="r num hide-m-cell">${fx.odds_skybet[k].toFixed(2)}</td>` : ''}</tr>`).join('')}
      </tbody></table>
      <p class="meta" style="margin:0;padding:12px 20px;border-top:1px solid var(--border-subtle)">In testing, bookmaker prices were more accurate than the model alone, so the odds-adjusted view leans almost entirely on them for home/draw/away. A big disagreement more often means the model is missing news (injuries, rotation) than that the bookmakers are wrong.</p></div>`;
  }
  const newsCard = await teamNews(lgKey, home, away);
  const atts = L.teams.map(x => x.attack), defs = L.teams.map(x => -x.defence);
  return `<div class="content">
    ${back}
    <div class="page-head"><div>
      <div class="meta" style="margin-bottom:4px">${esc(L.name)}${fx ? ` · ${fmtDay(fx.kickoff)} · ${fmtTime(fx.kickoff)}` : ' · Custom matchup'}</div>
      <h1>${esc(home)} <span style="color:var(--text-tertiary);font-weight:400">vs</span> ${esc(away)}</h1>
    </div>${statusBadge(meta)}</div>
    ${canBlend ? `<div class="toolbar"><div class="chips" role="group" aria-label="Prediction source">
        <button class="chip" data-view="blend" aria-pressed="${state.view === 'blend'}">Odds-adjusted (most accurate)</button>
        <button class="chip" data-view="model" aria-pressed="${state.view === 'model'}">Model only</button></div></div>` : ''}
    <div class="with-panel"><div>
      <div class="card outcomes">${outcome(0, home + ' win')}${outcome(1, 'Draw')}${outcome(2, away + ' win')}</div>
      ${market}
      ${newsCard}
      <div class="grid-2">
        <div class="card"><div class="card-head"><h3>Most likely scores</h3></div>
          <table><tbody>${p.top.slice(0, 5).map(([x, y, v]) => `<tr><td>${esc(home)} ${x}–${y} ${esc(away)}</td><td class="r num">${pct(v, 1)}</td></tr>`).join('')}</tbody></table></div>
        <div class="card card-pad"><h3 style="margin-bottom:12px">Score probabilities (%)</h3>
          <div class="axis-note"><span>Rows: ${esc(home)}</span><span>Columns: ${esc(away)}</span></div>
          <div class="scoregrid" role="img" aria-label="Probability of each scoreline from 0–0 to 5–5">${sg}</div></div>
      </div>
      <div class="card section"><div class="card-head"><h3>Markets</h3><span class="meta">Fair odds = 1 ÷ probability</span></div>
        <table><thead><tr><th>Selection</th><th class="r">Probability</th><th class="r">Fair odds</th></tr></thead><tbody>
          <tr><td class="grp" colspan="3">Double chance</td></tr>
          ${mrow('Home or draw (1X)', p.H + p.D)}${mrow('Away or draw (X2)', p.A + p.D)}${mrow('Either team wins (12)', p.H + p.A)}
          <tr><td class="grp" colspan="3">Total goals</td></tr>
          ${[0.5, 1.5, 2.5, 3.5, 4.5].map(k => mrow(`Over ${k}`, p.over[k]) + mrow(`Under ${k}`, 1 - p.over[k])).join('')}
          <tr><td class="grp" colspan="3">Both teams to score</td></tr>
          ${mrow('Yes', p.btts)}${mrow('No', 1 - p.btts)}
        </tbody></table></div>
      <div class="card card-pad section"><h3 style="margin-bottom:12px">Why the model thinks this</h3><ul class="why">${why.map(w => `<li>${w}</li>`).join('')}</ul>
        <p class="meta" style="margin:12px 0 0">The model uses past results only. It doesn't know about injuries, suspensions or team news.</p></div>
    </div>
    <aside class="panel" aria-label="Team strength and model details">
      <div class="card card-pad"><h3 style="margin-bottom:4px">Team strength</h3><p class="meta" style="margin:0 0 12px">Compared with the rest of the ${esc(L.name)}</p>
        ${[th, ta].map(tm => `
          <div style="font-weight:500;margin-top:8px">${esc(tm.name)}</div>
          <div class="strength-row"><div>${strengthBar(tm.attack, Math.min(...atts), Math.max(...atts))}</div><span class="meta">Attack ${ord(tm.rank_attack)}</span></div>
          <div class="strength-row"><div>${strengthBar(-tm.defence, Math.min(...defs), Math.max(...defs))}</div><span class="meta">Defence ${ord(tm.rank_defence)}</span></div>`).join('')}
      </div>
      <div class="card card-pad"><h3 style="margin-bottom:8px">Predicted goals</h3>
        <div class="kv"><span>${esc(home)}</span><span class="num">${p.lam.toFixed(2)}</span></div>
        <div class="kv"><span>${esc(away)}</span><span class="num">${p.mu.toFixed(2)}</span></div>
        <p class="meta" style="margin:8px 0 0">Model scoring rates, not shot-based xG.</p></div>
      <div class="card card-pad"><h3 style="margin-bottom:8px">Model details</h3>
        <div class="kv"><span>Method</span><span>Dixon–Coles</span></div>
        <div class="kv"><span>Results used</span><span class="num">${L.model.n_matches.toLocaleString('en-GB')}</span></div>
        <div class="kv"><span>Results up to</span><span>${fmtDate(L.data_through)}</span></div>
        <div class="kv"><span>Version</span><span>${esc(L.model.version)}</span></div>
        <div class="kv"><span>Status</span><span>${statusBadge(meta)}</span></div></div>
    </aside></div></div>`;
}

/* ---------- team news ---------- */
const NEWS_BADGE = { injured: 'bad', suspended: 'bad', doubtful: 'warn' };
async function teamNews(lgKey, home, away) {
  if (lgKey !== 'epl') {
    return `<div class="card card-pad section"><h3 style="margin-bottom:4px">Team news</h3><p class="meta" style="margin:0">Injury and suspension news is only available for the Premier League at the moment.</p></div>`;
  }
  let N;
  try { N = await getJSON('news-epl'); } catch { return ''; }
  const col = team => {
    const list = N.teams[team] || [];
    if (!list.length) return `<div><div style="font-weight:500;margin-bottom:6px">${esc(team)}</div><p class="meta" style="margin:0">No reported absences.</p></div>`;
    return `<div><div style="font-weight:500;margin-bottom:6px">${esc(team)}</div>
      <ul style="list-style:none;margin:0;padding:0">${list.map(x => `
        <li style="padding:6px 0;border-bottom:1px solid var(--border-subtle)">
          <div style="display:flex;justify-content:space-between;gap:8px;align-items:center">
            <span>${esc(x.player)} <span class="meta">${esc(x.position)}</span>${x.regular ? ' <span class="badge accent" title="Started at least half of this season\'s matches">Regular starter</span>' : ''}</span>
            <span class="badge ${NEWS_BADGE[x.status]}">${x.status === 'doubtful' && x.chance != null ? `${x.chance}% chance` : x.status[0].toUpperCase() + x.status.slice(1)}</span>
          </div>
          ${x.news ? `<div class="meta">${esc(x.news)}</div>` : ''}
        </li>`).join('')}</ul></div>`;
  };
  return `<div class="card section"><div class="card-head"><h3>Team news</h3><span class="meta">Updated ${fmtDate(N.fetched_at)} · Fantasy Premier League</span></div>
    <div class="card-pad grid-2" style="margin-top:0">${col(home)}${col(away)}</div>
    <p class="meta" style="margin:0;padding:12px 20px;border-top:1px solid var(--border-subtle)">Shown for context. The model doesn't use team news yet, but bookmaker odds usually reflect it, so the odds-adjusted view partly accounts for it.</p></div>`;
}

/* ---------- predict ---------- */
async function predictPage(meta) {
  const s = state.predict;
  const L = await league(s.league);
  const names = L.teams.map(t => t.name).sort((a, b) => a.localeCompare(b));
  if (!names.includes(s.home)) s.home = '';
  if (!names.includes(s.away)) s.away = '';
  const opts = (sel, other) => `<option value="">Choose a team</option>` + names.map(nm => `<option ${nm === sel ? 'selected' : ''} ${nm === other ? 'disabled' : ''}>${esc(nm)}</option>`).join('');
  const ready = s.home && s.away && s.home !== s.away;
  return `<div class="content">
    <div class="page-head"><div><h1>Predict a match</h1><p class="sub">Pick any two teams from the same league to see the model's prediction.</p></div>${statusBadge(meta)}</div>
    <div class="card card-pad">
      <div class="form-row">
        <div class="field"><label for="p-league">League</label><select id="p-league" data-p="league">${meta.leagues.map(l => `<option value="${l.key}" ${l.key === s.league ? 'selected' : ''}>${esc(l.name)}</option>`).join('')}</select></div>
        <div class="field"><label for="p-home">Home team</label><select id="p-home" data-p="home">${opts(s.home, s.away)}</select></div>
        <div class="field"><label for="p-away">Away team</label><select id="p-away" data-p="away">${opts(s.away, s.home)}</select></div>
        <div class="field"><a class="btn primary ${ready ? '' : 'disabled'}" ${ready ? `href="${matchHref(s.league, s.home, s.away)}"` : 'aria-disabled="true" style="opacity:.5;pointer-events:none"'} style="height:40px">See prediction</a></div>
      </div>
    </div>
    <div class="card section"><div class="card-head"><h3>${esc(L.name)} team ratings</h3><span class="meta">Results up to ${fmtDate(L.data_through)}</span></div>
      <table><thead><tr><th>#</th><th>Team</th><th class="r">Attack</th><th class="r">Defence</th><th class="r hide-m-cell">Goal difference vs average team</th></tr></thead><tbody>
      ${L.teams.map((t, i) => `<tr class="rating-row"><td class="num">${i + 1}</td><td>${esc(t.name)}${t.limited ? ' <span class="badge warn" title="Little recent data in this league">Limited data</span>' : ''}</td><td class="r num">${ord(t.rank_attack)}</td><td class="r num">${ord(t.rank_defence)}</td><td class="r num hide-m-cell">${t.strength > 0 ? '+' : ''}${t.strength.toFixed(2)}</td></tr>`).join('')}
      </tbody></table></div>
  </div>`;
}

/* ---------- this season ---------- */
async function historyPage(meta) {
  const H = await getJSON('history');
  const rows = H.matches.filter(m => state.histLeague === 'all' || m.league === state.histLeague);
  const n = rows.length;
  const hits = rows.filter(m => topIdx(m.p) === m.outcome).length;
  const brier = rows.reduce((s, m) => s + m.p.reduce((a, v, k) => a + (v - (k === m.outcome ? 1 : 0)) ** 2, 0), 0) / (n || 1);
  const withMkt = rows.filter(m => m.mkt);
  const mBrier = withMkt.reduce((s, m) => s + m.mkt.reduce((a, v, k) => a + (v - (k === m.outcome ? 1 : 0)) ** 2, 0), 0) / (withMkt.length || 1);
  const mHits = withMkt.filter(m => topIdx(m.mkt) === m.outcome).length;
  const names = Object.fromEntries(meta.leagues.map(l => [l.key, l.name]));
  const chips = [['all', 'All leagues'], ...meta.leagues.map(l => [l.key, l.name])]
    .map(([k, l]) => `<button class="chip" data-hl="${k}" aria-pressed="${state.histLeague === k}">${esc(l)}</button>`).join('');
  const saved = rows.filter(r => r.source === 'saved').length;
  return `<div class="content">
    <div class="page-head"><div><h1>This season</h1><p class="sub">Every ${H.season.slice(0, 2)}/${H.season.slice(2)} match so far, with the prediction the model would have made using only earlier results.</p></div></div>
    <div class="toolbar"><div class="chips" role="group" aria-label="Filter by league">${chips}</div></div>
    ${n ? `<div class="card stats">
      <div class="stat"><div class="lbl">Matches</div><div class="val num">${n}</div></div>
      <div class="stat"><div class="lbl">Top pick correct</div><div class="val num">${pct(hits / n)}</div><div class="meta">Bookmakers: ${withMkt.length ? pct(mHits / withMkt.length) : '—'}</div></div>
      <div class="stat"><div class="lbl">Brier score</div><div class="val num">${brier.toFixed(3)}</div><div class="meta">Bookmakers: ${withMkt.length ? mBrier.toFixed(3) : '—'}</div></div>
      <div class="stat"><div class="lbl">Saved before kick-off</div><div class="val num">${saved}</div><div class="meta">The rest are replays</div></div>
    </div>
    <div class="card"><table><thead><tr><th class="hide-m-cell">Date</th><th>Result</th><th class="hide-m-cell">Model's pick</th><th class="r hide-m-cell">Chance given to result</th><th class="r">Outcome</th></tr></thead><tbody>
      ${rows.slice(0, 200).map(m => {
        const t = topIdx(m.p), ok = t === m.outcome, pick = [m.home, 'Draw', m.away][t];
        return `<tr><td class="num hide-m-cell">${fmtShort(m.date)}</td><td><div style="font-weight:500">${esc(m.home)} ${m.hg}–${m.ag} ${esc(m.away)}</div><div class="meta">${esc(names[m.league])} · <span class="src">${m.source === 'saved' ? 'Saved before kick-off' : 'Replayed'}</span></div></td>
          <td class="hide-m-cell">${esc(pick)} <span class="meta num">${pct(m.p[t])}</span></td>
          <td class="r num hide-m-cell">${pct(m.p[m.outcome])}</td>
          <td class="r">${ok ? '<span class="badge ok">Correct</span>' : '<span class="badge">Missed</span>'}</td></tr>`;
      }).join('')}
    </tbody></table></div>
    <p class="meta" style="margin-top:12px">Brier score measures how good the probabilities were across home, draw and away: lower is better, and 0.667 is what you'd get by guessing a third each. "Replayed" means the prediction was recreated using only results before that week. "Saved" means it was stored before kick-off by this app.</p>`
    : `<div class="card empty"><h3>No matches yet</h3><p class="sub">Nothing has been played in this league this season.</p></div>`}
  </div>`;
}

/* ---------- accuracy ---------- */
async function accuracyPage(meta) {
  const A = await getJSON('accuracy');
  const W = 320, Hh = 240, P = 36, sx = v => P + v * (W - P - 12), sy = v => Hh - P - v * (Hh - P - 12);
  const cal = A.calibration_1x2.filter(c => c.n >= 20);
  const chart = `<svg viewBox="0 0 ${W} ${Hh}" width="100%" role="img" aria-label="Calibration chart of predicted chance against how often it happened">
    ${[0, .25, .5, .75, 1].map(v => `<line x1="${sx(0)}" x2="${sx(1)}" y1="${sy(v)}" y2="${sy(v)}" stroke="#E4E7EC"/><text x="${P - 6}" y="${sy(v) + 4}" font-size="10" fill="#667085" text-anchor="end">${v * 100}%</text><text x="${sx(v)}" y="${Hh - P + 16}" font-size="10" fill="#667085" text-anchor="middle">${v * 100}%</text>`).join('')}
    <line x1="${sx(0)}" y1="${sy(0)}" x2="${sx(1)}" y2="${sy(1)}" stroke="#98A2B3" stroke-dasharray="4 4"/>
    <polyline fill="none" stroke="#3157E1" stroke-width="2" points="${cal.map(c => sx(c.predicted) + ',' + sy(c.observed)).join(' ')}"/>
    ${cal.map(c => `<circle cx="${sx(c.predicted)}" cy="${sy(c.observed)}" r="3.5" fill="#fff" stroke="#3157E1" stroke-width="2"><title>Predicted ${pct(c.predicted)}, happened ${pct(c.observed)} (${c.n} outcomes)</title></circle>`).join('')}
    <text x="${sx(.5)}" y="${Hh - 4}" font-size="11" fill="#475467" text-anchor="middle">Predicted chance</text>
  </svg>`;
  const dc = A.table.find(t => t.key === 'dc'), mk = A.table.find(t => t.key === 'market'), base = A.table.find(t => t.key === 'base');
  const bl = A.table.find(t => t.key === 'blend');
  const f3 = v => v == null ? '—' : v.toFixed(3);
  const d = A.diffs;
  return `<div class="content">
    <div class="page-head"><div><h1>Model accuracy</h1><p class="sub">How the model did on ${A.n_common.toLocaleString('en-GB')} matches from ${A.test_seasons.join(' and ')} that it never saw during tuning.</p></div>${statusBadge(meta)}</div>
    <div class="card stats">
      <div class="stat"><div class="lbl">Top pick correct</div><div class="val num">${pct(dc.x12.accuracy, 1)}</div><div class="meta">${bl ? `Odds-adjusted ${pct(bl.x12.accuracy, 1)}` : `Bookmakers ${pct(mk.x12.accuracy, 1)}`}</div></div>
      <div class="stat"><div class="lbl">Guessing from league averages</div><div class="val num">${pct(base.x12.accuracy, 1)}</div><div class="meta">Always backing the usual result</div></div>
      <div class="stat"><div class="lbl">Calibration error</div><div class="val num">${pct(A.ece_1x2, 1)}</div><div class="meta">Average gap, predicted vs actual</div></div>
      <div class="stat"><div class="lbl">Matches tested</div><div class="val num">${A.n_common.toLocaleString('en-GB')}</div><div class="meta">5 leagues, 2 seasons</div></div>
    </div>
    <div class="card"><div class="card-head"><h3>Comparison</h3><span class="meta">Lower log loss and Brier are better</span></div>
      <table><thead><tr><th>Approach</th><th class="r">Log loss</th><th class="r hide-m-cell">Brier</th><th class="r">Top pick</th><th class="r hide-m-cell">Over 2.5 log loss</th></tr></thead><tbody>
      ${A.table.map(t => `<tr${t.key === 'dc' ? ' style="background:var(--accent-soft)"' : ''}><td style="font-weight:${t.key === 'dc' ? 600 : 400}">${esc(t.label)}</td><td class="r num">${f3(t.x12.log_loss)}</td><td class="r num hide-m-cell">${f3(t.x12.brier)}</td><td class="r num">${pct(t.x12.accuracy, 1)}</td><td class="r num hide-m-cell">${f3(t.o25 && t.o25.log_loss)}</td></tr>`).join('')}
      </tbody></table></div>
    <div class="card card-pad section"><h3 style="margin-bottom:8px">What this means</h3><ul class="why">
      <li>The model is <b>clearly better than guessing</b> from league averages (log loss ${Math.abs(d.dc_vs_base.mean).toFixed(3)} lower; 95% interval ${Math.abs(d.dc_vs_base.hi).toFixed(3)} to ${Math.abs(d.dc_vs_base.lo).toFixed(3)}).</li>
      <li>Its probabilities are <b>well calibrated</b>: when it says 40%, that outcome happened close to 40% of the time.</li>
      <li>It is <b>slightly less accurate than bookmaker closing odds</b> (log loss ${d.dc_vs_market.mean.toFixed(3)} higher). Bookmakers use team news and money from sharp bettors, which this model doesn't have.</li>
      ${bl ? `<li>Combining the model with <b>bookmakers' pre-match odds</b> improves log loss by ${Math.abs(d.blend_vs_dc.mean).toFixed(3)} and matches the bookmakers' own accuracy. The best mix found was ${A.config.blend.w_1x2 * 100}% bookmakers for home/draw/away and ${A.config.blend.w_o25 * 100}% for over/under 2.5. So the model adds almost nothing to the odds for match results, and a little for goals.</li>` : ''}
      ${d.dc_vs_goals ? (A.config.alpha < 1
        ? `<li>Team ratings use <b>${Math.round(A.config.alpha * 100)}% goals and ${Math.round((1 - A.config.alpha) * 100)}% shots on target</b>. Compared with goals alone, log loss changed by ${d.dc_vs_goals.mean.toFixed(4)} (95% interval ${d.dc_vs_goals.lo.toFixed(4)} to ${d.dc_vs_goals.hi.toFixed(4)}).</li>`
        : `<li>Adding <b>shots on target</b> to team ratings was tested and didn't beat goals alone, so ratings use goals only.</li>`) : ''}
      <li>The Dixon–Coles low-score adjustment performs <b>about the same as a plain Poisson model</b> here (difference ${d.dc_vs_poisson.mean.toFixed(4)}).</li>
    </ul></div>
    <div class="grid-2">
      <div class="card card-pad"><h3 style="margin-bottom:4px">Calibration</h3><p class="meta" style="margin:0 0 12px">Home, draw and away probabilities grouped into bands. Closer to the dashed line is better.</p>${chart}</div>
      <div class="card"><div class="card-head"><h3>By league</h3><span class="meta">Log loss</span></div><table><thead><tr><th>League</th><th class="r">Model only</th><th class="r">Bookmakers</th><th class="r">Top pick</th></tr></thead><tbody>
        ${A.by_league.map(l => `<tr><td>${esc(l.name)}</td><td class="r num">${f3(l.dc.log_loss)}</td><td class="r num">${f3(l.market.log_loss)}</td><td class="r num">${pct(l.dc.accuracy)}</td></tr>`).join('')}
      </tbody></table></div>
    </div>
    <details class="card section"><summary>How this was tested</summary><div class="card-pad">
      <ul class="why">
        <li>Each test season was replayed week by week. Before every week, the model was refitted using only results from before that week.</li>
        <li>Settings were chosen on ${A.validation_seasons.join(', ')} only. The test seasons were not used for tuning. Settings tried: ${A.configs_tried.length}. Chosen: time decay ${A.config.xi}, shrinkage ${A.config.ridge}.</li>
        <li>Bookmaker comparison uses the average closing odds across bookmakers with the margin removed. These are the hardest odds to beat because they include all late team news.</li>
        <li>Promoted teams start from the average rating of the teams they replaced.</li>
      </ul></div></details>
  </div>`;
}

/* ---------- events ---------- */
function bind() {
  document.querySelectorAll('[data-league]').forEach(b => b.onclick = () => { state.league = b.dataset.league; route(); });
  document.querySelectorAll('[data-view]').forEach(b => b.onclick = () => { state.view = b.dataset.view; const y = scrollY; route().then(() => scrollTo(0, y)); });
  document.querySelectorAll('[data-hl]').forEach(b => b.onclick = () => { state.histLeague = b.dataset.hl; route(); });
  document.querySelectorAll('[data-p]').forEach(s => s.onchange = () => {
    state.predict[s.dataset.p] = s.value;
    if (s.dataset.p === 'league') { state.predict.home = ''; state.predict.away = ''; }
    route();
  });
  const s = document.querySelector('[data-search]');
  if (s) s.oninput = () => { state.q = s.value; document.getElementById('fixlist').innerHTML = fixturesList(); bindRows(); };
  bindRows();
}
function bindRows() {
  document.querySelectorAll('[data-reset]').forEach(b => b.onclick = () => { state.league = 'all'; state.q = ''; route(); });
  document.querySelectorAll('[data-fix]').forEach(r => r.onclick = () => {
    const f = state.fx.find(x => x.id === r.dataset.fix);
    if (window.innerWidth >= 1200) {
      state.selected = f.id;
      document.querySelectorAll('[data-fix]').forEach(x => x.setAttribute('aria-selected', x === r));
      document.getElementById('panel').innerHTML = quickPanel();
    } else location.hash = matchHref(f.league, f.home, f.away);
  });
}
route();
