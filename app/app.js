/* Matchwise app: renders predictions produced by the Python engine (engine/). All
   probabilities come from data/*.json; this file only formats and displays them. */
'use strict';

const TZ = 'Europe/London';
const state = { league: 'all', q: '', histLeague: 'all', view: 'blend', from: 'fixtures', predict: { league: 'epl', home: '', away: '' } };
const cache = {};

/* ---------- storage-safe theme ---------- */
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* private mode */ } },
};
const prefersDark = () => !!(window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches);
// null = follow the phone's setting; 'light'/'dark' = manual choice (kept in memory if storage is blocked).
let themePref = store.get('mw-theme');
const isDark = () => themePref ? themePref === 'dark' : prefersDark();
function applyTheme() {
  if (themePref) document.documentElement.dataset.theme = themePref;
  else delete document.documentElement.dataset.theme;
  const dark = isDark();
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', dark ? '#0B0D12' : '#F8F9FB');
  document.querySelectorAll('[data-theme-toggle]').forEach(b => {
    b.innerHTML = dark ? I.sun : I.moon;
    b.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');
  });
}
function toggleTheme() {
  const next = isDark() ? 'light' : 'dark';
  // Choosing the same look as the phone goes back to following the phone.
  themePref = next === (prefersDark() ? 'dark' : 'light') ? null : next;
  store.set('mw-theme', themePref);
  applyTheme();
}

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
async function allLeagues(meta) {
  const out = {};
  await Promise.all(meta.leagues.map(async l => { out[l.key] = await league(l.key); }));
  return out;
}
function parsePayload(v) {
  const [lam, mu, H, D, A, o05, o15, o25, o35, o45, btts, ...grid] = v;
  const n = Math.round(Math.sqrt(grid.length));
  const cells = [];
  for (let x = 0; x < n; x++) for (let y = 0; y < n; y++) cells.push([x, y, grid[x * n + y]]);
  const top = cells.slice().sort((a, b) => b[2] - a[2]);
  return { lam, mu, H, D, A, over: { 0.5: o05, 1.5: o15, 2.5: o25, 3.5: o35, 4.5: o45 }, btts, grid, n, top };
}
function pair(L, home, away) {
  const v = L.pairs[`${home}|${away}`];
  return v ? parsePayload(v) : null;
}
/* Fixtures with model and (when odds exist) odds-adjusted predictions attached. */
async function fixtures(meta) {
  const L = await allLeagues(meta);
  return meta.fixtures.map(f => {
    const model = f.assessable ? pair(L[f.league], f.home, f.away) : null;
    return { ...f, lgName: L[f.league].name, model, pr: f.blend ? parsePayload(f.blend) : model };
  });
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
const fmtDate = s => dt(s).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: TZ });
const topIdx = p => p.indexOf(Math.max(...p));
const ord = n => n + (['th', 'st', 'nd', 'rd'][(n % 100 > 10 && n % 100 < 14) ? 0 : (n % 10 < 4 ? n % 10 : 0)] || 'th');
const matchHref = (lg, h, a) => `#/match/${lg}/${encodeURIComponent(h)}/${encodeURIComponent(a)}`;
function ago(s) {
  const m = Math.max(0, Math.round((Date.now() - new Date(s)) / 6e4));
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  return h < 48 ? `${h} h ago` : `${Math.round(h / 24)} days ago`;
}
function countdown(s) {
  if (!hasTime(s)) return '';
  const ms = dt(s) - Date.now();
  if (ms <= 0) return 'Kicked off';
  const h = ms / 36e5;
  if (h < 1) return `Kick-off in ${Math.max(1, Math.round(ms / 6e4))} min`;
  if (h < 24) return `Kick-off in ${Math.round(h)} h`;
  const d = Math.round(h / 24);
  return `Kick-off in ${d} day${d > 1 ? 's' : ''}`;
}
function verdict(p) {
  const probs = [p.H, p.D, p.A], k = topIdx(probs), mx = probs[k];
  if (k === 1) return { label: 'Draw most likely', cls: '', k };
  if (mx >= 0.62) return { label: 'Strong favourite', cls: 'accent', k };
  if (mx >= 0.5) return { label: 'Favourite', cls: 'accent', k };
  if (mx >= 0.42) return { label: 'Slight edge', cls: '', k };
  return { label: 'Close call', cls: '', k };
}

/* ---------- visual atoms ---------- */
function crest(name, size = '') {
  const m = teamMeta(name);
  const ring = isLightColor(m.bg) || isDarkColor(m.bg); // keeps white and black badges visible in both themes
  return `<span class="crest ${size} ${ring ? 'ring' : ''}" style="background:${m.bg};color:${m.fg}" aria-hidden="true">${esc(m.code)}</span>`;
}
let HIST = [];
function formOf(team) {
  return HIST.filter(m => m.home === team || m.away === team).slice(0, 5).reverse().map(m => {
    const gf = m.home === team ? m.hg : m.ag, ga = m.home === team ? m.ag : m.hg;
    return gf > ga ? 'W' : gf === ga ? 'D' : 'L';
  });
}
function formHtml(team) {
  const f = formOf(team);
  if (!f.length) return '';
  const words = { W: 'won', D: 'drew', L: 'lost' };
  return `<span class="form" role="img" aria-label="Last ${f.length}: ${f.map(r => words[r]).join(', ')}">${f.map(r => `<i class="${r}">${r}</i>`).join('')}</span>`;
}
const pbar = (probs, k) => `<div class="pbar" aria-hidden="true">${probs.map((v, i) => `<i class="${i === k ? 'top' : ''}" style="flex:${Math.max(v, 0.02)}"></i>`).join('')}</div>`;
const probsRow = (probs, k) => `<div class="probs num">${[['Home', probs[0]], ['Draw', probs[1]], ['Away', probs[2]]].map(([l, v], i) => `<span class="${i === k ? 'top' : ''}"><b>${pct(v)}</b>${l}</span>`).join('')}</div>`;

