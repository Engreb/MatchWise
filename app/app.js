/* Matchwise app: renders predictions produced by the Python engine (engine/). All
   probabilities come from data/*.json; this file only formats and displays them. */
'use strict';

const TZ = 'Europe/London';
const state = {
  histLeague: 'all', histView: 'all', view: 'blend', from: 'fixtures', fxDay: null, collapsed: new Set(),
  tableLeague: null, tableView: 'proj', predict: { league: 'epl', home: '', away: '' }, setQ: '',
};
const cache = {};

/* ---------- storage (per-device conveniences; everything works without it) ---------- */
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* private mode */ } },
  json(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
};
let favs = store.json('mw-fav', { teams: [], leagues: [] });
const saveFavs = () => store.set('mw-fav', JSON.stringify(favs));
const isFavTeam = (lg, t) => favs.teams.some(f => f.league === lg && f.name === t);
const isFavLeague = lg => favs.leagues.includes(lg);
function toggleFavTeam(lg, t) {
  favs.teams = isFavTeam(lg, t) ? favs.teams.filter(f => !(f.league === lg && f.name === t)) : [...favs.teams, { league: lg, name: t }];
  saveFavs();
}
function toggleFavLeague(lg) {
  favs.leagues = isFavLeague(lg) ? favs.leagues.filter(k => k !== lg) : [...favs.leagues, lg];
  saveFavs();
}
state.fxView = store.get('mw-fxview') === 'cards' ? 'cards' : 'compact';
state.fxMine = store.get('mw-fxmine') === '1';