/* ---------- icons ---------- */
const svg = (d, extra = '') => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" ${extra}>${d}</svg>`;
const I = {
  weekend: svg('<path d="M12 3.5l2.6 5.2 5.7.8-4.1 4 1 5.7L12 16.5l-5.2 2.7 1-5.7-4.1-4 5.7-.8z"/>'),
  fixtures: svg('<rect x="3" y="4" width="18" height="17" rx="2.5"/><path d="M3 9h18M8 2v4M16 2v4"/>'),
  predict: svg('<circle cx="12" cy="12" r="9"/><path d="M12 7l4 3-1.5 5h-5L8 10z"/>'),
  history: svg('<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/>'),
  accuracy: svg('<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>'),
  back: svg('<path d="M15 6l-6 6 6 6"/>'),
  search: svg('<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>'),
  moon: svg('<path d="M20.5 13.2A8.5 8.5 0 1 1 10.8 3.5a6.6 6.6 0 0 0 9.7 9.7z"/>'),
  sun: svg('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>'),
  share: svg('<path d="M4 12v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7M16 6l-4-4-4 4M12 2v13"/>'),
};
const BRAND = `<span class="brand-mark" aria-hidden="true"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke-width="2.4"><circle cx="12" cy="12" r="9"/><path d="M12 7l4 3-1.5 5h-5L8 10z"/></svg></span>`;
const NAV = [['weekend', 'This weekend', 'Weekend'], ['fixtures', 'Fixtures', 'Fixtures'], ['predict', 'Predict a match', 'Predict'], ['history', 'This season', 'Season'], ['accuracy', 'Model accuracy', 'Accuracy']];
const topbar = () => `<div class="topbar"><span class="brand">${BRAND}Matchwise</span><button class="iconbtn" data-theme-toggle></button></div>`;
const statusPill = meta => meta.status === 'validated'
  ? `<a href="#/accuracy" class="pill ok"><span class="dot"></span>Tested on past seasons</a>`
  : `<a href="#/accuracy" class="pill warn"><span class="dot"></span>Not yet validated</a>`;
const errorBox = e => `<div class="card empty"><h3>Couldn't load predictions</h3><p>${esc(e.message || e)}</p><button class="btn" onclick="location.reload()">Try again</button></div>`;

/* ---------- routing ---------- */
async function route() {
  const parts = location.hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent);
  const page = parts[0] || 'weekend';
  const active = page === 'match' ? state.from : page;
  const nav = short => NAV.map(([k, long, s]) => `<a href="#/${k}" ${k === active ? 'aria-current="page"' : ''}>${short ? `<span class="ic">${I[k]}</span>` : I[k]}<span>${short ? s : long}</span></a>`).join('');
  document.getElementById('nav').innerHTML = nav(false);
  document.getElementById('tabbar').innerHTML = nav(true);
  const main = document.getElementById('main');
  main.innerHTML = `<div class="content">${topbar()}<div class="skeleton"></div><div class="skeleton"></div></div>`;
  applyTheme();
  try {
    const meta = await getJSON('fixtures');
    try { HIST = (await getJSON('history')).matches; } catch { HIST = []; }
    renderFreshness(meta);
    let html, title;
    if (page === 'match') { html = await matchPage(meta, parts[1], parts[2], parts[3]); title = `${parts[2]} vs ${parts[3]}`; }
    else if (page === 'fixtures') { html = await fixturesPage(meta); title = 'Fixtures'; state.from = 'fixtures'; }
    else if (page === 'predict') { html = await predictPage(meta); title = 'Predict a match'; state.from = 'predict'; }
    else if (page === 'history') { html = await historyPage(meta); title = 'This season'; }
    else if (page === 'accuracy') { html = await accuracyPage(meta); title = 'Model accuracy'; }
    else { html = await weekendPage(meta); title = 'This weekend'; state.from = 'weekend'; }
    main.innerHTML = `<div class="page">${html}</div>`;
    document.title = `${title} · Matchwise`;
    bind();
    applyTheme();
  } catch (e) {
    console.error(e);
    main.innerHTML = `<div class="content">${topbar()}${errorBox(e)}</div>`;
    applyTheme();
  }
}
window.addEventListener('hashchange', () => { route().then(() => window.scrollTo(0, 0)); });

function renderFreshness(meta) {
  const ageDays = (Date.now() - new Date(meta.generated_at)) / 864e5;
  const through = meta.leagues.map(l => l.data_through).sort().pop();
  document.getElementById('freshness').innerHTML = `
    <div class="theme-row"><span>Appearance</span><button class="iconbtn" data-theme-toggle></button></div>
    ${ageDays > 3 ? '<span class="pill warn"><span class="dot"></span>Data may be out of date</span>' : ''}
    <div>Updated ${fmtDate(meta.generated_at)} · results to ${fmtDate(through)}<br>Data: football-data.co.uk</div>`;
}
const staleNotice = meta => ((Date.now() - new Date(meta.generated_at)) / 864e5 > 3)
  ? `<div class="notice">Predictions were last updated ${fmtDate(meta.generated_at)}. The daily update may have failed.</div>` : '';

/* ---------- fixture card ---------- */
function fixtureCard(f, showLeague = true) {
  if (!f.pr) {
    return `<div class="card fx"><div class="fx-top"><span class="num">${fmtTime(f.kickoff)}${showLeague ? ' · ' + esc(f.lgName) : ''}</span><span class="pill">Unable to assess</span></div>
      <div class="team">${crest(f.home)}<span class="nm">${esc(f.home)}</span></div><div class="team">${crest(f.away)}<span class="nm">${esc(f.away)}</span></div></div>`;
  }
  const p = f.pr, probs = [p.H, p.D, p.A], v = verdict(p);
  return `<a class="card fx" href="${matchHref(f.league, f.home, f.away)}" aria-label="${esc(f.home)} versus ${esc(f.away)}: ${pct(p.H)} home, ${pct(p.D)} draw, ${pct(p.A)} away">
    <div class="fx-top"><span class="num">${fmtTime(f.kickoff)}${showLeague ? ' · ' + esc(f.lgName) : ''}</span><span class="pill ${v.cls}">${v.label}</span></div>
    <div class="team">${crest(f.home)}<span class="nm ${v.k === 0 ? 'fav' : ''}">${esc(f.home)}</span>${formHtml(f.home)}</div>
    <div class="team">${crest(f.away)}<span class="nm ${v.k === 2 ? 'fav' : ''}">${esc(f.away)}</span>${formHtml(f.away)}</div>
    ${pbar(probs, v.k)}${probsRow(probs, v.k)}
    <div class="fx-foot num"><span>Expected goals <b>${p.lam.toFixed(1)}–${p.mu.toFixed(1)}</b> · Likely <b>${p.top[0][0]}–${p.top[0][1]}</b></span><span>${f.blend ? 'Odds-adjusted' : 'Model'}</span></div>
  </a>`;
}

/* ---------- weekend ---------- */
function weekendWindow(fx) {
  const now = new Date();
  const london = new Date(now.toLocaleString('en-US', { timeZone: TZ }));
  const daysToMon = (8 - london.getDay()) % 7 || 7; // through the coming Monday
  const end = new Date(now.getTime() + daysToMon * 864e5 + 864e5);
  const inWin = fx.filter(f => dt(f.kickoff) <= end);
  return inWin.length ? inWin : fx;
}
async function weekendPage(meta) {
  const all = (await fixtures(meta)).filter(f => f.pr && dt(f.kickoff) > Date.now() - 2 * 36e5);
  const fx = weekendWindow(all);
  const head = `${topbar()}<div class="page-head"><div><h1>This weekend</h1><p class="sub">${fx.length} matches across ${new Set(fx.map(f => f.league)).size} leagues${fx.length ? ` · ${fmtShort(fx[0].kickoff)} – ${fmtShort(fx[fx.length - 1].kickoff)}` : ''}</p></div>${statusPill(meta)}</div>`;
  if (!fx.length) return `<div class="content">${head}${staleNotice(meta)}<div class="card empty"><h3>No upcoming matches found</h3><p>You can still predict any match.</p><a class="btn primary" href="#/predict">Predict a match</a></div></div>`;

  // Last 7 days of results: model vs bookmakers on the same matches.
  const latest = HIST.length ? dt(HIST[0].date) : null;
  const recent = latest ? HIST.filter(m => (latest - dt(m.date)) / 864e5 < 7) : [];
  const withMkt = recent.filter(m => m.mkt);
  const hits = recent.filter(m => topIdx(m.p) === m.outcome).length;
  const mHits = withMkt.filter(m => topIdx(m.mkt) === m.outcome).length;
  const mx = f => Math.max(f.pr.H, f.pr.D, f.pr.A);
  const row = (f, val, muted) => `<a class="irow" href="${matchHref(f.league, f.home, f.away)}"><span class="pairc">${crest(f.home, 'sm')}${crest(f.away, 'sm')}</span><span class="t">${esc(f.home)} v ${esc(f.away)}</span><span class="v num" ${muted ? 'style="color:var(--text-2)"' : ''}>${val}</span></a>`;
  const strong = fx.slice().sort((a, b) => Math.max(b.pr.H, b.pr.A) - Math.max(a.pr.H, a.pr.A)).slice(0, 4);
  const close = fx.slice().sort((a, b) => mx(a) - mx(b)).slice(0, 4);
  const goals = fx.slice().sort((a, b) => (b.pr.lam + b.pr.mu) - (a.pr.lam + a.pr.mu)).slice(0, 4);
  const next = fx.slice(0, 4);
  const favName = f => f.pr.H >= f.pr.A ? f.home : f.away;
  return `<div class="content">${head}${staleNotice(meta)}
    ${recent.length ? `<div class="card stats">
      <div class="stat"><div class="lbl">Last 7 days</div><div class="val num">${hits}/${recent.length}</div><div class="meta">top picks right</div></div>
      <div class="stat"><div class="lbl">Hit rate</div><div class="val num">${pct(hits / recent.length)}</div><div class="meta">${withMkt.length ? `Bookmakers ${pct(mHits / withMkt.length)}` : 'No odds to compare'}</div></div>
      <div class="stat"><div class="lbl">This season</div><div class="val num">${pct(HIST.filter(m => topIdx(m.p) === m.outcome).length / HIST.length)}</div><div class="meta">${HIST.length} matches</div></div>
      <div class="stat"><div class="lbl">Matches ahead</div><div class="val num">${fx.length}</div><div class="meta">${fx.filter(f => f.blend).length} odds-adjusted</div></div>
    </div>` : ''}
    <div class="overview">
      <div class="card insight"><h3>Strongest favourites</h3><p>Where the prediction is most confident</p>${strong.map(f => row(f, `${esc(teamMeta(favName(f)).code)} ${pct(Math.max(f.pr.H, f.pr.A))}`)).join('')}</div>
      <div class="card insight"><h3>Closest games</h3><p>Home · draw · away</p>${close.map(f => row(f, `${pct(f.pr.H)}·${pct(f.pr.D)}·${pct(f.pr.A)}`, true)).join('')}</div>
      <div class="card insight"><h3>Most goals expected</h3><p>Combined expected goals</p>${goals.map(f => row(f, (f.pr.lam + f.pr.mu).toFixed(1))).join('')}</div>
    </div>
    <div class="day" style="margin-top:26px"><span>Next kick-offs</span><a href="#/fixtures">All fixtures</a></div>
    <div class="fx-grid">${next.map(f => fixtureCard(f)).join('')}</div>
  </div>`;
}