/* ---------- theme ---------- */
const prefersDark = () => !!(window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches);
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
  document.querySelectorAll('[data-theme-label]').forEach(el => { el.textContent = themePref ? (dark ? 'Dark' : 'Light') : `Follow phone (${dark ? 'dark' : 'light'})`; });
}
function toggleTheme() {
  const next = isDark() ? 'light' : 'dark';
  themePref = next === (prefersDark() ? 'dark' : 'light') ? null : next; // matching the phone = follow the phone
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
function parsePayload(v) {
  const [lam, mu, H, D, A, o05, o15, o25, o35, o45, btts, ...grid] = v;
  const n = Math.round(Math.sqrt(grid.length));
  const cells = [];
  for (let x = 0; x < n; x++) for (let y = 0; y < n; y++) cells.push([x, y, grid[x * n + y]]);
  const top = cells.slice().sort((a, b) => b[2] - a[2]);
  return { lam, mu, H, D, A, over: { 0.5: o05, 1.5: o15, 2.5: o25, 3.5: o35, 4.5: o45 }, btts, grid, n, top };
}
async function pairFor(lg, home, away) {
  const P = await getJSON(`pairs-${lg}`);
  const v = P.pairs[`${home}|${away}`];
  return v ? parsePayload(v) : null;
}
let TABLES = {}, LEAGUE_NAMES = {}, TEAM_LG = {};
function indexTables(meta, T) {
  TABLES = T;
  LEAGUE_NAMES = Object.fromEntries(meta.leagues.map(l => [l.key, l.name]));
  TEAM_LG = {};
  for (const [k, t] of Object.entries(T)) for (const r of t.rows) TEAM_LG[r.team] = k;
}
function fixtures(meta) {
  return meta.fixtures.map((f, i) => {
    const model = f.model ? parsePayload(f.model) : null;
    let pr = f.blend ? parsePayload(f.blend) : model;
    const saved = f.saved_adj || f.saved;
    if (isStarted(f) && pr && saved) pr = { ...pr, H: saved[0], D: saved[1], A: saved[2] }; // exactly as saved before kick-off
    return { ...f, id: i, lgName: LEAGUE_NAMES[f.league], model, pr };
  });
}
// Kicked off but no result published yet (kept for a few days by the engine).
const isStarted = f => f.status === 'started' || (hasTime(f.kickoff) && dt(f.kickoff) <= Date.now());
const upcoming = meta => fixtures(meta).filter(f => f.status === 'started' || !hasTime(f.kickoff) || dt(f.kickoff) > Date.now() - 2 * 36e5);
const notStarted = meta => upcoming(meta).filter(f => !isStarted(f));
const leagueOrder = meta => [...meta.leagues.map(l => l.key).filter(isFavLeague), ...meta.leagues.map(l => l.key).filter(k => !isFavLeague(k))];

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
const ukDate = s => dt(s).toLocaleDateString('en-CA', { timeZone: TZ }); // YYYY-MM-DD in UK time
const topIdx = p => p.indexOf(Math.max(...p));
const ord = n => n + (['th', 'st', 'nd', 'rd'][(n % 100 > 10 && n % 100 < 14) ? 0 : (n % 10 < 4 ? n % 10 : 0)] || 'th');
const matchHref = (lg, h, a) => `#/match/${lg}/${encodeURIComponent(h)}/${encodeURIComponent(a)}`;
const teamHref = (lg, t) => `#/team/${lg}/${encodeURIComponent(t)}`;
const CC = { epl: 'ENG', championship: 'ENG', laliga: 'ESP', seriea: 'ITA', bundesliga: 'GER', ligue1: 'FRA', scotland: 'SCO', eredivisie: 'NED', portugal: 'POR' };
const cc = lg => `<span class="cc" aria-hidden="true">${CC[lg] || ''}</span>`;
function ago(s) {
  const m = Math.max(0, Math.round((Date.now() - new Date(s)) / 6e4));
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  return h < 48 ? `${h} h ago` : `${Math.round(h / 24)} days ago`;
}
function countdownParts(s) {
  const ms = dt(s) - Date.now();
  if (ms <= 0) return null;
  return [Math.floor(ms / 864e5), Math.floor(ms % 864e5 / 36e5), Math.floor(ms % 36e5 / 6e4)];
}
function countdownText(s) {
  if (!hasTime(s)) return '';
  const c = countdownParts(s);
  if (!c) return 'Kicked off';
  const [d, h, m] = c;
  return d ? `Kick-off in ${d} day${d > 1 ? 's' : ''}` : h ? `Kick-off in ${h} h` : `Kick-off in ${m} min`;
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
let HIST = null;
function formOf(team) {
  const lg = TEAM_LG[team];
  return (lg && TABLES[lg]?.form?.[team]) || [];
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
const STAR_PATH = '<path d="M12 3.5l2.6 5.2 5.7.8-4.1 4 1 5.7L12 16.5l-5.2 2.7 1-5.7-4.1-4 5.7-.8z"/>';
const I = {
  weekend: svg(STAR_PATH),
  fixtures: svg('<rect x="3" y="4" width="18" height="17" rx="2.5"/><path d="M3 9h18M8 2v4M16 2v4"/>'),
  tables: svg('<path d="M3 6h18M3 12h18M3 18h18M9 6v12"/>'),
  history: svg('<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/>'),
  more: svg('<circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/>'),
  predict: svg('<circle cx="12" cy="12" r="9"/><path d="M12 7l4 3-1.5 5h-5L8 10z"/>'),
  accuracy: svg('<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>'),
  settings: svg('<path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>'),
  back: svg('<path d="M15 6l-6 6 6 6"/>'),
  down: svg('<path d="M6 9l6 6 6-6"/>'),
  right: svg('<path d="M9 6l6 6-6 6"/>'),
  search: svg('<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>'),
  moon: svg('<path d="M20.5 13.2A8.5 8.5 0 1 1 10.8 3.5a6.6 6.6 0 0 0 9.7 9.7z"/>'),
  sun: svg('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>'),
  star: `<svg viewBox="0 0 24 24" width="15" height="15" fill="#F5B000" aria-hidden="true">${STAR_PATH}</svg>`,
  starOutline: svg(STAR_PATH),
  starFill: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round">${STAR_PATH}</svg>`,
};
const BRAND = `<span class="brand-mark" aria-hidden="true"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke-width="2.4"><circle cx="12" cy="12" r="9"/><path d="M12 7l4 3-1.5 5h-5L8 10z"/></svg></span>`;
const NAV_MOBILE = [['weekend', 'Weekend'], ['fixtures', 'Fixtures'], ['tables', 'Tables'], ['history', 'Season'], ['more', 'More']];
const NAV_DESKTOP = [['weekend', 'This weekend'], ['fixtures', 'Fixtures'], ['tables', 'Tables'], ['history', 'This season'], ['predict', 'Predict a match'], ['accuracy', 'Model accuracy'], ['settings', 'My teams & leagues']];
const topbar = () => `<div class="topbar"><span class="brand">${BRAND}Matchwise</span><button class="iconbtn" data-search-open aria-label="Search teams">${I.search}</button></div>`;
const statusPill = meta => meta.status === 'validated'
  ? `<a href="#/accuracy" class="pill ok"><span class="dot"></span>Tested on past seasons</a>`
  : `<a href="#/accuracy" class="pill warn"><span class="dot"></span>Not yet validated</a>`;
const errorBox = e => `<div class="card empty"><h3>Couldn't load predictions</h3><p>${esc(e.message || e)}</p><button class="btn" onclick="location.reload()">Try again</button></div>`;
const starBtn = (lg, t) => `<button class="starbtn" data-fav-team="${esc(lg)}|${esc(t)}" aria-pressed="${isFavTeam(lg, t)}" aria-label="${isFavTeam(lg, t) ? 'Remove from' : 'Add to'} my teams">${isFavTeam(lg, t) ? I.starFill : I.starOutline}</button>`;

/* ---------- routing ---------- */
async function route() {
  const parts = location.hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent);
  const page = parts[0] || 'weekend';
  const sub = { match: state.from, team: 'tables', sync: 'settings' }[page] || page;
  if (page !== 'settings') state.syncNote = '';
  const mobileActive = ['predict', 'accuracy', 'settings'].includes(sub) ? 'more' : sub;
  document.getElementById('nav').innerHTML = NAV_DESKTOP.map(([k, l]) => `<a href="#/${k}" ${k === sub ? 'aria-current="page"' : ''}>${I[k]}<span>${l}</span></a>`).join('');
  document.getElementById('tabbar').innerHTML = NAV_MOBILE.map(([k, l]) => `<a href="#/${k}" ${k === mobileActive ? 'aria-current="page"' : ''}><span class="ic">${I[k]}</span><span>${l}</span></a>`).join('');
  const main = document.getElementById('main');
  main.innerHTML = `<div class="content">${topbar()}<div class="skeleton"></div><div class="skeleton"></div></div>`;
  applyTheme();
  try {
    const meta = await getJSON('fixtures');
    indexTables(meta, await getJSON('tables'));
    renderFreshness(meta);
    const pages = {
      match: () => matchPage(meta, parts[1], parts[2], parts[3]),
      team: () => teamPage(meta, parts[1], parts[2]),
      fixtures: () => fixturesPage(meta), tables: () => tablesPage(meta, parts[1]),
      predict: () => predictPage(meta), history: () => historyPage(meta), accuracy: () => accuracyPage(meta),
      more: () => morePage(meta), settings: () => settingsPage(meta), weekend: () => weekendPage(meta),
      sync: () => syncPage(meta, parts[1]),
    };
    const titles = { sync: 'Add teams from a link', fixtures: 'Fixtures', tables: 'Tables', predict: 'Predict a match', history: 'This season', accuracy: 'Model accuracy', more: 'More', settings: 'My teams & leagues', weekend: 'This weekend' };
    if (['fixtures', 'predict', 'weekend'].includes(page)) state.from = page;
    const html = await (pages[page] || pages.weekend)();
    main.innerHTML = `<div class="page">${html}</div>`;
    document.title = `${page === 'match' ? `${parts[2]} vs ${parts[3]}` : page === 'team' ? parts[2] : titles[page] || 'This weekend'} · Matchwise`;
    bind();
    applyTheme();
    tickCountdowns();
  } catch (e) {
    console.error(e);
    main.innerHTML = `<div class="content">${topbar()}${errorBox(e)}</div>`;
    bind();
    applyTheme();
  }
}
window.addEventListener('hashchange', () => { closeSearch(); route().then(() => window.scrollTo(0, 0)); });

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

/* ---------- fixture card + compact row ---------- */
function fixtureCard(f, showLeague = true) {
  const star = t => isFavTeam(f.league, t) ? I.star : '';
  if (!f.pr) {
    return `<div class="card fx"><div class="fx-top"><span class="num">${cc(f.league)} ${fmtTime(f.kickoff)}${showLeague ? ' · ' + esc(f.lgName) : ''}</span><span class="pill">Unable to assess</span></div>
      <div class="team">${crest(f.home)}<span class="nm">${esc(f.home)}</span></div><div class="team">${crest(f.away)}<span class="nm">${esc(f.away)}</span></div></div>`;
  }
  const p = f.pr, probs = [p.H, p.D, p.A], v = verdict(p), started = isStarted(f);
  if (started) { v.label = 'Awaiting result'; v.cls = 'warn'; }
  return `<a class="card fx" href="${matchHref(f.league, f.home, f.away)}" aria-label="${esc(f.home)} versus ${esc(f.away)}: ${pct(p.H)} home, ${pct(p.D)} draw, ${pct(p.A)} away">
    <div class="fx-top"><span class="num">${cc(f.league)} ${fmtTime(f.kickoff)}${showLeague ? ' · ' + esc(f.lgName) : ''}</span><span class="pill ${v.cls}">${v.label}</span></div>
    <div class="team">${crest(f.home)}<span class="nm ${v.k === 0 ? 'fav' : ''}">${esc(f.home)}</span>${star(f.home)}${formHtml(f.home)}</div>
    <div class="team">${crest(f.away)}<span class="nm ${v.k === 2 ? 'fav' : ''}">${esc(f.away)}</span>${star(f.away)}${formHtml(f.away)}</div>
    ${pbar(probs, v.k)}${probsRow(probs, v.k)}
    <div class="fx-foot num">${started
      ? `<span>Kicked off ${fmtTime(f.kickoff)} · prediction saved ${f.saved_at ? fmtShort(f.saved_at) + ' ' + fmtTime(f.saved_at) : 'before kick-off'}</span>`
      : `<span>Expected goals <b>${p.lam.toFixed(1)}–${p.mu.toFixed(1)}</b> · Likely <b>${p.top[0][0]}–${p.top[0][1]}</b></span><span>${f.blend ? 'Odds-adjusted' : 'Model'}</span>`}</div>
  </a>`;
}
function compactRow(f) {
  if (!f.pr) return `<div class="crow"><span class="small muted num">${fmtTime(f.kickoff)}</span><span><div class="t">${crest(f.home)}${esc(f.home)}</div><div class="t">${crest(f.away)}${esc(f.away)}</div></span><span class="small muted">Unable to assess</span></div>`;
  const ps = [f.pr.H, f.pr.D, f.pr.A], k = topIdx(ps);
  const nm = (t, i) => `<div class="t ${k === i ? 'f' : ''}">${crest(t)}${esc(t)}${isFavTeam(f.league, t) ? ' ' + I.star : ''}</div>`;
  return `<a class="crow" href="${matchHref(f.league, f.home, f.away)}" aria-label="${esc(f.home)} versus ${esc(f.away)}: ${pct(ps[0])} home, ${pct(ps[1])} draw, ${pct(ps[2])} away">
    <span class="small muted num">${isStarted(f) ? '<span class="pill warn" style="padding:1px 5px;font-size:10px">Started</span>' : fmtTime(f.kickoff)}</span><span style="min-width:0">${nm(f.home, 0)}${nm(f.away, 2)}</span>
    <span><div class="p3 num">${ps.map((x, i) => i === k ? `<b>${pct(x)}</b>` : `<span>${pct(x)}</span>`).join('')}</div><div class="mini" aria-hidden="true">${ps.map((x, i) => `<i class="${i === k ? 'on' : ''}" style="flex:${Math.max(x, .02)}"></i>`).join('')}</div></span></a>`;
}

/* ---------- weekend ---------- */
function weekendWindow(fx) {
  const now = new Date();
  const london = new Date(now.toLocaleString('en-US', { timeZone: TZ }));
  const daysToMon = (8 - london.getDay()) % 7 || 7;
  const end = new Date(now.getTime() + daysToMon * 864e5); // through the coming Monday
  const inWin = fx.filter(f => dt(f.kickoff) <= end);
  return inWin.length ? inWin : fx;
}
async function weekendPage(meta) {
  const all = notStarted(meta).filter(f => f.pr);
  const fx = weekendWindow(all);
  const head = `${topbar()}<div class="page-head"><div><h1>This weekend</h1><p class="sub">${fx.length} matches across ${new Set(fx.map(f => f.league)).size} leagues${fx.length ? ` · ${fmtShort(fx[0].kickoff)} – ${fmtShort(fx[fx.length - 1].kickoff)}` : ''}</p></div>${statusPill(meta)}</div>`;
  if (!fx.length) return `<div class="content">${head}${staleNotice(meta)}<div class="card empty"><h3>No upcoming matches found</h3><p>You can still predict any match.</p><a class="btn primary" href="#/predict">Predict a match</a></div></div>`;

  // Your teams first: a spotlight on the next match, then the rest.
  const mine = all.filter(f => isFavTeam(f.league, f.home) || isFavTeam(f.league, f.away));
  let yours;
  if (mine.length) {
    const sp = mine[0], p = sp.pr, v = verdict(p);
    const club = teamMeta(isFavTeam(sp.league, sp.home) ? sp.home : sp.away).bg;
    const parts = hasTime(sp.kickoff) ? countdownParts(sp.kickoff) : null;
    yours = `<div class="eyebrow"><span>Next up for your teams</span><a href="#/settings">Edit</a></div>
      <a class="card spot" style="--club:${club};display:block;color:inherit" href="${matchHref(sp.league, sp.home, sp.away)}">
        <div class="fx-top"><span>${cc(sp.league)} ${esc(sp.lgName)} · ${fmtShort(sp.kickoff)} ${fmtTime(sp.kickoff)}</span><span class="pill ${v.cls}">${v.label}</span></div>
        <div class="vs"><div class="side">${crest(sp.home, 'lg')}<span class="nm">${esc(sp.home)}</span></div><div class="mid">vs</div><div class="side">${crest(sp.away, 'lg')}<span class="nm">${esc(sp.away)}</span></div></div>
        ${parts ? `<div class="count num" data-countdown="${esc(sp.kickoff)}" aria-label="${esc(countdownText(sp.kickoff))}"><span><b>${parts[0]}</b>days</span><span><b>${parts[1]}</b>hrs</span><span><b>${parts[2]}</b>min</span></div>` : ''}
        <div class="big3 num" style="margin-top:12px;padding-top:12px">${[['Home', p.H], ['Draw', p.D], ['Away', p.A]].map(([l, x], i) => `<div class="${i === v.k ? 'top' : ''}"><b style="font-size:26px">${pct(x)}</b><span>${l}</span></div>`).join('')}</div>
      </a>
      ${mine.length > 1 ? `<div class="fx-grid" style="margin-top:12px">${mine.slice(1, 5).map(f => fixtureCard(f)).join('')}</div>` : ''}`;
  } else {
    yours = `<div class="card card-pad" style="margin-bottom:14px;display:flex;gap:14px;align-items:center"><span class="starbtn" style="color:#F5B000">${I.starFill}</span>
      <div style="flex:1"><h3>Make it yours</h3><p class="small muted" style="margin:2px 0 0">Star your teams and leagues to see them first.</p></div><a class="btn" href="#/settings">Choose</a></div>`;
  }
  const myLeagues = favs.leagues.length ? `<div class="eyebrow"><span>My leagues</span></div>
    <div class="hscroll">${favs.leagues.map(k => `<a class="lchip" aria-pressed="true" href="#/tables/${k}">${cc(k)}${esc(LEAGUE_NAMES[k] || k)}</a>`).join('')}<a class="lchip" style="padding-left:12px" href="#/settings">+ Add</a></div>` : '';

  const R = meta.recent || { last7: { n: 0 }, season: { n: 0 } };
  const mx = f => Math.max(f.pr.H, f.pr.D, f.pr.A);
  const row = (f, val, muted) => `<a class="irow" href="${matchHref(f.league, f.home, f.away)}"><span class="pairc">${crest(f.home, 'sm')}${crest(f.away, 'sm')}</span><span class="t">${esc(f.home)} v ${esc(f.away)}</span><span class="v num" ${muted ? 'style="color:var(--text-2)"' : ''}>${val}</span></a>`;
  const strong = fx.slice().sort((a, b) => Math.max(b.pr.H, b.pr.A) - Math.max(a.pr.H, a.pr.A)).slice(0, 4);
  const close = fx.slice().sort((a, b) => mx(a) - mx(b)).slice(0, 4);
  const goals = fx.slice().sort((a, b) => (b.pr.lam + b.pr.mu) - (a.pr.lam + a.pr.mu)).slice(0, 4);
  const favName = f => f.pr.H >= f.pr.A ? f.home : f.away;
  return `<div class="content">${head}${staleNotice(meta)}${yours}${myLeagues}
    ${R.last7.n ? `<div class="eyebrow"><span>How it's doing</span><a href="#/history">Details</a></div><div class="card stats">
      <div class="stat"><div class="lbl">Last 7 days</div><div class="val num">${R.last7.hits}/${R.last7.n}</div><div class="meta">top picks right</div></div>
      <div class="stat"><div class="lbl">Hit rate</div><div class="val num">${pct(R.last7.hits / R.last7.n)}</div><div class="meta">${R.last7.mkt_n ? `Bookmakers ${pct(R.last7.mkt_hits / R.last7.mkt_n)}` : 'No odds to compare'}</div></div>
      <div class="stat"><div class="lbl">This season</div><div class="val num">${pct(R.season.hits / R.season.n)}</div><div class="meta">${R.season.n} matches</div></div>
      <div class="stat"><div class="lbl">Matches ahead</div><div class="val num">${fx.length}</div><div class="meta">${fx.filter(f => f.blend).length} odds-adjusted</div></div>
    </div>` : ''}
    <div class="overview">
      <div class="card insight"><h3>Strongest favourites</h3><p>Where the prediction is most confident</p>${strong.map(f => row(f, `${esc(teamMeta(favName(f)).code)} ${pct(Math.max(f.pr.H, f.pr.A))}`)).join('')}</div>
      <div class="card insight"><h3>Closest games</h3><p>Home · draw · away</p>${close.map(f => row(f, `${pct(f.pr.H)}·${pct(f.pr.D)}·${pct(f.pr.A)}`, true)).join('')}</div>
      <div class="card insight"><h3>Most goals expected</h3><p>Combined expected goals</p>${goals.map(f => row(f, (f.pr.lam + f.pr.mu).toFixed(1))).join('')}</div>
    </div>
    <div class="eyebrow" style="margin-top:22px"><span>Next kick-offs</span><a href="#/fixtures">All fixtures</a></div>
    <div class="fx-grid">${fx.slice(0, 4).map(f => fixtureCard(f)).join('')}</div>
  </div>`;
}

/* ---------- fixtures ---------- */
async function fixturesPage(meta) {
  const hasFavs = favs.teams.length || favs.leagues.length;
  const mineOnly = hasFavs && state.fxMine;
  const isMine = f => isFavLeague(f.league) || isFavTeam(f.league, f.home) || isFavTeam(f.league, f.away);
  const fx = upcoming(meta).filter(f => !mineOnly || isMine(f));
  const days = [...new Set(fx.map(f => ukDate(f.kickoff)))].sort();
  if (!state.fxDay || !days.includes(state.fxDay)) state.fxDay = days[0] || null;
  const head = `${topbar()}<div class="page-head"><div><h1>Fixtures</h1><p class="sub">Next 10 days · UK time</p></div>
    <div class="seg" role="group" aria-label="Layout"><button data-fxview="cards" aria-pressed="${state.fxView === 'cards'}">Cards</button><button data-fxview="compact" aria-pressed="${state.fxView === 'compact'}">Compact</button></div></div>`;
  if (!fx.length && mineOnly) return `<div class="content">${head}<button class="lchip" data-fxmine aria-pressed="true" style="margin:10px 0 12px;padding-left:10px">${I.star} My matches</button><div class="card empty"><h3>No matches for your teams or leagues</h3><p>None of them play in the next 10 days.</p></div></div>`;
  if (!fx.length) return `<div class="content">${head}${staleNotice(meta)}<div class="card empty"><h3>No upcoming fixtures found</h3><p>The schedule couldn't be loaded, or every match has already kicked off.</p><a class="btn primary" href="#/predict">Predict a match</a></div></div>`;
  const mineBtn = hasFavs ? `<button class="lchip" data-fxmine aria-pressed="${!!mineOnly}" style="margin:10px 0 0;padding-left:10px">${I.star} My matches${mineOnly ? '' : ` · ${upcoming(meta).filter(isMine).length}`}</button>` : '';
  const strip = `${mineBtn}<div class="days hscroll" role="group" aria-label="Choose a day">${days.map(d => {
    const x = new Date(d + 'T12:00:00Z');
    return `<button class="day-pill" data-day="${d}" aria-pressed="${d === state.fxDay}" style="min-width:54px"><small>${x.toLocaleDateString('en-GB', { weekday: 'short', timeZone: 'UTC' })}</small><b>${x.getUTCDate()}</b><i></i></button>`;
  }).join('')}</div>`;
  const dayFx = fx.filter(f => ukDate(f.kickoff) === state.fxDay);
  const groups = {};
  dayFx.forEach(f => (groups[f.league] ||= []).push(f));
  const order = leagueOrder(meta).filter(k => groups[k]);
  const body = order.map(k => {
    const open = !state.collapsed.has(k);
    const headBtn = `<button class="lg-head" data-collapse="${k}" aria-expanded="${open}">${cc(k)}${isFavLeague(k) ? I.star : ''}${esc(LEAGUE_NAMES[k])} <span class="n">${groups[k].length}</span><span class="chev">${open ? I.down : I.right}</span></button>`;
    if (state.fxView === 'compact') return `<div class="card" style="margin-top:10px;overflow:hidden">${headBtn}${open ? groups[k].map(compactRow).join('') : ''}</div>`;
    return `<div class="card" style="margin-top:10px;overflow:hidden">${headBtn}</div>${open ? `<div class="fx-grid" style="margin-top:10px">${groups[k].map(f => fixtureCard(f, false)).join('')}</div>` : ''}`;
  }).join('');
  return `<div class="content">${head}${staleNotice(meta)}${strip}
    <p class="small muted" style="margin:10px 2px 0">${fmtDay(state.fxDay)} · ${dayFx.length} match${dayFx.length === 1 ? '' : 'es'}${dayFx.some(f => f.blend) ? ' · bookmaker odds included where published' : ''}</p>${body}</div>`;
}

/* ---------- tables ---------- */
const heat = (v, c) => `<span class="prob num" style="background:color-mix(in srgb, ${c} ${Math.round(Math.min(1, v) * 80)}%, var(--surface-2));color:${v > .5 ? '#fff' : 'var(--text-2)'}">${v < .005 ? '–' : v > .995 ? '✓' : pct(v)}</span>`;
async function tablesPage(meta, key) {
  const order = leagueOrder(meta);
  const k = (key && TABLES[key]) ? key : (state.tableLeague && TABLES[state.tableLeague] ? state.tableLeague : order[0]);
  state.tableLeague = k;
  const T = TABLES[k], z = T.zones, rows = T.rows.slice().sort((a, b) => a.pos - b.pos);
  const zc = r => r.pos <= z.top[2] ? 'var(--accent)' : (z.playoff && r.pos >= z.playoff[1] && r.pos <= z.playoff[2]) ? 'color-mix(in srgb, var(--accent) 45%, transparent)' : r.pos >= z.rel[1] ? 'var(--loss)' : 'transparent';
  const fav = r => isFavTeam(k, r.team);
  const name = r => `<span class="team" style="padding:0;gap:7px">${crest(r.team, 'sm')}<span class="tm" style="font-weight:${fav(r) ? 650 : 500}">${esc(r.team)}</span>${fav(r) ? I.star : ''}</span>`;
  const proj = state.tableView === 'proj';
  const head = proj
    ? `<th>#</th><th style="text-align:left">Team</th><th class="r">Pts</th><th class="r">Proj</th><th class="r">Title</th><th class="r">${esc(z.top[0])}</th>${z.playoff ? `<th class="r hide-m">${esc(z.playoff[0])}</th>` : ''}<th class="r">Rel</th>`
    : `<th>#</th><th style="text-align:left">Team</th><th class="r">P</th><th class="r hide-m">W</th><th class="r hide-m">D</th><th class="r hide-m">L</th><th class="r">GD</th><th class="r">Pts</th><th class="r hide-m">Form</th>`;
  const body = rows.map(r => `<tr class="${fav(r) ? 'me' : ''}" data-href="${teamHref(k, r.team)}"><td class="pos num" style="--zc:${zc(r)}">${r.pos}</td><td><a href="${teamHref(k, r.team)}" style="color:inherit">${name(r)}</a></td>${proj
    ? `<td class="r num" style="font-weight:650">${r.pts}</td><td class="r num muted">${Math.round(r.xpts)}</td><td class="r">${heat(r.title, 'var(--accent)')}</td><td class="r">${heat(r.top, 'var(--accent)')}</td>${z.playoff ? `<td class="r hide-m">${heat(r.playoff, 'var(--accent)')}</td>` : ''}<td class="r">${heat(r.rel, 'var(--loss)')}</td>`
    : `<td class="r num">${r.p}</td><td class="r num hide-m">${r.w}</td><td class="r num hide-m">${r.d}</td><td class="r num hide-m">${r.l}</td><td class="r num">${r.gd > 0 ? '+' : ''}${r.gd}</td><td class="r num" style="font-weight:650">${r.pts}</td><td class="r hide-m">${formHtml(r.team)}</td>`}</tr>`).join('');
  return `<div class="content">${topbar()}<div class="page-head"><div><h1>Tables</h1><p class="sub">Live standings and how the season is likely to finish</p></div></div>
    <div class="hscroll" role="group" aria-label="Choose a league" style="margin-bottom:12px">${order.map(x => `<a class="lchip" href="#/tables/${x}" aria-pressed="${x === k}">${cc(x)}${isFavLeague(x) ? I.star : ''}${esc(LEAGUE_NAMES[x])}</a>`).join('')}</div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;gap:8px">
      <div class="seg" role="group" aria-label="Table view"><button data-tview="now" aria-pressed="${!proj}">Now</button><button data-tview="proj" aria-pressed="${proj}">Projected</button></div>
      <span class="small muted">${proj ? `${T.sims.toLocaleString('en-GB')} simulated seasons` : `${T.rows.reduce((s, r) => s + r.p, 0) / 2} games played`}</span></div>
    <div class="card" style="overflow-x:auto"><table class="tt"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>
    <div class="legend"><span><i style="background:var(--accent)"></i>${esc(z.top[0])}</span>${z.playoff ? `<span><i style="background:color-mix(in srgb, var(--accent) 45%, transparent)"></i>${esc(z.playoff[0])}</span>` : ''}<span><i style="background:var(--loss)"></i>${esc(z.rel[0])}</span>${proj ? '<span>Proj = projected final points</span>' : ''}</div>
    ${proj ? `<p class="small muted" style="margin:10px 2px 0">Each remaining fixture is simulated from the model's predictions, allowing for team strength to drift over the season. Ties are split by goal difference, then goals scored.${T.note ? ' ' + esc(T.note) : ''}</p>` : ''}
  </div>`;
}

/* ---------- team page ---------- */
async function teamPage(meta, lg, team) {
  const T = TABLES[lg];
  const r = T && T.rows.find(x => x.team === team);
  const back = `<a class="back" href="#/tables/${lg}">${I.back}${esc(LEAGUE_NAMES[lg] || 'Tables')}</a>`;
  if (!r) return `<div class="content">${back}<div class="card empty"><h3>Team not found</h3></div></div>`;
  const L = await league(lg);
  const tm = L.teams.find(t => t.name === team);
  const z = T.zones, n = T.rows.length;
  // Finishing-position chart
  const mx = Math.max(...r.dist), shown = r.dist.length;
  const dist = `<div class="dist" role="img" aria-label="Chance of each final position">${r.dist.map((v, i) => `<div title="${ord(i + 1)}: ${pct(v, 1)}">${shown <= 12 && v >= .03 ? `<em>${pct(v)}</em>` : ''}<i style="height:${Math.max(2, v / mx * 70)}px;opacity:${i + 1 <= z.top[2] ? 1 : i + 1 >= z.rel[1] ? .9 : .45};${i + 1 >= z.rel[1] ? 'background:var(--loss)' : ''}"></i><small>${shown > 20 && (i + 1) % 2 === 0 && i + 1 !== shown ? '' : i + 1}</small></div>`).join('')}</div>`;
  // Rating trend
  const tr = T.trend, vals = tr.teams[team] || [];
  const pts = vals.map((v, i) => [i, v]).filter(([, v]) => v != null);
  let chart = '';
  if (pts.length >= 2) {
    const ys = pts.map(p => p[1]), lo = Math.min(...ys) - .3, hi = Math.max(...ys) + .3, W = 326, H = 96;
    const sx = i => 32 + i * (W - 42) / Math.max(1, vals.length - 1), sy = v => H - 18 - (v - lo) / (hi - lo) * (H - 30);
    const line = pts.map(([i, v]) => `${sx(i)},${sy(v)}`).join(' ');
    const rank = i => 1 + Object.values(tr.teams).filter(v => v[i] != null && v[i] > vals[i]).length;
    chart = `<div style="display:flex;justify-content:space-between;align-items:center"><h3>Rating this season</h3><span class="pill accent">Rank ${rank(pts[pts.length - 1][0])} of ${n}</span></div>
      <p class="small muted" style="margin:2px 0 4px">Expected goal difference against an average team</p>
      <svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Rating trend this season">
        ${[.15, .5, .85].map(f => lo + f * (hi - lo)).map(v => `<line x1="32" x2="${W - 6}" y1="${sy(v)}" y2="${sy(v)}" stroke="var(--border)"/><text x="26" y="${sy(v) + 3.5}" font-size="9.5" text-anchor="end" fill="var(--text-3)">${v >= 0 ? '+' : ''}${v.toFixed(1)}</text>`).join('')}
        <path d="M${line.replaceAll(' ', ' L')} L${sx(pts[pts.length - 1][0])},${H - 18} L${sx(pts[0][0])},${H - 18}Z" fill="color-mix(in srgb, var(--accent) 12%, transparent)"/>
        <polyline fill="none" stroke="var(--accent)" stroke-width="2.4" stroke-linejoin="round" points="${line}"/>
        ${pts.map(([i, v], j) => `<circle cx="${sx(i)}" cy="${sy(v)}" r="${j === pts.length - 1 ? 4 : 2.5}" fill="${j === pts.length - 1 ? 'var(--surface)' : 'var(--accent)'}" stroke="var(--accent)" stroke-width="2"><title>${fmtDate(tr.dates[i])}: ${v >= 0 ? '+' : ''}${v.toFixed(2)}</title></circle>`).join('')}
        ${tr.dates.map((d, i) => (i % Math.ceil(tr.dates.length / 4) === 0 || i === tr.dates.length - 1) ? `<text x="${sx(i)}" y="${H - 3}" font-size="9.5" text-anchor="middle" fill="var(--text-3)">${fmtDate(d)}</text>` : '').join('')}
      </svg>`;
  }
  const next = upcoming(meta).filter(f => f.league === lg && (f.home === team || f.away === team)).slice(0, 3);
  let hist = [];
  try { HIST = HIST || (await getJSON('history')).matches; hist = HIST.filter(m => m.league === lg && (m.home === team || m.away === team)).slice(0, 6); } catch { /* optional */ }
  const news = lg === 'epl' ? await teamNewsList(team) : '';
  return `<div class="content narrow">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">${back.replace('class="back"', 'class="back" style="margin:0"')}${starBtn(lg, team)}</div>
    <div class="card spot" style="--club:${teamMeta(team).bg}">
      <div style="display:flex;align-items:center;gap:14px">${crest(team, 'lg')}<div style="min-width:0"><h2 style="font-size:22px">${esc(team)}</h2>
        <div class="small muted">${cc(lg)} ${esc(LEAGUE_NAMES[lg])} · ${ord(r.pos)} · ${r.pts} pts from ${r.p}</div><div style="margin-top:6px">${formHtml(team)}</div></div></div>
      <div class="keys num" style="grid-template-columns:repeat(3,minmax(0,1fr));margin-top:14px">
        <div class="key card"><div class="k">Title</div><div class="v">${r.title < .005 ? '<1%' : pct(r.title)}</div></div>
        <div class="key card"><div class="k">${esc(z.top[0])}</div><div class="v">${r.top < .005 ? '<1%' : pct(r.top)}</div></div>
        <div class="key card"><div class="k">${r.rel >= .1 ? 'Relegation' : 'Proj. points'}</div><div class="v">${r.rel >= .1 ? pct(r.rel) : Math.round(r.xpts)}</div></div>
      </div></div>
    <div class="card card-pad" style="margin-top:12px"><h3>Where they'll finish</h3><p class="small muted" style="margin:2px 0 0">Chance of each final position from ${T.sims.toLocaleString('en-GB')} simulated seasons · projected ${Math.round(r.xpts)} points</p>${dist}
      <p class="small" style="margin:8px 0 0">Most likely: ${r.dist.map((v, i) => [i + 1, v]).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([pos, v]) => `<b>${ord(pos)}</b> <span class="muted">${pct(v)}</span>`).join(' · ')}</p></div>
    ${chart ? `<div class="card card-pad" style="margin-top:12px">${chart}</div>` : ''}
    ${tm ? `<div class="card card-pad" style="margin-top:12px"><h3 style="margin-bottom:6px">Ratings</h3>
      <div class="kv"><span>Attack</span><span>${ord(tm.rank_attack)} of ${n}</span></div><div class="kv"><span>Defence</span><span>${ord(tm.rank_defence)} of ${n}</span></div>
      <div class="kv"><span>Vs an average team</span><span class="num">${tm.strength > 0 ? '+' : ''}${tm.strength.toFixed(2)} goals</span></div></div>` : ''}
    ${next.length ? `<div class="eyebrow"><span>Coming up</span></div><div class="fx-grid">${next.map(f => fixtureCard(f)).join('')}</div>` : ''}
    ${hist.length ? `<div class="eyebrow"><span>Recent results</span></div><div class="card" style="overflow:hidden">${hist.map(m => {
      const k = topIdx(m.pb || m.p), ok = k === m.outcome;
      return `<a class="crow" style="grid-template-columns:minmax(0,1fr) auto" href="${teamHref(lg, m.home === team ? m.away : m.home)}"><span style="min-width:0"><b class="num">${esc(m.home)} ${m.hg}–${m.ag} ${esc(m.away)}</b><div class="small muted">${fmtShort(m.date)} · predicted ${['home win', 'draw', 'away win'][k]} (${pct((m.pb || m.p)[k])})</div></span><span class="pill ${ok ? 'ok' : ''}">${ok ? 'Called it' : 'Missed'}</span></a>`;
    }).join('')}</div>` : ''}
    ${news}
  </div>`;
}

/* ---------- match ---------- */
async function matchPage(meta, lgKey, home, away) {
  const backTo = { predict: ['#/predict', 'Predict'], weekend: ['#/weekend', 'This weekend'] }[state.from] || ['#/fixtures', 'Fixtures'];
  const back = `<a class="back" href="${backTo[0]}">${I.back}${backTo[1]}</a>`;
  if (!LEAGUE_NAMES[lgKey]) return `<div class="content">${back}<div class="card empty"><h3>Unknown league</h3></div></div>`;
  const L = await league(lgKey);
  const fx = meta.fixtures.find(f => f.league === lgKey && f.home === home && f.away === away);
  const started = !!(fx && isStarted(fx));
  let modelP = fx && fx.model ? parsePayload(fx.model) : await pairFor(lgKey, home, away);
  if (started && modelP && fx.saved) modelP = { ...modelP, H: fx.saved[0], D: fx.saved[1], A: fx.saved[2] };
  if (!modelP) return `<div class="content">${back}<div class="card empty"><h3>Unable to assess this match</h3><p>One of the teams isn't in the current ${esc(L.name)} model.</p></div></div>`;
  const canBlend = !!(fx && (fx.blend || (started && fx.saved_adj)));
  const blended = canBlend && state.view === 'blend';
  let p = blended && fx.blend ? parsePayload(fx.blend) : modelP;
  if (blended && started && fx.saved_adj) p = { ...p, H: fx.saved_adj[0], D: fx.saved_adj[1], A: fx.saved_adj[2] };
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

  // Odds: better of Sky Bet / Coral highlighted, with model vs bookmaker bars.
  let odds = '';
  if (fx && fx.market && !started) {
    const mm = [modelP.H, modelP.D, modelP.A], lbl = [home, 'Draw', away];
    const books = [['Sky Bet', fx.odds_skybet], ['Coral', fx.odds_coral]].filter(([, o]) => o);
    const src = fx.odds_source === 'The Odds API'
      ? `${fx.odds_books} UK bookmakers${fx.odds_updated ? ` · updated ${ago(fx.odds_updated)}` : ''}`
      : 'average pre-match odds · football-data.co.uk';
    const cols = books.length ? books : [['Average', fx.odds_avg]];
    odds = `<section id="odds" class="card" style="overflow:hidden"><div class="card-head"><h3>${books.length > 1 ? 'Best prices' : 'Odds'}</h3><span class="small muted">${src}</span></div>
      <div class="oddsrow" style="border-top:0;padding-bottom:4px;grid-template-columns:minmax(0,1fr) repeat(${cols.length},56px)"><span class="small muted">Outcome</span>${cols.map(([b]) => `<span class="small muted" style="text-align:center">${b}</span>`).join('')}</div>
      ${[0, 1, 2].map(k => {
        const prices = cols.map(([, o]) => o ? o[k] : null), best = Math.max(...prices.filter(x => x));
        return `<div class="oddsrow" style="grid-template-columns:minmax(0,1fr) repeat(${cols.length},56px)"><span style="min-width:0"><b>${esc(lbl[k])}</b>
          <div class="cmp"><span>Model</span><span class="bar"><i style="width:${mm[k] * 100}%"></i></span><span class="num">${pct(mm[k])}</span></div>
          <div class="cmp"><span>Bookies</span><span class="bar bk"><i style="width:${fx.market[k] * 100}%"></i></span><span class="num">${pct(fx.market[k])}</span></div></span>
          ${prices.map(x => `<span class="price num ${cols.length > 1 && x === best && prices.filter(y => y === best).length === 1 ? 'best' : ''}">${x ? x.toFixed(2) : '—'}</span>`).join('')}</div>`;
      }).join('')}
      <p class="card-foot">${cols.length > 1 ? 'Green marks the better price. ' : ''}Bars compare the model's chance with the bookmakers' (margin removed). Bookmakers were more accurate than the model alone in testing, so a big gap more often means the model is missing news.</p></section>`;
  }
  const newsCard = await teamNews(lgKey, home, away);
  const atts = L.teams.map(x => x.attack), defs = L.teams.map(x => -x.defence);
  const sb = (val, arr) => `<div class="track"><i style="width:${Math.max(4, ((val - Math.min(...arr)) / ((Math.max(...arr) - Math.min(...arr)) || 1)) * 100)}%"></i></div>`;
  const cd = fx ? countdownText(fx.kickoff) : '';
  const side = t => `<a class="side" href="${teamHref(lgKey, t)}" style="color:inherit">${crest(t, 'lg')}<span class="nm">${esc(t)}</span>${formHtml(t)}</a>`;

  const startedNote = started ? `<div class="notice" role="status">Kicked off ${fmtShort(fx.kickoff)} ${fmtTime(fx.kickoff)}. This is the prediction saved before kick-off${fx.saved_at ? ` (${fmtShort(fx.saved_at)} ${fmtTime(fx.saved_at)})` : ''}. The result will appear under This season once it's published, usually within a day or two.</div>` : '';
  return `<div class="content">
    ${back}${startedNote}
    <div class="card hero">
      <div class="meta">${cc(lgKey)} ${esc(L.name)} · ${fx ? `${fmtDay(fx.kickoff)} · ${fmtTime(fx.kickoff)}` : 'Custom matchup'}</div>
      <div class="vs">${side(home)}<div class="mid">vs</div>${side(away)}</div>
      <span class="pill ${started ? 'warn' : 'accent'}">${started ? 'Awaiting result' : v.label + (cd ? ' · ' + cd : '')}</span>
      <div class="big3 num">${[[home + ' win', p.H], ['Draw', p.D], [away + ' win', p.A]].map(([l, val], i) => `<div class="${i === v.k ? 'top' : ''}"><b>${pct(val)}</b><span>${esc(l)}</span><small>Fair odds ${fair(val)}</small></div>`).join('')}</div>
      ${pbar(probs, v.k)}
    </div>
    <nav class="sectabs" aria-label="Sections"><a href="#prediction" data-sec>Prediction</a>${odds ? '<a href="#odds" data-sec>Odds</a>' : ''}<a href="#goals" data-sec>Goals</a><a href="#scores" data-sec>Scores</a><a href="#news" data-sec>Team news</a><a href="#why" data-sec>Why</a></nav>
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
      ${odds}
      <section id="goals" class="card" style="${odds ? 'margin-top:12px' : ''}"><div class="card-head"><h3>Markets</h3><span class="small muted">Fair odds = 1 ÷ probability</span></div>
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
        ${[th, ta].map(tm => `<a class="news-team" style="margin-top:10px;color:inherit" href="${teamHref(lgKey, tm.name)}">${crest(tm.name, 'sm')}${esc(tm.name)}</a>
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
function newsItems(list) {
  return list.length ? `<ul class="news-list">${list.map(x => `<li>
    <div class="line"><span>${esc(x.player)} <span class="small muted">${esc(x.position)}</span>${x.regular ? ' <span class="pill accent" title="Started at least half of this season\'s matches">Regular</span>' : ''}</span>
      <span class="pill ${x.status === 'doubtful' ? 'warn' : 'bad'}">${x.status === 'doubtful' && x.chance != null ? `${x.chance}%` : x.status[0].toUpperCase() + x.status.slice(1)}</span></div>
    ${x.news ? `<div class="small muted">${esc(x.news)}</div>` : ''}</li>`).join('')}</ul>` : '<p class="small muted" style="margin:0">No reported absences.</p>';
}
async function teamNews(lgKey, home, away) {
  if (lgKey !== 'epl') return `<div class="card card-pad"><h3 style="margin-bottom:4px">Team news</h3><p class="small muted" style="margin:0">Injury and suspension news is only available for the Premier League at the moment.</p></div>`;
  let N;
  try { N = await getJSON('news-epl'); } catch { return ''; }
  const col = team => `<div><div class="news-team">${crest(team, 'sm')}${esc(team)}</div>${newsItems(N.teams[team] || [])}</div>`;
  return `<div class="card"><div class="card-head"><h3>Team news</h3><span class="small muted">Updated ${fmtDate(N.fetched_at)} · Fantasy Premier League</span></div>
    <div class="card-pad grid-2">${col(home)}${col(away)}</div>
    <p class="card-foot">Shown for context. Bookmaker odds usually reflect it, so the odds-adjusted view partly accounts for it.</p></div>`;
}
async function teamNewsList(team) {
  try {
    const N = await getJSON('news-epl');
    return `<div class="eyebrow"><span>Team news</span><span style="text-transform:none;letter-spacing:0">Updated ${fmtDate(N.fetched_at)}</span></div><div class="card card-pad">${newsItems(N.teams[team] || [])}</div>`;
  } catch { return ''; }
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
      ${L.teams.map((t, i) => `<tr><td class="num muted">${i + 1}</td><td><a class="team" style="padding:0;color:inherit" href="${teamHref(s.league, t.name)}">${crest(t.name, 'sm')}<span>${esc(t.name)}</span>${t.limited ? '<span class="pill warn">Limited data</span>' : ''}</a></td><td class="r num">${ord(t.rank_attack)}</td><td class="r num">${ord(t.rank_defence)}</td><td class="r num hide-m">${t.strength > 0 ? '+' : ''}${t.strength.toFixed(2)} goals</td></tr>`).join('')}
      </tbody></table></div>
  </div>`;
}

/* ---------- this season ---------- */
const brierOf = (p, o) => p.reduce((a, v, k) => a + (v - (k === o ? 1 : 0)) ** 2, 0);
function histToolbar(meta) {
  const chips = [['all', 'All'], ...meta.leagues.map(l => [l.key, l.name])]
    .map(([k, l]) => `<button class="chip" data-hl="${k}" aria-pressed="${state.histLeague === k}">${esc(l)}</button>`).join('');
  return `<div class="toggle" role="group" aria-label="Which predictions">
      <button data-hv="all" aria-pressed="${state.histView !== 'saved'}">All matches</button>
      <button data-hv="saved" aria-pressed="${state.histView === 'saved'}">Saved before kick-off</button></div>
    <div class="toolbar"><div class="chips" role="group" aria-label="Filter by league">${chips}</div></div>`;
}
function savedView(meta, H) {
  const rows = H.matches.filter(m => m.source === 'saved' && (state.histLeague === 'all' || m.league === state.histLeague));
  const head = `${topbar()}<div class="page-head"><div><h1>This season</h1><p class="sub">Predictions exactly as this app saved them before kick-off, settled against the final score.</p></div></div>${histToolbar(meta)}`;
  if (!rows.length) {
    const next = meta.fixtures.map(f => f.kickoff).filter(k => hasTime(k) && dt(k) > Date.now()).sort()[0];
    return `<div class="content">${head}<div class="card empty"><h3>Nothing settled yet</h3>
      <p>The app started saving predictions on 14 October. They'll appear here once those matches are played${next ? `, starting ${fmtShort(next)}` : ''}.</p></div></div>`;
  }
  const adj = rows.filter(m => m.pb), mk = rows.filter(m => m.pmkt || m.mkt);
  const rate = (arr, f) => arr.length ? pct(arr.filter(m => topIdx(f(m)) === m.outcome).length / arr.length) : '—';
  const br = (arr, f) => arr.length ? (arr.reduce((s, m) => s + brierOf(f(m), m.outcome), 0) / arr.length).toFixed(3) : '—';
  const cell = p => { const t = topIdx(p); return `${esc(['H', 'D', 'A'][t])} <span class="small muted num">${pct(p[t])}</span>`; };
  return `<div class="content">${head}
    <div class="card stats">
      <div class="stat"><div class="lbl">Settled</div><div class="val num">${rows.length}</div><div class="meta">${adj.length} with odds-adjusted</div></div>
      <div class="stat"><div class="lbl">Model only</div><div class="val num">${rate(rows, m => m.p)}</div><div class="meta">Brier ${br(rows, m => m.p)}</div></div>
      <div class="stat"><div class="lbl">Odds-adjusted</div><div class="val num">${rate(adj, m => m.pb)}</div><div class="meta">Brier ${br(adj, m => m.pb)}</div></div>
      <div class="stat"><div class="lbl">Bookmakers</div><div class="val num">${rate(mk, m => m.pmkt || m.mkt)}</div><div class="meta">Brier ${br(mk, m => m.pmkt || m.mkt)}</div></div>
    </div>
    <div class="card"><table><thead><tr><th>Result</th><th class="r">Model</th><th class="r">Odds-adj.</th><th class="r hide-m">Saved</th><th class="r">Outcome</th></tr></thead><tbody>
      ${rows.map(m => {
        const shown = m.pb || m.p, ok = topIdx(shown) === m.outcome;
        return `<tr><td><div class="team" style="padding:0">${crest(m.home, 'sm')}<span style="font-weight:600" class="num">${esc(m.home)} ${m.hg}–${m.ag} ${esc(m.away)}</span></div>
            <div class="small muted" style="margin-left:38px">${esc(LEAGUE_NAMES[m.league])} · ${fmtShort(m.date)}</div></td>
          <td class="r">${cell(m.p)}</td><td class="r">${m.pb ? cell(m.pb) : '<span class="muted">—</span>'}</td>
          <td class="r small muted hide-m">${fmtDate(m.saved_at)}${m.saves > 1 ? ` · ${m.saves} saves` : ''}</td>
          <td class="r">${ok ? '<span class="pill ok">Correct</span>' : '<span class="pill">Missed</span>'}</td></tr>`;
      }).join('')}
    </tbody></table></div>
    <p class="small muted" style="margin-top:12px">H, D and A are the home win, draw and away win picks with their chance. "Outcome" judges the odds-adjusted pick when there was one, otherwise the model's. The latest save before kick-off counts.</p>
  </div>`;
}
function seasonChart(rows) {
  const weeks = {};
  rows.slice().reverse().forEach(m => { const d = new Date(m.date + 'T12:00:00Z'); const w = new Date(d - ((d.getUTCDay() + 6) % 7) * 864e5).toISOString().slice(0, 10); (weeks[w] ||= []).push(m); });
  let a = 0, an = 0, b = 0, bn = 0;
  const ser = Object.entries(weeks).map(([d, ms]) => { ms.forEach(m => { an++; if (topIdx(m.p) === m.outcome) a++; if (m.mkt) { bn++; if (topIdx(m.mkt) === m.outcome) b++; } }); return [d, a / an, bn ? b / bn : null, an]; }).filter(s => s[3] >= 10);
  if (ser.length < 2) return '';
  const vals = ser.flatMap(s => [s[1], s[2]]).filter(v => v != null), lo = Math.min(.4, Math.floor(Math.min(...vals) * 20) / 20), hi = Math.max(.65, Math.ceil(Math.max(...vals) * 20) / 20);
  const W = 380, H = 170, x = i => 36 + i * (W - 46) / (ser.length - 1), y = v => H - 22 - (v - lo) / (hi - lo) * (H - 34);
  const ticks = [lo, (lo + hi) / 2, hi];
  return `<div class="card card-pad"><h3>Hit rate over the season</h3><p class="small muted" style="margin:2px 0 6px">Cumulative top-pick accuracy, by week</p>
    <svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Cumulative hit rate by week: model ${pct(ser[ser.length - 1][1])}, bookmakers ${ser[ser.length - 1][2] != null ? pct(ser[ser.length - 1][2]) : 'n/a'}">
      ${ticks.map(v => `<line x1="36" x2="${W - 6}" y1="${y(v)}" y2="${y(v)}" stroke="var(--border)"/><text x="30" y="${y(v) + 3.5}" font-size="10" text-anchor="end" fill="var(--text-3)">${Math.round(v * 100)}%</text>`).join('')}
      <polyline fill="none" stroke="var(--text-3)" stroke-width="2" stroke-dasharray="4 3" points="${ser.filter(s => s[2] != null).map((s, i) => x(ser.indexOf(s)) + ',' + y(s[2])).join(' ')}"/>
      <polyline fill="none" stroke="var(--accent)" stroke-width="2.6" stroke-linejoin="round" points="${ser.map((s, i) => x(i) + ',' + y(s[1])).join(' ')}"/>
      ${ser.map((s, i) => i % Math.ceil(ser.length / 6) === 0 || i === ser.length - 1 ? `<text x="${x(i)}" y="${H - 5}" font-size="10" text-anchor="middle" fill="var(--text-3)">${fmtDate(s[0])}</text>` : '').join('')}
    </svg><div class="legend"><span><i style="background:var(--accent);height:3px"></i>Model</span><span><i style="background:var(--text-3);height:3px"></i>Bookmakers</span></div></div>`;
}
async function historyPage(meta) {
  const H = await getJSON('history');
  if (state.histView === 'saved') return savedView(meta, H);
  const rows = H.matches.filter(m => state.histLeague === 'all' || m.league === state.histLeague);
  const n = rows.length;
  const hits = rows.filter(m => topIdx(m.p) === m.outcome).length;
  const brier = rows.reduce((s, m) => s + brierOf(m.p, m.outcome), 0) / (n || 1);
  const withMkt = rows.filter(m => m.mkt);
  const mBrier = withMkt.reduce((s, m) => s + brierOf(m.mkt, m.outcome), 0) / (withMkt.length || 1);
  const mHits = withMkt.filter(m => topIdx(m.mkt) === m.outcome).length;
  const saved = rows.filter(r => r.source === 'saved').length;
  const byLeague = state.histLeague === 'all' ? meta.leagues.map(l => {
    const ms = H.matches.filter(m => m.league === l.key), mk = ms.filter(m => m.mkt);
    return [l.key, l.name, ms.length ? ms.filter(m => topIdx(m.p) === m.outcome).length / ms.length : 0, mk.length ? mk.filter(m => topIdx(m.mkt) === m.outcome).length / mk.length : null, ms.length];
  }).filter(x => x[4]).sort((a, b) => b[2] - a[2]) : [];
  return `<div class="content">${topbar()}
    <div class="page-head"><div><h1>This season</h1><p class="sub">Every ${H.season.slice(0, 2)}/${H.season.slice(2)} match so far, with the prediction made using only earlier results.</p></div></div>
    ${histToolbar(meta)}
    ${n ? `<div class="card stats">
      <div class="stat"><div class="lbl">Matches</div><div class="val num">${n}</div><div class="meta">${saved} saved before kick-off</div></div>
      <div class="stat"><div class="lbl">Top pick right</div><div class="val num">${pct(hits / n)}</div><div class="meta">Bookmakers ${withMkt.length ? pct(mHits / withMkt.length) : '—'}</div></div>
      <div class="stat"><div class="lbl">Brier score</div><div class="val num">${brier.toFixed(3)}</div><div class="meta">Bookmakers ${withMkt.length ? mBrier.toFixed(3) : '—'}</div></div>
      <div class="stat"><div class="lbl">Guessing</div><div class="val num">0.667</div><div class="meta">Brier for ⅓ each</div></div>
    </div>
    <div class="${byLeague.length ? 'grid-2' : ''}" style="margin-bottom:12px">${seasonChart(rows)}
      ${byLeague.length ? `<div class="card card-pad"><h3 style="margin-bottom:6px">By league</h3>${byLeague.map(([k, nm, h, bh]) => `<div class="lgbar"><span>${cc(k)} ${esc(nm.replace('Scottish ', ''))}</span><span class="b"><i style="width:${h * 100}%"></i>${bh != null ? `<u style="left:${bh * 100}%"></u>` : ''}</span><span class="num" style="text-align:right;font-weight:600">${pct(h)}</span></div>`).join('')}
        <div class="legend"><span><i style="background:var(--accent)"></i>Model</span><span><i style="background:var(--text-2);width:2px"></i>Bookmakers</span></div></div>` : ''}</div>
    <div class="card"><table><thead><tr><th class="hide-m">Date</th><th>Result</th><th class="hide-m">Model's pick</th><th class="r hide-m">Chance given</th><th class="r">Outcome</th></tr></thead><tbody>
      ${rows.slice(0, 200).map(m => {
        const t = topIdx(m.p), ok = t === m.outcome, pick = [m.home, 'Draw', m.away][t];
        return `<tr><td class="num hide-m muted">${fmtShort(m.date)}</td>
          <td><div class="team" style="padding:0">${crest(m.home, 'sm')}<span style="font-weight:600" class="num">${esc(m.home)} ${m.hg}–${m.ag} ${esc(m.away)}</span></div>
            <div class="small muted" style="margin-left:38px">${esc(LEAGUE_NAMES[m.league])} · ${m.source === 'saved' ? 'Saved before kick-off' : 'Replayed'}</div></td>
          <td class="hide-m">${esc(pick)} <span class="small muted num">${pct(m.p[t])}</span></td>
          <td class="r num hide-m">${pct(m.p[m.outcome])}</td>
          <td class="r">${ok ? '<span class="pill ok">Correct</span>' : '<span class="pill">Missed</span>'}</td></tr>`;
      }).join('')}
    </tbody></table></div>
    <p class="small muted" style="margin-top:12px">Brier score measures how good the probabilities were (lower is better). "Replayed" means the prediction was recreated using only results before that week; "saved" means it was stored before kick-off.</p>`
    : `<div class="card empty"><h3>No matches yet</h3><p>Nothing has been played in this league this season.</p></div>`}
  </div>`;
}

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
      <li>Promoted teams start from the average rating of the teams they replaced.${A.link_test && A.link_test.E0 ? ` Rating Premier League newcomers from their Championship results instead was tested and ${A.link_test.E0.adopt ? 'adopted' : 'not adopted: it was no better'} (log loss change ${A.link_test.E0.test.all.mean >= 0 ? '+' : ''}${A.link_test.E0.test.all.mean.toFixed(4)} on the test seasons).` : ''}</li>
      <li>Accuracy differs by league: more even leagues such as the Championship are harder for everyone, bookmakers included.</li>
    </ul></div></details>
  </div>`;
}


/* ---------- more ---------- */
async function morePage(meta) {
  const item = (href, icon, t, s) => `<a class="setting-row" href="${href}" style="padding:14px"><span class="iconbtn" style="pointer-events:none">${icon}</span><span class="grow"><b>${t}</b><div class="small muted">${s}</div></span><span class="muted" style="width:18px">${I.right}</span></a>`;
  return `<div class="content narrow">${topbar()}<div class="page-head"><div><h1>More</h1></div></div>
    <div class="card" style="overflow:hidden">
      ${item('#/predict', I.predict, 'Predict a match', 'Any two teams in the same league')}
      ${item('#/settings', I.weekend, 'My teams & leagues', `${favs.teams.length} teams · ${favs.leagues.length} leagues starred`)}
      ${item('#/accuracy', I.accuracy, 'Model accuracy', 'How the predictions are tested')}
      <div class="setting-row" style="padding:14px"><span class="iconbtn" style="pointer-events:none">${isDark() ? I.moon : I.sun}</span><span class="grow"><b>Appearance</b><div class="small muted" data-theme-label></div></span><button class="iconbtn" data-theme-toggle></button></div>
    </div>
    <p class="small muted" style="margin:14px 2px">Updated ${fmtDate(meta.generated_at)}. Results and odds: football-data.co.uk and The Odds API. Schedules: fixturedownload.com. Team news: Fantasy Premier League.</p>
  </div>`;
}

/* ---------- my teams & leagues ---------- */
function myTeamCard(meta, f, i) {
  const r = TABLES[f.league]?.rows.find(x => x.team === f.name);
  const nx = upcoming(meta).find(x => x.league === f.league && (x.home === f.name || x.away === f.name) && x.pr);
  let next = '<span class="muted">No fixture in the next 10 days</span>';
  if (nx) {
    const home = nx.home === f.name, win = home ? nx.pr.H : nx.pr.A;
    next = `Next: ${home ? 'v' : '@'} ${esc(home ? nx.away : nx.home)} · ${fmtShort(nx.kickoff)} ${fmtTime(nx.kickoff)} · <b class="num">${pct(win)}</b> to win`;
  }
  return `<div class="card myteam">
    <a class="mt-main" href="${teamHref(f.league, f.name)}">${crest(f.name)}<span style="min-width:0">
      <b>${esc(f.name)}</b><div class="small muted">${cc(f.league)} ${esc(LEAGUE_NAMES[f.league])}${r ? ` · ${ord(r.pos)} · ${r.pts} pts` : ''}</div>
      <div class="mt-next">${next}</div></span></a>
    <div class="mt-actions">${i > 0 ? `<button class="iconbtn" data-fav-move="${i}" aria-label="Move ${esc(f.name)} up">${svg('<path d="M12 19V5M5 12l7-7 7 7"/>')}</button>` : ''}${starBtn(f.league, f.name)}</div></div>`;
}
const tile = (lg, t, showLeague) => `<button class="tile" data-fav-team="${esc(lg)}|${esc(t)}" aria-pressed="${isFavTeam(lg, t)}" aria-label="${isFavTeam(lg, t) ? 'Remove' : 'Add'} ${esc(t)}">${crest(t)}<span class="n">${esc(t)}${showLeague ? `<small class="muted" style="display:block;font-weight:400">${esc(LEAGUE_NAMES[lg])}</small>` : ''}</span>${isFavTeam(lg, t) ? `<span class="st">${I.starFill}</span>` : ''}</button>`;
function encodeFavs() {
  const json = JSON.stringify({ t: favs.teams.map(f => [f.league, f.name]), l: favs.leagues });
  return btoa(unescape(encodeURIComponent(json))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
function decodeFavs(code) {
  try {
    const json = decodeURIComponent(escape(atob(code.replace(/-/g, '+').replace(/_/g, '/'))));
    const o = JSON.parse(json);
    return {
      teams: (o.t || []).filter(x => Array.isArray(x) && TABLES[x[0]]?.rows.some(r => r.team === x[1])).map(([league, name]) => ({ league, name })),
      leagues: (o.l || []).filter(k => TABLES[k]),
    };
  } catch { return null; }
}
const syncLink = () => `${location.origin}${location.pathname}#/sync/${encodeFavs()}`;
async function settingsPage(meta) {
  const q = state.setQ.trim().toLowerCase();
  const order = leagueOrder(meta);
  if (!state.setLeague || !TABLES[state.setLeague]) state.setLeague = favs.leagues[0] || order[0];
  const mine = favs.teams.filter(f => TABLES[f.league]);
  let picker;
  if (q) {
    const hits = Object.entries(TABLES).flatMap(([k, t]) => t.rows.map(r => [k, r.team])).filter(([, t]) => t.toLowerCase().includes(q)).sort((a, b) => a[1].localeCompare(b[1]));
    picker = hits.length ? `<div class="tiles">${hits.slice(0, 40).map(([k, t]) => tile(k, t, true)).join('')}</div>` : '<div class="card empty"><h3>No teams match</h3></div>';
  } else {
    const teams = TABLES[state.setLeague].rows.map(r => r.team).sort((a, b) => a.localeCompare(b));
    picker = `<div class="hscroll" role="group" aria-label="Choose a league" style="margin-bottom:10px">${order.map(k => `<button class="lchip" data-setlg="${k}" aria-pressed="${k === state.setLeague}">${cc(k)}${esc(LEAGUE_NAMES[k])}</button>`).join('')}</div>
      <div class="tiles">${teams.map(t => tile(state.setLeague, t)).join('')}</div>`;
  }
  const n = mine.length + favs.leagues.length, note = state.syncNote;
  state.syncNote = ''; // show the confirmation once
  return `<div class="content narrow">${topbar()}
    <div class="page-head"><div><h1>My teams & leagues</h1><p class="sub">Starred teams and leagues come first across the app: the weekend spotlight, fixtures, tables and search.</p></div></div>
    ${note ? `<div class="notice" role="status" style="background:var(--win-soft);border-color:transparent;color:var(--win)">${esc(note)}</div>` : ''}
    <div class="eyebrow"><span>Your teams${mine.length ? ` · ${mine.length}` : ''}</span></div>
    ${mine.length ? mine.map((f, i) => myTeamCard(meta, f, i)).join('') : '<div class="card card-pad"><p class="small muted" style="margin:0">No teams yet. Tap any team below to star it.</p></div>'}
    <div class="eyebrow"><span>Add teams</span></div>
    <label class="search" style="margin:0 0 10px;width:100%">${I.search}<input type="search" placeholder="Search all teams" aria-label="Search all teams" value="${esc(state.setQ)}" data-setq style="width:100%"></label>
    ${picker}
    <div class="eyebrow"><span>Your leagues</span></div>
    <div class="tiles">${meta.leagues.map(l => `<button class="tile" data-fav-league="${l.key}" aria-pressed="${isFavLeague(l.key)}" aria-label="${isFavLeague(l.key) ? 'Remove' : 'Add'} ${esc(l.name)}">${cc(l.key)}<span class="n">${esc(l.name)}</span>${isFavLeague(l.key) ? `<span class="st">${I.starFill}</span>` : ''}</button>`).join('')}</div>
    <div class="eyebrow"><span>Use on another device</span></div>
    <div class="card card-pad">
      <p class="small" style="margin:0 0 10px;color:var(--text-2)">Your stars are saved on this device only. Open this link on your phone or computer to copy them there. It contains only team and league names.</p>
      ${n ? `<div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn primary" data-sync-share>${navigator.share ? 'Share link' : 'Copy link'}</button>${navigator.share ? '<button class="btn" data-sync-copy>Copy link</button>' : ''}</div>
        <p class="small muted" data-sync-status style="margin:8px 0 0" role="status"></p>` : '<p class="small muted" style="margin:0">Star a team or league first.</p>'}
    </div>
  </div>`;
}
async function syncPage(meta, code) {
  const got = decodeFavs(code || '');
  const back = `<a class="back" href="#/settings">${I.back}My teams & leagues</a>`;
  if (!got || (!got.teams.length && !got.leagues.length)) return `<div class="content narrow">${back}<div class="card empty"><h3>This link doesn't contain any teams</h3><p>It may have been cut short when it was copied.</p></div></div>`;
  return `<div class="content narrow">${back}<div class="page-head"><div><h1>Add these to this device?</h1><p class="sub">From a Matchwise sync link.</p></div></div>
    ${got.teams.length ? `<div class="eyebrow"><span>Teams · ${got.teams.length}</span></div><div class="hscroll" style="flex-wrap:wrap">${got.teams.map(f => `<span class="lchip">${crest(f.name, 'sm')}${esc(f.name)}</span>`).join('')}</div>` : ''}
    ${got.leagues.length ? `<div class="eyebrow"><span>Leagues · ${got.leagues.length}</span></div><div class="hscroll" style="flex-wrap:wrap">${got.leagues.map(k => `<span class="lchip">${cc(k)}${esc(LEAGUE_NAMES[k])}</span>`).join('')}</div>` : ''}
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:18px">
      <button class="btn primary" data-sync-apply="merge" data-code="${esc(code)}">Add to mine</button>
      ${favs.teams.length || favs.leagues.length ? `<button class="btn" data-sync-apply="replace" data-code="${esc(code)}">Replace mine</button>` : ''}
      <a class="btn" href="#/settings">Cancel</a></div>
  </div>`;
}

/* ---------- search ---------- */
let recent = store.json('mw-recent', []);
function searchResults(q) {
  q = q.trim().toLowerCase();
  if (!q) {
    return recent.length ? `<div class="eyebrow"><span>Recent</span></div><div class="recent">${recent.map(r => `<a href="${teamHref(r.league, r.name)}" data-recent="${esc(r.league)}|${esc(r.name)}" style="font-size:13px;padding:6px 11px;border-radius:999px;background:var(--surface-2);color:var(--text-2)">${esc(r.name)}</a>`).join('')}</div>`
      : '<p class="small muted" style="margin:14px 2px">Search any of the teams in the nine leagues.</p>';
  }
  const teams = Object.entries(TABLES).flatMap(([k, t]) => t.rows.map(r => ({ league: k, name: r.team })))
    .filter(t => t.name.toLowerCase().includes(q))
    .sort((a, b) => (b.name.toLowerCase().startsWith(q) - a.name.toLowerCase().startsWith(q)) || a.name.localeCompare(b.name)).slice(0, 8);
  const lgs = Object.entries(LEAGUE_NAMES).filter(([, n]) => n.toLowerCase().includes(q));
  const mark = n => { const i = n.toLowerCase().indexOf(q); return i < 0 ? esc(n) : esc(n.slice(0, i)) + `<mark>${esc(n.slice(i, i + q.length))}</mark>` + esc(n.slice(i + q.length)); };
  const meta = cache._meta;
  const nextOf = (lg, t) => meta ? upcoming(meta).find(f => f.league === lg && (f.home === t || f.away === t)) : null;
  return (teams.length ? `<div class="eyebrow"><span>Teams</span></div><div class="card" style="padding:0 12px">${teams.map(t => {
    const nf = nextOf(t.league, t.name);
    return `<a class="sres" href="${teamHref(t.league, t.name)}" data-recent="${esc(t.league)}|${esc(t.name)}">${crest(t.name, 'sm')}<span style="flex:1;min-width:0"><b>${mark(t.name)}</b><div class="small muted">${cc(t.league)} ${esc(LEAGUE_NAMES[t.league])}${nf ? ` · next ${nf.home === t.name ? 'v ' + esc(nf.away) : '@ ' + esc(nf.home)}, ${fmtShort(nf.kickoff)}` : ''}</div></span><span class="muted" style="width:16px">${I.right}</span></a>`;
  }).join('')}</div>` : '') +
    (lgs.length ? `<div class="eyebrow"><span>Leagues</span></div><div class="card" style="padding:0 12px">${lgs.map(([k, n]) => `<a class="sres" href="#/tables/${k}">${cc(k)}<span style="flex:1"><b>${mark(n)}</b><div class="small muted">Table and projections</div></span><span class="muted" style="width:16px">${I.right}</span></a>`).join('')}</div>` : '') +
    (!teams.length && !lgs.length ? '<p class="small muted" style="margin:14px 2px">No teams or leagues match.</p>' : '');
}
function openSearch() {
  const ov = document.getElementById('search');
  ov.classList.add('open');
  ov.innerHTML = `<div class="sheet" role="dialog" aria-modal="true" aria-label="Search teams"><div class="sfield">${I.search}<input type="search" placeholder="Search teams or leagues" aria-label="Search teams or leagues" autocomplete="off" data-sq><button data-search-close>Cancel</button></div><div id="sres">${searchResults('')}</div></div>`;
  const input = ov.querySelector('[data-sq]');
  input.focus();
  input.oninput = () => { document.getElementById('sres').innerHTML = searchResults(input.value); };
  input.onkeydown = e => { if (e.key === 'Enter') { const first = ov.querySelector('#sres a'); if (first) first.click(); } };
  ov.querySelector('[data-search-close]').onclick = closeSearch;
  ov.onclick = e => {
    if (e.target === ov) return closeSearch();
    const a = e.target.closest('[data-recent]');
    if (a) {
      const [league, ...rest] = a.dataset.recent.split('|'), name = rest.join('|');
      recent = [{ league, name }, ...recent.filter(r => !(r.league === league && r.name === name))].slice(0, 6);
      store.set('mw-recent', JSON.stringify(recent));
    }
  };
}
function closeSearch() {
  const ov = document.getElementById('search');
  if (ov && ov.classList.contains('open')) { ov.classList.remove('open'); ov.innerHTML = ''; }
}
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeSearch();
  if (e.key === '/' && !/input|select|textarea/i.test(document.activeElement.tagName)) { e.preventDefault(); openSearch(); }
});

/* ---------- live countdown ---------- */
function tickCountdowns() {
  document.querySelectorAll('[data-countdown]').forEach(el => {
    const c = countdownParts(el.dataset.countdown);
    if (!c) { el.innerHTML = '<span><b>Kicked off</b></span>'; return; }
    el.innerHTML = `<span><b>${c[0]}</b>days</span><span><b>${c[1]}</b>hrs</span><span><b>${c[2]}</b>min</span>`;
  });
}
setInterval(tickCountdowns, 30_000);

/* ---------- events ---------- */
function bind() {
  document.querySelectorAll('[data-theme-toggle]').forEach(b => b.onclick = toggleTheme);
  document.querySelectorAll('[data-search-open]').forEach(b => b.onclick = openSearch);
  document.querySelectorAll('[data-hl]').forEach(b => b.onclick = () => { state.histLeague = b.dataset.hl; route(); });
  document.querySelectorAll('[data-hv]').forEach(b => b.onclick = () => { state.histView = b.dataset.hv; route(); });
  document.querySelectorAll('[data-view]').forEach(b => b.onclick = () => { state.view = b.dataset.view; const y = scrollY; route().then(() => scrollTo(0, y)); });
  document.querySelectorAll('[data-day]').forEach(b => b.onclick = () => { state.fxDay = b.dataset.day; route(); });
  document.querySelectorAll('[data-fxview]').forEach(b => b.onclick = () => { state.fxView = b.dataset.fxview; store.set('mw-fxview', state.fxView); const y = scrollY; route().then(() => scrollTo(0, y)); });
  document.querySelectorAll('[data-collapse]').forEach(b => b.onclick = () => { const k = b.dataset.collapse; state.collapsed.has(k) ? state.collapsed.delete(k) : state.collapsed.add(k); const y = scrollY; route().then(() => scrollTo(0, y)); });
  document.querySelectorAll('[data-tview]').forEach(b => b.onclick = () => { state.tableView = b.dataset.tview; route(); });
  document.querySelectorAll('tr[data-href]').forEach(tr => tr.onclick = e => { if (!e.target.closest('a')) location.hash = tr.dataset.href; });
  document.querySelectorAll('[data-fav-team]').forEach(b => b.onclick = e => {
    e.preventDefault();
    const [lg, ...rest] = b.dataset.favTeam.split('|');
    toggleFavTeam(lg, rest.join('|'));
    const y = scrollY; route().then(() => scrollTo(0, y));
  });
  document.querySelectorAll('[data-fav-league]').forEach(b => b.onclick = () => { toggleFavLeague(b.dataset.favLeague); const y = scrollY; route().then(() => scrollTo(0, y)); });
  const rerender = () => { const y = scrollY; route().then(() => scrollTo(0, y)); };
  document.querySelectorAll('[data-setlg]').forEach(b => b.onclick = () => { state.setLeague = b.dataset.setlg; rerender(); });
  document.querySelectorAll('[data-fxmine]').forEach(b => b.onclick = () => { state.fxMine = !state.fxMine; store.set('mw-fxmine', state.fxMine ? '1' : null); rerender(); });
  document.querySelectorAll('[data-fav-move]').forEach(b => b.onclick = () => {
    const i = +b.dataset.favMove;
    if (i > 0) { [favs.teams[i - 1], favs.teams[i]] = [favs.teams[i], favs.teams[i - 1]]; saveFavs(); }
    rerender();
  });
  const status = msg => { const el = document.querySelector('[data-sync-status]'); if (el) el.textContent = msg; };
  const copyLink = async () => {
    try { await navigator.clipboard.writeText(syncLink()); status('Link copied. Open it on your other device.'); }
    catch { status(syncLink()); }
  };
  document.querySelectorAll('[data-sync-copy]').forEach(b => b.onclick = copyLink);
  document.querySelectorAll('[data-sync-share]').forEach(b => b.onclick = async () => {
    if (!navigator.share) return copyLink();
    try { await navigator.share({ title: 'My Matchwise teams', text: 'Open this to copy my teams and leagues to this device:', url: syncLink() }); }
    catch { /* share sheet closed */ }
  });
  document.querySelectorAll('[data-sync-apply]').forEach(b => b.onclick = () => {
    const got = decodeFavs(b.dataset.code);
    if (!got) return;
    if (b.dataset.syncApply === 'replace') favs = { teams: got.teams, leagues: got.leagues };
    else {
      got.teams.forEach(f => { if (!isFavTeam(f.league, f.name)) favs.teams.push(f); });
      got.leagues.forEach(k => { if (!isFavLeague(k)) favs.leagues.push(k); });
    }
    saveFavs();
    state.syncNote = `Added ${got.teams.length} team${got.teams.length === 1 ? '' : 's'} and ${got.leagues.length} league${got.leagues.length === 1 ? '' : 's'} to this device.`;
    location.hash = '#/settings';
  });
  const sq = document.querySelector('[data-setq]');
  if (sq) sq.oninput = () => {
    state.setQ = sq.value;
    const pos = sq.selectionStart;
    route().then(() => { const s2 = document.querySelector('[data-setq]'); if (s2) { s2.focus(); s2.setSelectionRange(pos, pos); } });
  };
  document.querySelectorAll('[data-p]').forEach(s => s.onchange = () => {
    state.predict[s.dataset.p] = s.value;
    if (s.dataset.p === 'league') { state.predict.home = ''; state.predict.away = ''; }
    route();
  });
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

/* ---------- boot ---------- */
if (window.matchMedia) matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change', applyTheme);
if ('serviceWorker' in navigator && location.protocol === 'https:') { // not on localhost, so local edits show immediately
  navigator.serviceWorker.register('sw.js').catch(() => { /* offline support is optional */ });
}
getJSON('fixtures').then(m => { cache._meta = m; }).catch(() => {});
route();