/* ---------- fixtures ---------- */
async function fixturesPage(meta) {
  state.fx = (await fixtures(meta)).filter(f => !hasTime(f.kickoff) || dt(f.kickoff) > Date.now() - 2 * 36e5);
  const chips = [['all', 'All'], ...meta.leagues.map(l => [l.key, l.name])]
    .map(([k, l]) => `<button class="chip" data-league="${k}" aria-pressed="${state.league === k}">${esc(l)}</button>`).join('');
  return `<div class="content">${topbar()}
    <div class="page-head"><div><h1>Fixtures</h1><p class="sub">Next 10 days · UK time · bookmaker odds appear a few days before each match</p></div>${statusPill(meta)}</div>
    ${staleNotice(meta)}
    ${state.fx.length ? `<div class="toolbar"><div class="chips" role="group" aria-label="Filter by league">${chips}</div>
      <label class="search">${I.search}<input type="search" placeholder="Search teams" aria-label="Search teams" value="${esc(state.q)}" data-search></label></div>
      <div id="fixlist">${fixturesList()}</div>`
    : `<div class="card empty"><h3>No upcoming fixtures found</h3><p>The schedule couldn't be loaded, or every match has already kicked off.</p><a class="btn primary" href="#/predict">Predict a match</a></div>`}
  </div>`;
}
function fixturesList() {
  const q = state.q.trim().toLowerCase();
  const list = state.fx.filter(f => (state.league === 'all' || f.league === state.league) && (!q || `${f.home} ${f.away}`.toLowerCase().includes(q)));
  if (!list.length) return `<div class="card empty"><h3>No fixtures match</h3><p>Try another league or clear the search.</p><button class="btn" data-reset>Clear filters</button></div>`;
  const days = {};
  list.forEach(f => (days[fmtDay(f.kickoff)] ||= []).push(f));
  return Object.entries(days).map(([day, fs]) => `
    <div class="day"><span>${day}</span><span>${fs.length} match${fs.length > 1 ? 'es' : ''}</span></div>
    <div class="fx-grid">${fs.map(f => fixtureCard(f, state.league === 'all')).join('')}</div>`).join('');
}

/* ---------- match ---------- */
async function matchPage(meta, lgKey, home, away) {
  const backTo = { predict: ['#/predict', 'Predict'], weekend: ['#/weekend', 'This weekend'] }[state.from] || ['#/fixtures', 'Fixtures'];
  const back = `<a class="back" href="${backTo[0]}">${I.back}${backTo[1]}</a>`;
  const lgMeta = meta.leagues.find(l => l.key === lgKey);
  if (!lgMeta) return `<div class="content">${back}<div class="card empty"><h3>Unknown league</h3></div></div>`;
  const L = await league(lgKey);
  const modelP = pair(L, home, away);
  if (!modelP) return `<div class="content">${back}<div class="card empty"><h3>Unable to assess this match</h3><p>One of the teams isn't in the current ${esc(L.name)} model.</p></div></div>`;
  const fx = meta.fixtures.find(f => f.league === lgKey && f.home === home && f.away === away);
  const canBlend = !!(fx && fx.blend);
  const blended = canBlend && state.view === 'blend';
  const p = blended ? parsePayload(fx.blend) : modelP;
  const T = Object.fromEntries(L.teams.map(t => [t.name, t]));
  const th = T[home], ta = T[away], n = L.teams.length;
  const probs = [p.H, p.D, p.A], v = verdict(p);
  const mrow = (sel, val) => `<tr><td>${sel}</td><td class="r num"><span class="meter"><i style="width:${val * 100}%"></i></span>${pct(val, 1)}</td><td class="r num">${fair(val)}</td></tr>`;

  const max = p.top[0][2];
  let sg = `<div class="h"></div>` + [...Array(p.n).keys()].map(y => `<div class="h">${y}</div>`).join('');
  for (let x = 0; x < p.n; x++) {
    sg += `<div class="h">${x}</div>`;
    for (let y = 0; y < p.n; y++) {
      const val = p.grid[x * p.n + y], a = Math.min(1, (val / max)) * 0.9;
      sg += `<div class="c num" style="background:color-mix(in srgb, var(--accent) ${Math.round(a * 100)}%, var(--surface-2));color:${a > .5 ? '#fff' : 'var(--text)'}" title="${esc(home)} ${x}–${y} ${esc(away)}: ${pct(val, 1)}">${(val * 100).toFixed(1)}</div>`;
    }
  }

  const why = [
    `<b>${esc(home)}</b> rate ${ord(th.rank_attack)} for attack and ${ord(th.rank_defence)} for defence out of ${n} ${esc(L.name)} teams.`,
    `<b>${esc(away)}</b> rate ${ord(ta.rank_attack)} for attack and ${ord(ta.rank_defence)} for defence.`,
    `Playing at home is worth about <b>${L.model.home_effect_pct}%</b> more goals in the ${esc(L.name)}, based on recent seasons.`,
    ...(L.model.alpha < 1 ? [`Ratings are built from <b>${Math.round(L.model.alpha * 100)}% goals and ${Math.round((1 - L.model.alpha) * 100)}% shots on target</b>, which smooths out lucky and unlucky results.`] : []),
    ...(blended ? [`Adjusted with bookmakers' pre-match odds: home/draw/away is ${Math.round(meta.config.blend.w_1x2 * 100)}% bookmakers and goals markets are ${Math.round(meta.config.blend.w_o25 * 100)}% bookmakers. These weights were chosen on past seasons.`] : []),
    `Together that gives expected goals of <b>${p.lam.toFixed(2)}</b> for ${esc(home)} and <b>${p.mu.toFixed(2)}</b> for ${esc(away)}. Every probability on this page comes from that score distribution.`,
  ];
  [th, ta].forEach(tm => {
    if (tm.limited) why.push(`<span style="color:var(--warn)">${esc(tm.name)} have little recent ${esc(L.name)} data${tm.promoted_prior ? ', so their rating started from the level of last season\'s relegated sides' : ''}. Treat this prediction with extra caution.</span>`);
  });

  let market = '';
  if (fx && fx.market) {
    const lbl = [home + ' win', 'Draw', away + ' win'];
    const odd = (arr, k) => arr ? arr[k].toFixed(2) : '—';
    const src = fx.odds_source === 'The Odds API'
      ? `Average of ${fx.odds_books} UK bookmakers via The Odds API${fx.odds_updated ? `, updated ${ago(fx.odds_updated)}` : ''}.`
      : 'Average pre-match odds via football-data.co.uk.';
    market = `<div class="card"><div class="card-head"><h3>Model vs bookmakers</h3><span class="small muted">Margin removed</span></div>
      <table><thead><tr><th>Outcome</th><th class="r">Model</th><th class="r">Bookies</th><th class="r">Sky Bet</th><th class="r">Coral</th><th class="r hide-m">Average</th></tr></thead><tbody>
      ${[0, 1, 2].map(k => `<tr><td>${esc(lbl[k])}</td><td class="r num">${pct([modelP.H, modelP.D, modelP.A][k])}</td><td class="r num">${pct(fx.market[k])}</td><td class="r num">${odd(fx.odds_skybet, k)}</td><td class="r num">${odd(fx.odds_coral, k)}</td><td class="r num hide-m">${odd(fx.odds_avg, k)}</td></tr>`).join('')}
      </tbody></table>
      <p class="card-foot">${src} Sky Bet, Coral and Average columns are decimal odds. Bookmaker prices were more accurate than the model alone in testing, so a big disagreement more often means the model is missing news.</p></div>`;
  }
  const newsCard = await teamNews(lgKey, home, away);
  const atts = L.teams.map(x => x.attack), defs = L.teams.map(x => -x.defence);
  const sb = (val, arr) => `<div class="track"><i style="width:${Math.max(4, ((val - Math.min(...arr)) / ((Math.max(...arr) - Math.min(...arr)) || 1)) * 100)}%"></i></div>`;
  const cd = fx ? countdown(fx.kickoff) : '';

  return `<div class="content">
    ${back}
    <div class="card hero">
      <div class="meta">${esc(L.name)} · ${fx ? `${fmtDay(fx.kickoff)} · ${fmtTime(fx.kickoff)}` : 'Custom matchup'}</div>
      <div class="vs">
        <div class="side">${crest(home, 'lg')}<span class="nm">${esc(home)}</span>${formHtml(home)}</div>
        <div class="mid">vs</div>
        <div class="side">${crest(away, 'lg')}<span class="nm">${esc(away)}</span>${formHtml(away)}</div>
      </div>
      <span class="pill accent">${v.label}${cd ? ' · ' + cd : ''}</span>
      <div class="big3 num">${[[home + ' win', p.H], ['Draw', p.D], [away + ' win', p.A]].map(([l, val], i) => `<div class="${i === v.k ? 'top' : ''}"><b>${pct(val)}</b><span>${esc(l)}</span><small>Fair odds ${fair(val)}</small></div>`).join('')}</div>
      ${pbar(probs, v.k)}
    </div>
    <nav class="sectabs" aria-label="Sections"><a href="#prediction" data-sec>Prediction</a><a href="#goals" data-sec>Goals</a><a href="#scores" data-sec>Scores</a><a href="#news" data-sec>Team news</a><a href="#why" data-sec>Why</a></nav>
    ${canBlend ? `<div class="toggle" role="group" aria-label="Prediction source"><button data-view="blend" aria-pressed="${state.view === 'blend'}">Odds-adjusted</button><button data-view="model" aria-pressed="${state.view === 'model'}">Model only</button></div>` : ''}
    <section id="prediction">
      <div class="keys num">
        <div class="card key"><div class="k">Expected goals</div><div class="v">${p.lam.toFixed(1)} – ${p.mu.toFixed(1)}</div></div>
        <div class="card key"><div class="k">Most likely score</div><div class="v">${p.top[0][0]}–${p.top[0][1]} <small>${pct(p.top[0][2])}</small></div></div>
        <div class="card key"><div class="k">Over 2.5 goals</div><div class="v">${pct(p.over[2.5])}</div></div>
        <div class="card key"><div class="k">Both teams score</div><div class="v">${pct(p.btts)}</div></div>
      </div>
    </section>
    <div class="match-cols"><div>
      ${market}
      <section id="goals" class="card"><div class="card-head"><h3>Markets</h3><span class="small muted">Fair odds = 1 ÷ probability</span></div>
        <table><thead><tr><th>Selection</th><th class="r">Probability</th><th class="r">Fair odds</th></tr></thead><tbody>
          <tr><td class="grp" colspan="3">Double chance</td></tr>
          ${mrow('Home or draw (1X)', p.H + p.D)}${mrow('Away or draw (X2)', p.A + p.D)}${mrow('Either team wins (12)', p.H + p.A)}
          <tr><td class="grp" colspan="3">Total goals</td></tr>
          ${[0.5, 1.5, 2.5, 3.5, 4.5].map(k => mrow(`Over ${k}`, p.over[k]) + mrow(`Under ${k}`, 1 - p.over[k])).join('')}
          <tr><td class="grp" colspan="3">Both teams to score</td></tr>
          ${mrow('Yes', p.btts)}${mrow('No', 1 - p.btts)}
        </tbody></table></section>
      <section id="scores" class="grid-2" style="margin-top:12px">
        <div class="card"><div class="card-head"><h3>Most likely scores</h3></div>
          <table><tbody>${p.top.slice(0, 6).map(([x, y, val]) => `<tr><td>${esc(teamMeta(home).code)} ${x}–${y} ${esc(teamMeta(away).code)}</td><td class="r num"><span class="meter"><i style="width:${val / max * 100}%"></i></span>${pct(val, 1)}</td></tr>`).join('')}</tbody></table></div>
        <div class="card card-pad"><h3 style="margin-bottom:10px">Score grid (%)</h3>
          <div class="axis"><span>↓ ${esc(home)}</span><span>${esc(away)} →</span></div>
          <div class="scoregrid" role="img" aria-label="Probability of each scoreline from 0–0 to 5–5">${sg}</div></div>
      </section>
      <section id="news" style="margin-top:12px">${newsCard}</section>
      <section id="why" class="card card-pad" style="margin-top:12px"><h3 style="margin-bottom:12px">Why the model thinks this</h3><ul class="why">${why.map(w => `<li>${w}</li>`).join('')}</ul>
        <p class="small muted" style="margin:10px 0 0">The model itself uses results and shots, not team news.</p></section>
    </div>
    <aside aria-label="Team strength and model details">
      <div class="card card-pad"><h3 style="margin-bottom:2px">Team strength</h3><p class="small muted" style="margin:0 0 10px">Compared with the rest of the ${esc(L.name)}</p>
        ${[th, ta].map(tm => `<div class="news-team" style="margin-top:10px">${crest(tm.name, 'sm')}${esc(tm.name)}</div>
          <div class="strength"><div>${sb(tm.attack, atts)}</div><span class="small muted">Attack ${ord(tm.rank_attack)}</span></div>
          <div class="strength"><div>${sb(-tm.defence, defs)}</div><span class="small muted">Defence ${ord(tm.rank_defence)}</span></div>`).join('')}
      </div>
      <div class="card card-pad"><h3 style="margin-bottom:6px">Model details</h3>
        <div class="kv"><span>Method</span><span>Dixon–Coles</span></div>
        <div class="kv"><span>Prediction</span><span>${blended ? 'Odds-adjusted' : 'Model only'}</span></div>
        <div class="kv"><span>Results used</span><span class="num">${L.model.n_matches.toLocaleString('en-GB')}</span></div>
        <div class="kv"><span>Results up to</span><span>${fmtDate(L.data_through)}</span></div>
        <div class="kv"><span>Status</span><span>${statusPill(meta)}</span></div></div>
    </aside></div>
  </div>`;
}

/* ---------- team news ---------- */
async function teamNews(lgKey, home, away) {
  if (lgKey !== 'epl') return `<div class="card card-pad"><h3 style="margin-bottom:4px">Team news</h3><p class="small muted" style="margin:0">Injury and suspension news is only available for the Premier League at the moment.</p></div>`;
  let N;
  try { N = await getJSON('news-epl'); } catch { return ''; }
  const col = team => {
    const list = N.teams[team] || [];
    return `<div><div class="news-team">${crest(team, 'sm')}${esc(team)}</div>
      ${list.length ? `<ul class="news-list">${list.map(x => `<li>
        <div class="line"><span>${esc(x.player)} <span class="small muted">${esc(x.position)}</span>${x.regular ? ' <span class="pill accent" title="Started at least half of this season\'s matches">Regular</span>' : ''}</span>
          <span class="pill ${x.status === 'doubtful' ? 'warn' : 'bad'}">${x.status === 'doubtful' && x.chance != null ? `${x.chance}%` : x.status[0].toUpperCase() + x.status.slice(1)}</span></div>
        ${x.news ? `<div class="small muted">${esc(x.news)}</div>` : ''}</li>`).join('')}</ul>` : '<p class="small muted" style="margin:0">No reported absences.</p>'}</div>`;
  };
  return `<div class="card"><div class="card-head"><h3>Team news</h3><span class="small muted">Updated ${fmtDate(N.fetched_at)} · Fantasy Premier League</span></div>
    <div class="card-pad grid-2">${col(home)}${col(away)}</div>
    <p class="card-foot">Shown for context. Bookmaker odds usually reflect it, so the odds-adjusted view partly accounts for it.</p></div>`;
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
  return `<div class="content">${topbar()}
    <div class="page-head"><div><h1>Predict a match</h1><p class="sub">Pick any two teams from the same league.</p></div>${statusPill(meta)}</div>
    <div class="card card-pad">
      <div class="form-row">
        <div class="field"><label for="p-league">League</label><select id="p-league" data-p="league">${meta.leagues.map(l => `<option value="${l.key}" ${l.key === s.league ? 'selected' : ''}>${esc(l.name)}</option>`).join('')}</select></div>
        <div class="field"><label for="p-home">Home team</label><select id="p-home" data-p="home">${opts(s.home, s.away)}</select></div>
        <div class="field"><label for="p-away">Away team</label><select id="p-away" data-p="away">${opts(s.away, s.home)}</select></div>
        <div class="field"><a class="btn primary" ${ready ? `href="${matchHref(s.league, s.home, s.away)}"` : 'aria-disabled="true"'}>See prediction</a></div>
      </div>
    </div>
    <div class="card" style="margin-top:14px"><div class="card-head"><h3>${esc(L.name)} power ratings</h3><span class="small muted">Results to ${fmtDate(L.data_through)}</span></div>
      <table><thead><tr><th style="width:44px">#</th><th>Team</th><th class="r">Attack</th><th class="r">Defence</th><th class="r hide-m">vs average team</th></tr></thead><tbody>
      ${L.teams.map((t, i) => `<tr><td class="num muted">${i + 1}</td><td><span class="team" style="padding:0">${crest(t.name, 'sm')}<span>${esc(t.name)}</span>${t.limited ? '<span class="pill warn">Limited data</span>' : ''}</span></td><td class="r num">${ord(t.rank_attack)}</td><td class="r num">${ord(t.rank_defence)}</td><td class="r num hide-m">${t.strength > 0 ? '+' : ''}${t.strength.toFixed(2)} goals</td></tr>`).join('')}
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
  const chips = [['all', 'All'], ...meta.leagues.map(l => [l.key, l.name])]
    .map(([k, l]) => `<button class="chip" data-hl="${k}" aria-pressed="${state.histLeague === k}">${esc(l)}</button>`).join('');
  const saved = rows.filter(r => r.source === 'saved').length;
  return `<div class="content">${topbar()}
    <div class="page-head"><div><h1>This season</h1><p class="sub">Every ${H.season.slice(0, 2)}/${H.season.slice(2)} match so far, with the prediction made using only earlier results.</p></div></div>
    <div class="toolbar"><div class="chips" role="group" aria-label="Filter by league">${chips}</div></div>
    ${n ? `<div class="card stats">
      <div class="stat"><div class="lbl">Matches</div><div class="val num">${n}</div><div class="meta">${saved} saved before kick-off</div></div>
      <div class="stat"><div class="lbl">Top pick right</div><div class="val num">${pct(hits / n)}</div><div class="meta">Bookmakers ${withMkt.length ? pct(mHits / withMkt.length) : '—'}</div></div>
      <div class="stat"><div class="lbl">Brier score</div><div class="val num">${brier.toFixed(3)}</div><div class="meta">Bookmakers ${withMkt.length ? mBrier.toFixed(3) : '—'}</div></div>
      <div class="stat"><div class="lbl">Guessing</div><div class="val num">0.667</div><div class="meta">Brier for ⅓ each</div></div>
    </div>
    <div class="card"><table><thead><tr><th class="hide-m">Date</th><th>Result</th><th class="hide-m">Model's pick</th><th class="r hide-m">Chance given</th><th class="r">Outcome</th></tr></thead><tbody>
      ${rows.slice(0, 200).map(m => {
        const t = topIdx(m.p), ok = t === m.outcome, pick = [m.home, 'Draw', m.away][t];
        return `<tr><td class="num hide-m muted">${fmtShort(m.date)}</td>
          <td><div class="team" style="padding:0">${crest(m.home, 'sm')}<span style="font-weight:600" class="num">${esc(m.home)} ${m.hg}–${m.ag} ${esc(m.away)}</span></div>
            <div class="small muted" style="margin-left:38px">${esc(names[m.league])} · ${m.source === 'saved' ? 'Saved before kick-off' : 'Replayed'}</div></td>
          <td class="hide-m">${esc(pick)} <span class="small muted num">${pct(m.p[t])}</span></td>
          <td class="r num hide-m">${pct(m.p[m.outcome])}</td>
          <td class="r">${ok ? '<span class="pill ok">Correct</span>' : '<span class="pill">Missed</span>'}</td></tr>`;
      }).join('')}
    </tbody></table></div>
    <p class="small muted" style="margin-top:12px">Brier score measures how good the probabilities were (lower is better). "Replayed" means the prediction was recreated using only results before that week; "saved" means it was stored before kick-off.</p>`
    : `<div class="card empty"><h3>No matches yet</h3><p>Nothing has been played in this league this season.</p></div>`}
  </div>`;
}

/* ---------- accuracy ---------- */
async function accuracyPage(meta) {
  const A = await getJSON('accuracy');
  const W = 320, Hh = 240, P = 36, sx = v => P + v * (W - P - 12), sy = v => Hh - P - v * (Hh - P - 12);
  const cal = A.calibration_1x2.filter(c => c.n >= 20);
  const chart = `<svg viewBox="0 0 ${W} ${Hh}" width="100%" role="img" aria-label="Calibration chart of predicted chance against how often it happened" style="color:var(--text-3)">
    ${[0, .25, .5, .75, 1].map(v => `<line x1="${sx(0)}" x2="${sx(1)}" y1="${sy(v)}" y2="${sy(v)}" stroke="var(--border)"/><text x="${P - 6}" y="${sy(v) + 4}" font-size="10" fill="currentColor" text-anchor="end">${v * 100}%</text><text x="${sx(v)}" y="${Hh - P + 16}" font-size="10" fill="currentColor" text-anchor="middle">${v * 100}%</text>`).join('')}
    <line x1="${sx(0)}" y1="${sy(0)}" x2="${sx(1)}" y2="${sy(1)}" stroke="var(--text-3)" stroke-dasharray="4 4"/>
    <polyline fill="none" stroke="var(--accent)" stroke-width="2" points="${cal.map(c => sx(c.predicted) + ',' + sy(c.observed)).join(' ')}"/>
    ${cal.map(c => `<circle cx="${sx(c.predicted)}" cy="${sy(c.observed)}" r="3.5" fill="var(--surface)" stroke="var(--accent)" stroke-width="2"><title>Predicted ${pct(c.predicted)}, happened ${pct(c.observed)} (${c.n} outcomes)</title></circle>`).join('')}
    <text x="${sx(.5)}" y="${Hh - 4}" font-size="11" fill="currentColor" text-anchor="middle">Predicted chance</text>
  </svg>`;
  const get = k => A.table.find(t => t.key === k);
  const dc = get('dc'), mk = get('market'), base = get('base'), bl = get('blend');
  const f3 = v => v == null ? '—' : v.toFixed(3);
  const d = A.diffs;
  return `<div class="content">${topbar()}
    <div class="page-head"><div><h1>Model accuracy</h1><p class="sub">Tested on ${A.n_common.toLocaleString('en-GB')} matches from ${A.test_seasons.join(' and ')} that the model never saw during tuning.</p></div>${statusPill(meta)}</div>
    <div class="card stats">
      <div class="stat"><div class="lbl">Odds-adjusted</div><div class="val num">${pct((bl || dc).x12.accuracy, 1)}</div><div class="meta">top pick right</div></div>
      <div class="stat"><div class="lbl">Model only</div><div class="val num">${pct(dc.x12.accuracy, 1)}</div><div class="meta">top pick right</div></div>
      <div class="stat"><div class="lbl">League averages</div><div class="val num">${pct(base.x12.accuracy, 1)}</div><div class="meta">naive guessing</div></div>
      <div class="stat"><div class="lbl">Calibration gap</div><div class="val num">${pct(A.ece_1x2, 1)}</div><div class="meta">predicted vs actual</div></div>
    </div>
    <div class="card"><div class="card-head"><h3>Comparison</h3><span class="small muted">Lower log loss is better</span></div>
      <table><thead><tr><th>Approach</th><th class="r">Log loss</th><th class="r hide-m">Brier</th><th class="r">Top pick</th><th class="r hide-m">Over 2.5</th></tr></thead><tbody>
      ${A.table.map(t => `<tr${t.key === 'dc' || t.key === 'blend' ? ' style="background:var(--accent-soft)"' : ''}><td style="font-weight:${t.key === 'dc' || t.key === 'blend' ? 600 : 400}">${esc(t.label)}</td><td class="r num">${f3(t.x12.log_loss)}</td><td class="r num hide-m">${f3(t.x12.brier)}</td><td class="r num">${pct(t.x12.accuracy, 1)}</td><td class="r num hide-m">${f3(t.o25 && t.o25.log_loss)}</td></tr>`).join('')}
      </tbody></table></div>
    <div class="card card-pad" style="margin-top:12px"><h3 style="margin-bottom:10px">What this means</h3><ul class="why">
      <li>The model is <b>clearly better than guessing</b> from league averages (log loss ${Math.abs(d.dc_vs_base.mean).toFixed(3)} lower).</li>
      <li>Its probabilities are <b>well calibrated</b>: when it says 40%, that outcome happened close to 40% of the time.</li>
      ${bl ? `<li>Combining it with <b>bookmakers' pre-match odds</b> matches the bookmakers' own accuracy. The best mix was ${Math.round(A.config.blend.w_1x2 * 100)}% bookmakers for home/draw/away and ${Math.round(A.config.blend.w_o25 * 100)}% for over/under 2.5.</li>` : ''}
      ${d.dc_vs_goals ? (A.config.alpha < 1 ? `<li>Ratings use <b>${Math.round(A.config.alpha * 100)}% goals and ${Math.round((1 - A.config.alpha) * 100)}% shots on target</b>, a small improvement over goals alone, mainly for goals markets.</li>` : `<li>Adding shots on target was tested and didn't beat goals alone.</li>`) : ''}
      <li>Bookmakers' <b>closing</b> odds remain the most accurate (${pct(mk.x12.accuracy, 1)} top pick), because they include late team news.</li>
    </ul></div>
    <div class="grid-2" style="margin-top:12px">
      <div class="card card-pad"><h3 style="margin-bottom:2px">Calibration</h3><p class="small muted" style="margin:0 0 10px">Closer to the dashed line is better.</p>${chart}</div>
      <div class="card"><div class="card-head"><h3>By league</h3><span class="small muted">Log loss</span></div><table><thead><tr><th>League</th><th class="r">Model</th><th class="r">Bookmakers</th><th class="r">Top pick</th></tr></thead><tbody>
        ${A.by_league.map(l => `<tr><td>${esc(l.name)}</td><td class="r num">${f3(l.dc.log_loss)}</td><td class="r num">${f3(l.market.log_loss)}</td><td class="r num">${pct(l.dc.accuracy)}</td></tr>`).join('')}
      </tbody></table></div>
    </div>
    <details class="card" style="margin-top:12px"><summary>How this was tested</summary><div class="card-pad"><ul class="why">
      <li>Each test season was replayed week by week. Before every week the model was refitted using only results from before that week.</li>
      <li>Settings were chosen on ${A.validation_seasons.join(', ')} only (${A.configs_tried.length} combinations tried); the test seasons were never used for tuning.</li>
      <li>Bookmaker comparisons use average odds across bookmakers with the margin removed.</li>
      <li>Promoted teams start from the average rating of the teams they replaced.</li>
    </ul></div></details>
  </div>`;
}

/* ---------- events ---------- */
function bind() {
  document.querySelectorAll('[data-theme-toggle]').forEach(b => b.onclick = toggleTheme);
  document.querySelectorAll('[data-league]').forEach(b => b.onclick = () => { state.league = b.dataset.league; document.getElementById('fixlist').innerHTML = fixturesList(); bindList(); document.querySelectorAll('[data-league]').forEach(x => x.setAttribute('aria-pressed', x === b)); });
  document.querySelectorAll('[data-hl]').forEach(b => b.onclick = () => { state.histLeague = b.dataset.hl; route(); });
  document.querySelectorAll('[data-view]').forEach(b => b.onclick = () => { state.view = b.dataset.view; const y = scrollY; route().then(() => scrollTo(0, y)); });
  document.querySelectorAll('[data-p]').forEach(s => s.onchange = () => {
    state.predict[s.dataset.p] = s.value;
    if (s.dataset.p === 'league') { state.predict.home = ''; state.predict.away = ''; }
    route();
  });
  const s = document.querySelector('[data-search]');
  if (s) s.oninput = () => { state.q = s.value; document.getElementById('fixlist').innerHTML = fixturesList(); bindList(); };
  bindList();
  // Section tabs: smooth-scroll without touching the router hash, and highlight the section in view.
  const tabs = [...document.querySelectorAll('[data-sec]')];
  tabs.forEach(a => a.onclick = e => { e.preventDefault(); document.getElementById(a.getAttribute('href').slice(1))?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' }); });
  if (tabs.length && 'IntersectionObserver' in window) {
    const io = new IntersectionObserver(es => es.forEach(en => {
      if (en.isIntersecting) tabs.forEach(t => t.classList.toggle('on', t.getAttribute('href') === '#' + en.target.id));
    }), { rootMargin: '-45% 0px -50% 0px' });
    tabs.forEach(t => { const el = document.getElementById(t.getAttribute('href').slice(1)); if (el) io.observe(el); });
    tabs[0].classList.add('on');
  }
}
function bindList() {
  document.querySelectorAll('[data-reset]').forEach(b => b.onclick = () => { state.league = 'all'; state.q = ''; route(); });
}

/* ---------- boot ---------- */
if (window.matchMedia) matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change', applyTheme);
if ('serviceWorker' in navigator && location.protocol === 'https:') { // not on localhost, so local edits show immediately
  navigator.serviceWorker.register('sw.js').catch(() => { /* offline support is optional */ });
}
route();
