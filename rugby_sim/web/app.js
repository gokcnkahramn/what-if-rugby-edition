// Clickable "what if" team builder - vanilla JS, no build step.
// Talks only to this project's own Flask API (rugby_sim/webapp.py), which
// wraps the real POOLS / get_all_legends / Player.rating_at / MatchEngine -
// nothing rugby-related is computed here, only rendered.

let POSITIONS = [];
let UNIONS = [];
let LOGOS = {};         // code -> "/logos/CODE.png"
let NAME_TO_CODE = {};  // real nation name (incl. historical aliases) -> code

// Shared status-message helpers: every mode (Friendly, Tournament, Draft,
// Season, live match substitution/swap, etc.) writes progress/result text
// into its own "status" element. setStatus() centralizes that so error text
// always gets the .status-error (red) class, and any normal/success text
// always clears it - otherwise a stale red error class could linger after a
// later successful action overwrote the same element's text.
function setStatus(el, message, isError) {
  if (!el) return;
  el.textContent = message;
  el.classList.toggle("status-error", !!isError);
}
function showError(el, message) {
  setStatus(el, message, true);
}

function logoCodeFor(codeOrName) {
  if (LOGOS[codeOrName]) return codeOrName;
  return NAME_TO_CODE[codeOrName] || null;
}
function logoImgHtml(codeOrName, size) {
  size = size || 20;
  const code = logoCodeFor(codeOrName);
  const src = code ? LOGOS[code] : null;
  if (!src) return `<span class="logo-ph" style="display:inline-block;width:${size}px"></span>`;
  return `<img src="${src}" alt="" class="logo-img" style="width:${size}px;height:${size}px;object-fit:contain;vertical-align:middle;margin-right:4px">`;
}
// Real rugbydata coverage is 2022-2026 (see README) - a dropdown of known-
// good seasons instead of a free-text field, so you're never guessing
// which years actually have data.
const SEASON_YEARS = ["2026", "2025", "2024", "2023", "2022"];
function seasonSelectHtml(id, selected) {
  selected = selected || "2026";
  return `<select id="${id}">` +
    SEASON_YEARS.map(y => `<option value="${y}" ${y === selected ? "selected" : ""}>${y}</option>`).join("") +
    `</select>`;
}

// Merges a freshly-loaded pool of players into an existing one, by real-
// person identity rather than object identity - loading the same union (or
// an overlapping historical squad) twice would otherwise add the exact same
// real player as two separate entries (each a distinct Player object/id
// server-side, since every `/api/pool/<code>`/historical-squad call builds
// fresh objects), showing up as a literal duplicate pick in any list. Keyed
// by name - same convention `build_union_pool` already uses server-side
// (see README) for the equivalent problem within one union's own pool.
function mergeUniquePlayers(existingPool, newPlayers) {
  const seen = new Set(existingPool.map(p => p.name));
  const added = newPlayers.filter(p => !seen.has(p.name));
  return existingPool.concat(added);
}

// ===================== Shared "sort by rating" control =====================
// One helper + one small toggle button, reused everywhere a list of
// players is shown for picking (TeamBuilder's candidate list and bench,
// the live match's bench, draft mode's remaining pool and protect/poach
// selects) instead of five separate ad-hoc sorts - see README.
function sortPlayersByRating(players, direction, field) {
  field = field || "fit";
  const sorted = players.slice().sort((a, b) => (a[field] || 0) - (b[field] || 0));
  if (direction === "desc") sorted.reverse();
  return sorted;
}

// Renders a tiny "Sort: Rating v/^" toggle button. `getDir`/`setDir` read
// and write wherever the caller is keeping its current direction (a plain
// variable, or a field on some state object) - `onChange` just re-renders.
function sortToggleHtml(id) {
  return `<button class="sort-toggle" id="${id}" type="button"></button>`;
}
function wireSortToggle(id, getDir, setDir, onChange) {
  const btn = document.getElementById(id);
  if (!btn) return;
  const paint = () => { btn.textContent = `Sort: Rating ${getDir() === "desc" ? "↓ high-to-low" : "↑ low-to-high"}`; };
  paint();
  btn.onclick = () => {
    setDir(getDir() === "desc" ? "asc" : "desc");
    paint();
    onChange();
  };
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "request failed");
  return data;
}

class TeamBuilder {
  constructor(side, opts) {
    opts = opts || {};
    this.side = side;
    this.mode = null;       // "nation" | "free" | "legends"
    this.pool = [];         // all players currently loaded, [{id,name,...}]
    this.slots = {};        // position value -> player id
    this.bench = new Set(); // player ids
    this.selectedPosition = null;
    this.teamId = null;
    this.title = opts.title || (side === "home" ? "Team A (home)" : side === "away" ? "Team B (away)" : side);
    this.fixedName = opts.fixedName || null; // if set, name field is pre-filled and locked
    if (this.fixedName) this.name = this.fixedName;
    this.fixedPool = opts.fixedPool || null; // if set, skip mode selection - draft from this exact squad
    if (this.fixedPool) { this.mode = "fixed"; this.pool = this.fixedPool; }
    this.el = document.getElementById(`panel-${side}`);
    this.render();
  }

  usedIds() {
    return new Set(Object.values(this.slots));
  }

  render() {
    const title = this.title;
    const modeButtons = this.fixedPool
      ? `<span class="muted">Drafting from this exact historical squad (${this.pool.length} players).</span>`
      : `
      <button data-mode="nation" class="${this.mode === "nation" ? "active" : ""}">By nation</button>
      <button data-mode="free" class="${this.mode === "free" ? "active" : ""}">Free pool</button>
      <button data-mode="legends" class="${this.mode === "legends" ? "active" : ""}">Legends (HoF)</button>
      <button data-mode="historical" class="${this.mode === "historical" ? "active" : ""}">Historical squad</button>
      <button id="${this.side}-import-btn">Load saved team...</button>
      <input type="file" id="${this.side}-import-file" accept="application/json" style="display:none">`;
    this.el.innerHTML = `
      <h2>${title}</h2>
      <div class="row">${modeButtons}</div>
      <div id="${this.side}-mode-area"></div>
      <div class="row">
        <label class="muted">Team name: <input type="text" id="${this.side}-name" value="${this.name || ""}" ${this.fixedName ? "disabled" : ""}></label>
      </div>
      <div class="pitch" id="${this.side}-pitch"></div>
      <div class="candidates" id="${this.side}-candidates"></div>
      <div id="${this.side}-finish"></div>
    `;
    this.el.querySelectorAll("[data-mode]").forEach(btn => {
      btn.onclick = () => { this.mode = btn.dataset.mode; this.pool = []; this.render(); this.renderModeArea(); };
    });
    const importBtn = document.getElementById(`${this.side}-import-btn`);
    const importFile = document.getElementById(`${this.side}-import-file`);
    if (importBtn && importFile) {
    importBtn.onclick = () => importFile.click();
    importFile.onchange = async () => {
      const file = importFile.files[0];
      if (!file) return;
      try {
        const text = await file.text();
        const data = JSON.parse(text);
        const res = await api("/api/team/import", {
          method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data),
        });
        this.pool = res.pool;
        this.slots = res.slots;
        this.bench = new Set(res.bench);
        this.teamId = res.team_id;
        this.name = res.name;
        this.render();
        updateRunButton();
      } catch (e) {
        alert("Could not load team file: " + e.message);
      }
    };
    }
    this.renderModeArea();
    this.renderPitch();
    this.renderFinish();
  }

  renderModeArea() {
    const area = document.getElementById(`${this.side}-mode-area`);
    if (!area) return;
    if (this.mode === "nation") {
      area.innerHTML = `
        <div class="row">
          <span id="${this.side}-union-logo">${logoImgHtml(null, 28)}</span>
          <select id="${this.side}-union"></select>
          ${seasonSelectHtml(`${this.side}-season`)}
          <button id="${this.side}-load">Load pool</button>
          <span class="muted" id="${this.side}-load-status"></span>
        </div>`;
      const sel = document.getElementById(`${this.side}-union`);
      sel.innerHTML = UNIONS.map(u => `<option value="${u.code}">${u.code} - ${u.name}</option>`).join("");
      const logoSpan = document.getElementById(`${this.side}-union-logo`);
      const updateLogo = () => { logoSpan.innerHTML = logoImgHtml(sel.value, 28); };
      sel.onchange = updateLogo;
      updateLogo();
      document.getElementById(`${this.side}-load`).onclick = async () => {
        const code = sel.value, season = document.getElementById(`${this.side}-season`).value || "2026";
        const status = document.getElementById(`${this.side}-load-status`);
        setStatus(status, "loading (first time may hit the network)...");
        const players = await api(`/api/pool/${code}?season=${encodeURIComponent(season)}`);
        this.pool = players;
        this.name = this.name || sel.options[sel.selectedIndex].text.split(" - ")[1];
        document.getElementById(`${this.side}-name`).value = this.name;
        setStatus(status, `${players.length} players loaded.`);
      };
    } else if (this.mode === "free") {
      area.innerHTML = `
        <div class="row muted">Click unions to merge their pools together:</div>
        <div class="row" id="${this.side}-union-list"></div>
        <div class="row">
          <label class="muted">Season: ${seasonSelectHtml(`${this.side}-season`)}</label>
          <span class="muted" id="${this.side}-load-status"></span>
        </div>`;
      const list = document.getElementById(`${this.side}-union-list`);
      list.innerHTML = UNIONS.map(u => `<button data-code="${u.code}">${logoImgHtml(u.code, 18)}${u.code}</button>`).join("");
      list.querySelectorAll("button").forEach(btn => {
        btn.onclick = async () => {
          const season = document.getElementById(`${this.side}-season`).value || "2026";
          const status = document.getElementById(`${this.side}-load-status`);
          setStatus(status, "loading...");
          const players = await api(`/api/pool/${btn.dataset.code}?season=${encodeURIComponent(season)}`);
          this.pool = mergeUniquePlayers(this.pool, players);
          btn.classList.add("active");
          setStatus(status, `${this.pool.length} players in the mix.`);
        };
      });
    } else if (this.mode === "legends") {
      area.innerHTML = `<div class="row"><button id="${this.side}-load-legends">Load Hall of Fame roster</button>
        <span class="muted" id="${this.side}-load-status"></span></div>`;
      document.getElementById(`${this.side}-load-legends`).onclick = async () => {
        const status = document.getElementById(`${this.side}-load-status`);
        setStatus(status, "loading (first time is network-heavy, ~190 pages - cached after)...");
        const players = await api("/api/legends");
        this.pool = players;
        setStatus(status, `${players.length} legends loaded.`);
      };
    } else if (this.mode === "historical") {
      area.innerHTML = `
        <div class="row muted">Mix in one or more real historical squads (World Cup or Six Nations):</div>
        <div class="row">
          <select id="${this.side}-hist-comp">
            <option value="rwc">Rugby World Cup (1995-2023)</option>
            <option value="sn">Six Nations Championship (2009-2021)</option>
          </select>
          <select id="${this.side}-hist-year"></select>
          <select id="${this.side}-hist-team"><option>(load a year first)</option></select>
          <span id="${this.side}-hist-logo">${logoImgHtml(null, 24)}</span>
          <button id="${this.side}-hist-add">Add this squad</button>
          <span class="muted" id="${this.side}-hist-status"></span>
        </div>
        <p class="muted">Historical-year squads show that union's current crest - same logo
        across eras, see README (sourcing an exact historical-year logo per team isn't practical
        at this scale).</p>`;
      const compSel = document.getElementById(`${this.side}-hist-comp`);
      const yearSel = document.getElementById(`${this.side}-hist-year`);
      const teamSel = document.getElementById(`${this.side}-hist-team`);
      const histLogoSpan = document.getElementById(`${this.side}-hist-logo`);
      const status = document.getElementById(`${this.side}-hist-status`);
      let yearData = null; // {year, squads: {name: [players]}}

      const updateHistLogo = () => { histLogoSpan.innerHTML = logoImgHtml(teamSel.value, 24); };
      const loadYears = async () => {
        const path = compSel.value === "rwc" ? "/api/historical_rwc/years" : "/api/historical_six_nations/years";
        const res = await api(path);
        yearSel.innerHTML = res.years.map(y => `<option value="${y}">${y}</option>`).join("");
        await loadYearData();
      };
      const loadYearData = async () => {
        const year = yearSel.value;
        setStatus(status, "loading real squads (first time is network-heavy - cached after)...");
        const path = compSel.value === "rwc" ? `/api/historical_rwc/${year}` : `/api/historical_six_nations/${year}`;
        const res = await api(path);
        yearData = res;
        const teamNames = Object.keys(res.squads).sort();
        teamSel.innerHTML = teamNames.map(n => `<option value="${n}">${n}</option>`).join("");
        setStatus(status, `${teamNames.length} teams loaded for ${year}.`);
        updateHistLogo();
      };
      compSel.onchange = loadYears;
      yearSel.onchange = loadYearData;
      teamSel.onchange = updateHistLogo;
      document.getElementById(`${this.side}-hist-add`).onclick = () => {
        if (!yearData) return;
        const squad = yearData.squads[teamSel.value] || [];
        this.pool = mergeUniquePlayers(this.pool, squad);
        setStatus(status, `${this.pool.length} players in the mix.`);
      };
      loadYears();
    } else {
      area.innerHTML = "";
    }
  }
  // (mode === "fixed": pool is pre-loaded in the constructor, nothing to render here)

  renderPitch() {
    const pitch = document.getElementById(`${this.side}-pitch`);
    if (!pitch) return;
    pitch.innerHTML = POSITIONS.map(pos => {
      const pid = this.slots[pos];
      const player = pid ? this.pool.find(p => p.id === pid) : null;
      const filled = player ? "filled" : "";
      const selected = this.selectedPosition === pos ? "selected" : "";
      const label = player ? `${player.name}` : "(empty)";
      return `<button class="slot ${filled} ${selected}" data-pos="${pos}"><span class="pos">${pos}</span>${label}</button>`;
    }).join("");
    pitch.querySelectorAll(".slot").forEach(btn => {
      btn.onclick = () => this.pickPosition(btn.dataset.pos);
    });
  }

  async pickPosition(pos) {
    if (!this.pool.length) { alert("Load a pool first."); return; }
    this.selectedPosition = pos;
    this.renderPitch();
    const used = this.usedIds();
    // Exclude bench picks too - without this, a player already sent to the
    // bench could still be clicked into a starting slot, putting the same
    // person in the squad twice (bench *and* starting XV).
    const available = this.pool.filter(p =>
      (!used.has(p.id) && !this.bench.has(p.id)) || this.slots[pos] === p.id);
    const ranked = await api("/api/rank", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({player_ids: available.map(p => p.id), position: pos}),
    });
    this._candidateSortDir = this._candidateSortDir || "desc";
    this._lastRanked = ranked;
    this._renderCandidateList(pos);
  }

  _renderCandidateList(pos) {
    const ranked = sortPlayersByRating(this._lastRanked, this._candidateSortDir, "fit");
    const box = document.getElementById(`${this.side}-candidates`);
    box.innerHTML = `<div class="row"><div class="muted">Top candidates for ${pos} (click to assign):</div>${sortToggleHtml(`${this.side}-candidates-sort`)}</div>` +
      ranked.slice(0, 15).map(p => `
        <div class="candidate" data-id="${p.id}">
          <span>${p.name} (${p.nation}${p.era ? ", " + p.era : ""}) - natural: ${p.natural_position}</span>
          <span class="fit">${p.fit.toFixed(1)}</span>
        </div>`).join("");
    wireSortToggle(`${this.side}-candidates-sort`,
      () => this._candidateSortDir, (d) => { this._candidateSortDir = d; },
      () => this._renderCandidateList(pos));
    box.querySelectorAll(".candidate").forEach(row => {
      row.onclick = () => {
        this.slots[pos] = parseInt(row.dataset.id, 10);
        this.selectedPosition = null;
        document.getElementById(`${this.side}-candidates`).innerHTML = "";
        this.renderPitch();
        this.renderFinish();
      };
    });
  }

  renderFinish() {
    const box = document.getElementById(`${this.side}-finish`);
    if (!box) return;
    const filledCount = Object.keys(this.slots).length;
    if (filledCount < POSITIONS.length) {
      box.innerHTML = `<p class="muted">${filledCount}/${POSITIONS.length} positions filled.</p>`;
      return;
    }
    const starterIds = new Set(Object.values(this.slots));
    this._benchSortDir = this._benchSortDir || "desc";
    const benchCandidates = sortPlayersByRating(
      this.pool.filter(p => !starterIds.has(p.id)), this._benchSortDir, "natural_fit");
    box.innerHTML = `
      <div class="row">
        <label class="muted">Captain:
          <select id="${this.side}-captain">
            ${Object.entries(this.slots).map(([pos, pid]) => {
              const p = this.pool.find(pp => pp.id === pid);
              return `<option value="${pid}">${p.name} (${pos})</option>`;
            }).join("")}
          </select>
        </label>
      </div>
      <div class="row"><div class="muted">Bench (optional, click up to 8, sorted by natural-position rating):</div>${sortToggleHtml(`${this.side}-bench-sort`)}</div>
      <div class="row" id="${this.side}-bench-list">
        ${benchCandidates.slice(0, 40).map(p =>
          `<button data-id="${p.id}" class="${this.bench.has(p.id) ? "active" : ""}">${p.name} (${p.natural_fit.toFixed(1)})</button>`
        ).join("")}
      </div>
      <div class="row">
        <button id="${this.side}-save">Save team</button>
        ${this.teamId ? `<button id="${this.side}-export">Download as file</button>` : ""}
        <span class="muted" id="${this.side}-save-status"></span>
      </div>`;
    if (this.teamId) {
      document.getElementById(`${this.side}-export`).onclick = async () => {
        const data = await api(`/api/team/${this.teamId}/export`);
        const blob = new Blob([JSON.stringify(data, null, 2)], {type: "application/json"});
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${(this.name || "team").replace(/[^A-Za-z0-9]+/g, "_")}.json`;
        a.click();
        URL.revokeObjectURL(url);
      };
    }
    wireSortToggle(`${this.side}-bench-sort`,
      () => this._benchSortDir, (d) => { this._benchSortDir = d; },
      () => this.renderFinish());
    document.getElementById(`${this.side}-bench-list`).querySelectorAll("button").forEach(btn => {
      // Toggle in place rather than calling renderFinish() again - a full
      // re-render would wipe the captain <select>'s current choice and any
      // "Saved" status text, which made it look like saving had silently
      // failed when really it just hadn't been (re-)clicked yet.
      btn.onclick = () => {
        const id = parseInt(btn.dataset.id, 10);
        if (this.bench.has(id)) {
          this.bench.delete(id);
          btn.classList.remove("active");
        } else if (this.bench.size < 8) {
          this.bench.add(id);
          btn.classList.add("active");
        }
        this.teamId = null; // bench changed - needs re-saving before it counts
        document.getElementById(`${this.side}-save-status`).textContent =
          "Bench changed - click Save team again.";
        updateRunButton();
      };
    });
    document.getElementById(`${this.side}-save`).onclick = async () => {
      this.name = document.getElementById(`${this.side}-name`).value || (this.side === "home" ? "Home" : "Away");
      const captain = parseInt(document.getElementById(`${this.side}-captain`).value, 10);
      const status = document.getElementById(`${this.side}-save-status`);
      setStatus(status, "saving...");
      try {
        const res = await api("/api/team", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            name: this.name, slots: this.slots, captain,
            bench: Array.from(this.bench),
          }),
        });
        this.teamId = res.team_id;
        setStatus(status, res.problems.length ? `Saved with issues: ${res.problems.join("; ")}` : "Saved - ready to play.");
        updateRunButton();
      } catch (e) {
        showError(status, "Error: " + e.message);
      }
    };
  }
}

function updateRunButton() {
  const btn = document.getElementById("run-match");
  const ready = homeBuilder.teamId && awayBuilder.teamId;
  btn.disabled = !ready;
  const hint = document.getElementById("run-hint");
  if (ready) {
    setStatus(hint, "");
  } else {
    const missing = [];
    if (!homeBuilder.teamId) missing.push("Team A");
    if (!awayBuilder.teamId) missing.push("Team B");
    showError(hint, `Click "Save team" on ${missing.join(" and ")} first.`);
  }
  updateTournamentRunHint();
}

let homeBuilder, awayBuilder;

// ===================== Screen navigation (mode-select -> friendly|tournament) =====================
// A tiny view-stack: each entry is {label, onClick} - onClick re-shows that
// screen (and is what the breadcrumb button does). The page starts on
// mode-select; friendly/tournament setup is deferred until the user
// actually picks that mode, so nothing heavy (team builders, tournament
// options fetch) runs before it's needed.
let navStack = [];
let friendlyInitialized = false;
let tournamentInitialized = false;

function renderBreadcrumb() {
  const box = document.getElementById("breadcrumb");
  box.innerHTML = navStack.map((entry, i) => {
    const isLast = i === navStack.length - 1;
    const sep = i > 0 ? `<span class="sep">/</span>` : "";
    return `${sep}<button class="crumb" data-i="${i}" ${isLast ? "disabled" : ""}>${entry.label}</button>`;
  }).join("");
  box.querySelectorAll(".crumb").forEach(btn => {
    btn.onclick = () => {
      const i = parseInt(btn.dataset.i, 10);
      navStack = navStack.slice(0, i + 1);
      navStack[i].onShow();
      renderBreadcrumb();
    };
  });
}

function showScreen(id) {
  document.querySelectorAll(".screen").forEach(el => el.classList.add("hidden"));
  document.getElementById(id).classList.remove("hidden");
}

function navTo(id, label, onShow) {
  navStack.push({label, onShow});
  onShow();
  renderBreadcrumb();
}

function navReset() {
  navStack = [];
  navTo("screen-mode-select", "What If Rugby Edition", () => {
    showScreen("screen-mode-select");
    randomizeBackground();
  });
}

async function enterFriendlyMode() {
  navTo("screen-friendly", "Friendly match", () => showScreen("screen-friendly"));
  randomizeBackground();
  if (friendlyInitialized) return;
  friendlyInitialized = true;
  homeBuilder = new TeamBuilder("home");
  awayBuilder = new TeamBuilder("away");
  updateRunButton();
}

async function enterTournamentMode() {
  navTo("screen-tournament", "Tournament mode", () => {
    showScreen("screen-tournament");
    if (tournamentInitialized) renderTournamentTypePicker();
  });
  randomizeBackground();
  if (tournamentInitialized) return;
  tournamentInitialized = true;
  await setupTournamentUI();
}

// Picks one of the cached, freely-licensed stadium photos (see
// background_image.py) at random for the blurred menu-screen background,
// and shows its required CC attribution in the corner. Re-randomized (never
// twice in a row - see `randomizeBackground`) each time the main
// mode-select screen or one of the 3 top-level modes is entered, not on
// every sub-screen navigation within a mode. Silently does nothing if none
// are cached (plain dark background instead) - a visual nicety, never
// blocks anything.
let backgroundEntries = null;
let lastBackgroundKey = null;

async function setupBackgroundPhoto() {
  try {
    const res = await api("/api/backgrounds");
    backgroundEntries = Object.entries(res.backgrounds || {}); // [[key, {url, caption, license, author}], ...]
    randomizeBackground();
  } catch (e) {
    // no photo, no problem
  }
}

function randomizeBackground() {
  if (!backgroundEntries || !backgroundEntries.length) return;
  let candidates = backgroundEntries;
  if (backgroundEntries.length > 1 && lastBackgroundKey) {
    candidates = backgroundEntries.filter(([key]) => key !== lastBackgroundKey);
  }
  const [key, chosen] = candidates[Math.floor(Math.random() * candidates.length)];
  lastBackgroundKey = key;
  document.documentElement.style.setProperty("--bg-photo", `url("${chosen.url}")`);
  const attr = document.getElementById("bg-attribution");
  if (attr) {
    attr.textContent = `${chosen.caption} - ${chosen.author} (${chosen.license}), via Wikimedia Commons`;
  }
}

async function boot() {
  POSITIONS = await api("/api/positions");
  UNIONS = await api("/api/unions");
  try {
    const logoData = await api("/api/logos");
    LOGOS = logoData.logos;
    NAME_TO_CODE = logoData.name_to_code;
  } catch (e) {
    LOGOS = {}; NAME_TO_CODE = {}; // logos are a visual nicety, never block the app
  }
  setupBackgroundPhoto(); // fire-and-forget, a visual nicety, never blocks boot
  updateClassicMatchCount(); // fire-and-forget, a label nicety, never blocks boot

  navReset();
  document.getElementById("mode-friendly").onclick = enterFriendlyMode;
  document.getElementById("mode-tournament").onclick = enterTournamentMode;
  document.getElementById("mode-draft").onclick = enterDraftMode;
  document.getElementById("mode-season").onclick = enterSeasonMode;
  document.getElementById("mode-classic-matches").onclick = enterClassicMatchesMode;

  document.getElementById("run-match").onclick = async () => {
    const seedRaw = document.getElementById("seed").value;
    const status = document.getElementById("run-status");
    const seed = seedRaw ? parseInt(seedRaw, 10) : null;
    const isLive = document.getElementById("live-match-toggle").checked;
    setStatus(status, "simulating...");
    try {
      if (isLive) {
        document.getElementById("report").innerHTML = "";
        await startLiveMatch(homeBuilder.teamId, awayBuilder.teamId, seed, "live-match-area", null);
        setStatus(status, "");
      } else {
        document.getElementById("live-match-area").innerHTML = "";
        const data = await api("/api/match", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({home_team_id: homeBuilder.teamId, away_team_id: awayBuilder.teamId, seed}),
        });
        renderReport(data);
        setStatus(status, "");
      }
    } catch (e) {
      showError(status, "Error: " + e.message);
    }
  };
}

// ===================== Live (pausable) single match =====================

async function startLiveMatch(homeTeamId, awayTeamId, seed, boxId, allowSubsFor, reportTargetId) {
  const state = await api("/api/match/live/start", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({home_team_id: homeTeamId, away_team_id: awayTeamId, seed}),
  });
  renderLiveMatchState(state, undefined, boxId, allowSubsFor, reportTargetId);
}

// `allowSubsFor`: null/undefined = both sides can substitute (a single
// friendly, where the user built both teams themselves); "home"/"away"
// restricts the "Substitute..." control to just that side (an interactive
// tournament fixture, where the opponent is an auto-drafted/CPU side the
// user shouldn't get to make substitution calls for).
let liveBenchSortDir = "desc";
// Mid-match "swap positions" selection in progress - null, or
// {side, position} for the first of the two on-field players picked so far
// (see `liveLineupTable`/`wireSwapButtons`). Reset whenever the lineup
// re-renders (a new state object) so a stale pending swap from a previous
// checkpoint/side can never leak into a later render.
let pendingSwap = null;

// Position fit and match condition are two separate numbers, never combined
// into one - `natural_fit` (how good a player is at their own normal job)
// comes from `Player.rating_at` and never changes mid-match; `condition` is
// the engine's own live in-match stamina (0-100, see
// `MatchEngine.condition_for`) and ticks down as the match goes on. Both are
// shown side by side here so it's clear which is which.
function liveLineupTable(side, lineup, bench, allowSubs) {
  const rows = lineup.map(p => `
    <tr><td>${p.position}</td><td>${p.name}</td><td>${p.natural_fit.toFixed(1)}</td><td>${p.condition.toFixed(0)}</td>
    <td>${allowSubs ? `<button class="live-sub-btn" data-side="${side}" data-pos="${p.position}">Substitute...</button>
      <button class="live-swap-btn" data-side="${side}" data-pos="${p.position}">Swap positions...</button>` : ""}</td></tr>
  `).join("");
  const sortedBench = sortPlayersByRating(bench, liveBenchSortDir, "natural_fit");
  const benchText = sortedBench.map(p => `${p.name} (fit ${p.natural_fit.toFixed(1)}, condition ${p.condition.toFixed(0)})`).join(", ") || "(none left)";
  return `<table class="stats"><tr><th>Position</th><th>Player</th><th>Fit</th><th>Condition</th><th></th></tr>${rows}</table>
    <p class="muted">Bench (by natural-position rating): ${benchText}</p>`;
}

// `renderLiveMatchState`/`renderReport` re-render the same box (same
// `playbackId`/`targetId`) repeatedly as a live match progresses (every
// "Resume play"/"Skip to next substitution point" click rebuilds the whole
// box from scratch, including a brand-new `pacedEventReveal`). Without
// this, the PREVIOUS render's `setInterval` timer kept running in the
// background against its own stale `cursor`/`events` closure even after
// its DOM elements were wiped out by `box.innerHTML = ...` - harmless to
// look at (nothing visible to paint into), but it kept firing
// `playCheerSound()` for events the user had already moved past, which is
// exactly the "cheer plays again after I've already clicked past those
// scores" bug. Every `pacedEventReveal(...)` call site must go through
// this wrapper, keyed by the same stable id the caller already uses for
// its container (`playbackId`/`targetId`), so the old timer is always
// stopped before the new one starts.
const activePacedReveals = {};
function startPacedReveal(key, ...args) {
  if (activePacedReveals[key]) activePacedReveals[key].stop();
  const reveal = pacedEventReveal(...args);
  activePacedReveals[key] = reveal;
  return reveal;
}

// `liveRevealProgress`: boxId -> {sessionId, shown} - how many of this
// session's events were already fully shown as of the LAST render, so a
// fresh render (after a continue/substitute) only paces the reveal of
// events that arrived since then, instead of re-revealing the whole list
// from scratch every time (the live state response always contains every
// event up to the current pause point, not just new ones).
const liveRevealProgress = {};

function renderLiveMatchState(state, onFinished, boxId, allowSubsFor, reportTargetId) {
  const boxKey = boxId || "live-match-area";
  const box = document.getElementById(boxKey);

  // Once the match is actually over, don't render any of the mid-match live
  // UI at all - no lineup/"Substitute..." tables (there's nothing left to
  // substitute for), no partial "paused at X'" event log, no Resume/skip
  // buttons. Rendering those alongside the final report used to show the
  // match twice: the live view's own last chunk of events in one box, and
  // the full final report's complete event list in another, right below
  // it. Now this box is cleared and the one full report is the only thing
  // shown, in every mode (friendly, tournament, draft) that uses this
  // function - they all funnel through here.
  if (state.finished) {
    box.innerHTML = "";
    if (state.result) {
      renderReport(state.result, reportTargetId, true);
    }
    if (onFinished) onFinished(state);
    return;
  }

  const homeSubsAllowed = allowSubsFor === undefined || allowSubsFor === null || allowSubsFor === "home";
  const awaySubsAllowed = allowSubsFor === undefined || allowSubsFor === null || allowSubsFor === "away";

  if (!liveRevealProgress[boxKey] || liveRevealProgress[boxKey].sessionId !== state.session_id) {
    liveRevealProgress[boxKey] = {sessionId: state.session_id, shown: 0};
  }
  pendingSwap = null;
  const startAt = Math.min(liveRevealProgress[boxKey].shown, state.events.length);
  const playbackId = `${boxKey}-live-playback`;

  box.innerHTML = `
    <h3>Live match - paused at ${state.minute}'</h3>
    <div id="scoreline">${state.scoreline}</div>
    ${playbackControlsHtml(playbackId, false)}
    <div id="${playbackId}-events" class="events"></div>
    <div class="row">
      <div style="flex:1"><h4>${state.home.name}</h4>${liveLineupTable("home", state.home.lineup, state.home.bench, homeSubsAllowed)}</div>
      <div style="flex:1"><h4>${state.away.name}</h4>${liveLineupTable("away", state.away.lineup, state.away.bench, awaySubsAllowed)}</div>
    </div>
    <div class="row">
      <button id="live-continue">Resume play</button>
      <button id="live-auto-to-sub">Skip to next substitution point</button>
      <button id="live-skip-to-end">Skip to end of match</button>
      ${sortToggleHtml("live-bench-sort")}
      <span class="muted" id="live-status"></span>
    </div>
    <div id="live-sub-picker"></div>`;

  const eventsEl = document.getElementById(`${playbackId}-events`);
  const scorelineEl = document.getElementById("scoreline");
  const reveal = startPacedReveal(playbackId, eventsEl, state.events, startAt, undefined, undefined, (h, a) => {
    if (scorelineEl) scorelineEl.textContent = `${state.home.name} ${h} - ${a} ${state.away.name}`;
  }, state.home_advantage_for);
  wirePlaybackControls(playbackId, reveal);
  liveRevealProgress[boxKey].shown = state.events.length;

  wireSortToggle("live-bench-sort", () => liveBenchSortDir, (d) => { liveBenchSortDir = d; },
    () => renderLiveMatchState(state, onFinished, boxId, allowSubsFor, reportTargetId));

  box.querySelectorAll(".live-sub-btn").forEach(btn => {
    btn.onclick = () => renderLiveSubPicker(state, btn.dataset.side, btn.dataset.pos, boxId, onFinished, allowSubsFor, reportTargetId);
  });
  box.querySelectorAll(".live-swap-btn").forEach(btn => {
    btn.onclick = () => handleSwapClick(state, btn.dataset.side, btn.dataset.pos, boxId, onFinished, allowSubsFor, reportTargetId);
  });

  const continueBtn = document.getElementById("live-continue");
  continueBtn.onclick = async () => {
    const status = document.getElementById("live-status");
    setStatus(status, "resuming...");
    try {
      const next = await api(`/api/match/live/${state.session_id}/continue`, {
        method: "POST", headers: {"Content-Type": "application/json"}, body: "{}",
      });
      renderLiveMatchState(next, onFinished, boxId, allowSubsFor, reportTargetId);
    } catch (e) {
      showError(status, "Error: " + e.message);
    }
  };
  // "Skip to next substitution" in the live/pausable context: the pause
  // checkpoints (LIVE_MATCH_CHECKPOINTS in webapp.py, e.g. 20'/40'/60'/70')
  // ARE the substitution opportunities - each `.../continue` call already
  // advances to exactly the next one and stops there (never further), so
  // this button is just that one call, not a search/loop. From 22' this
  // lands on 40' and stops (offering the chance to sub, whether or not you
  // take it); from 41' it lands on 60' and stops - always exactly the next
  // checkpoint, never skipping past one looking for something "more
  // interesting" to happen first.
  document.getElementById("live-auto-to-sub").onclick = async () => {
    const status = document.getElementById("live-status");
    setStatus(status, "advancing to the next substitution point...");
    try {
      const next = await api(`/api/match/live/${state.session_id}/continue`, {
        method: "POST", headers: {"Content-Type": "application/json"}, body: "{}",
      });
      renderLiveMatchState(next, onFinished, boxId, allowSubsFor, reportTargetId);
    } catch (e) {
      showError(status, "Error: " + e.message);
    }
  };
  // "Skip to end of match" - repeatedly calls the exact same `.../continue`
  // endpoint "Resume play" uses, one checkpoint at a time, until the match
  // reports finished - no backend change needed, this is just doing
  // several of the same round-trips the user would otherwise click
  // through one at a time. Unlike the plain report's "Skip to end" (which
  // instantly reveals an already-fully-simulated event list), this one
  // actually drives the match to completion first, then reveals it.
  document.getElementById("live-skip-to-end").onclick = async () => {
    const status = document.getElementById("live-status");
    let current = state;
    try {
      while (!current.finished) {
        setStatus(status, "skipping to the end of the match...");
        current = await api(`/api/match/live/${current.session_id}/continue`, {
          method: "POST", headers: {"Content-Type": "application/json"}, body: "{}",
        });
      }
      renderLiveMatchState(current, onFinished, boxId, allowSubsFor, reportTargetId);
    } catch (e) {
      showError(status, "Error: " + e.message);
    }
  };
}

// Like draft mode's depth chart / `/api/rank`, the bench picker shows each
// candidate's OWN natural position plus their fit rating AT THE SPECIFIC
// POSITION being substituted into (never the same number) - computed
// server-side via `/api/rank` (`Player.rating_at`), not duplicated in JS.
async function renderLiveSubPicker(state, side, position, boxId, onFinished, allowSubsFor, reportTargetId) {
  const picker = document.getElementById("live-sub-picker");
  const bench = state[side].bench;
  if (!bench.length) {
    picker.innerHTML = `<p class="muted">No bench players left for ${state[side].name}.</p>`;
    return;
  }
  picker.innerHTML = `<p class="muted">Loading fit ratings...</p>`;
  let ranked;
  try {
    ranked = await api("/api/rank", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({player_ids: bench.map(p => p.id), position}),
    });
  } catch (e) {
    picker.innerHTML = `<p class="muted">Could not load fit ratings: ${e.message}</p>`;
    return;
  }
  const sorted = liveBenchSortDir === "desc"
    ? [...ranked].sort((a, b) => b.fit - a.fit)
    : [...ranked].sort((a, b) => a.fit - b.fit);
  // `/api/rank` only returns fit (it's a pure position-fit lookup, reused
  // from draft mode) - condition is live in-match stamina the bench list
  // already carries (`_bench_json`), so it's merged in here by id rather
  // than duplicated into `/api/rank` itself.
  const conditionById = new Map(bench.map(p => [p.id, p.condition]));
  picker.innerHTML = `
    <div class="row">
      <span class="muted">Bring on for ${state[side].name} at ${position} (name, natural position, fit at ${position}, condition):</span>
      ${sortToggleHtml("live-sub-picker-sort")}
    </div>
    <div class="row">
      ${sorted.map(p => `<button class="live-sub-pick" data-id="${p.id}">${p.name} (${p.natural_position}) - fit ${p.fit.toFixed(1)}, condition ${(conditionById.get(p.id) ?? 100).toFixed(0)}</button>`).join("")}
    </div>`;
  wireSortToggle("live-sub-picker-sort", () => liveBenchSortDir, (d) => { liveBenchSortDir = d; },
    () => renderLiveSubPicker(state, side, position, boxId, onFinished, allowSubsFor, reportTargetId));
  picker.querySelectorAll(".live-sub-pick").forEach(btn => {
    btn.onclick = async () => {
      try {
        const next = await api(`/api/match/live/${state.session_id}/substitute`, {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({team: side, position, bench_player_id: parseInt(btn.dataset.id, 10)}),
        });
        renderLiveMatchState(next, onFinished, boxId, allowSubsFor, reportTargetId);
      } catch (e) {
        alert("Could not make that substitution: " + e.message);
      }
    };
  });
}

// First click on a "Swap positions..." button remembers that on-field
// player; a second click (same side, different position) performs the
// actual swap via `/api/match/live/<id>/swap`. Clicking the SAME position
// again cancels the pending swap, and picking a position on the OTHER side
// restarts the pending swap on that side instead (a swap is always within
// one team, same as the real rugby mechanic this models).
function handleSwapClick(state, side, position, boxId, onFinished, allowSubsFor, reportTargetId) {
  const picker = document.getElementById("live-sub-picker");
  if (!pendingSwap || pendingSwap.side !== side) {
    pendingSwap = {side, position};
    picker.innerHTML = `<p class="muted">Swap ${position} with which other on-field position for ${state[side].name}? Click "Swap positions..." on the other player.</p>`;
    return;
  }
  if (pendingSwap.position === position) {
    pendingSwap = null;
    picker.innerHTML = "";
    return;
  }
  const positionA = pendingSwap.position;
  const positionB = position;
  pendingSwap = null;
  (async () => {
    try {
      const next = await api(`/api/match/live/${state.session_id}/swap`, {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({team: side, position_a: positionA, position_b: positionB}),
      });
      renderLiveMatchState(next, onFinished, boxId, allowSubsFor, reportTargetId);
    } catch (e) {
      alert("Could not make that swap: " + e.message);
    }
  })();
}

// A self-contained HTML file (inlined CSS, no external requests) of
// whatever's currently in a report box - the live web UI already renders
// this, this just freezes one view into a file you can keep/share/open
// offline without the server running.
const SNAPSHOT_CSS = `
:root{--bg:#0f1613;--panel:#182622;--accent:#4caf7d;--text:#e8f1ec;--muted:#9fb8ad;--border:#2a3d36}
body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,Segoe UI,Roboto,sans-serif;padding:24px}
h1{font-size:1.3rem}h3,h4{margin-top:24px}
#scoreline{font-size:1.4rem;margin:10px 0}
#events{max-height:600px;overflow-y:auto;background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:10px;font-size:0.85rem}
#events div{padding:2px 0}
table.stats{border-collapse:collapse;margin-top:12px;width:100%}
table.stats th,table.stats td{border:1px solid var(--border);padding:6px 8px;font-size:0.82rem;text-align:left}
.muted{color:var(--muted);font-size:0.8rem}
.match-link{background:none;border:none;color:var(--text);text-decoration:underline;cursor:default;padding:2px 0;font:inherit}
`;

function downloadHtmlSnapshot(title, bodyHtml, filenameBase) {
  const doc = `<!doctype html><html><head><meta charset="utf-8"><title>${title}</title>` +
    `<style>${SNAPSHOT_CSS}</style></head><body><h1>${title}</h1>${bodyHtml}` +
    `<p class="muted">Static snapshot from What If Rugby Edition - generated ${new Date().toISOString()}.</p>` +
    `</body></html>`;
  const blob = new Blob([doc], {type: "text/html"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${filenameBase.replace(/[^A-Za-z0-9]+/g, "_") || "report"}.html`;
  a.click();
  URL.revokeObjectURL(url);
}

function snapshotButtonHtml(id) {
  return `<div class="row"><button id="${id}">Download as standalone HTML file</button></div>`;
}

// ===================== Paced event reveal (client-side only) ===============
// The server always computes a match's full event list in one shot (a
// finished match report, or whatever's happened up to the current live
// pause point) - this purely animates *revealing* it, a short delay
// between each line instead of dumping the whole list at once, plus
// "skip to next substitution" (jump the reveal cursor to the next event
// whose text mentions a substitution or injury - see match_engine.py's
// commentary wording: "Substitution:", "Tactical substitution:", or
// "Injury: ... comes on."/"no replacements left") and "skip to end"
// (reveal everything immediately - the fast path, not the only path).
const SUB_EVENT_RE = /substitution|injury/i;

// Matches a successful scoring event's commentary text ONLY - a converted
// try, a slotted conversion, or a kicked penalty (see match_engine.py's
// exact wording: "TRY! ... crosses the whitewash...", "... slots the
// conversion.", "... kicks the penalty.") - deliberately NOT a missed
// conversion/penalty ("... drifts wide."/"... is off target."), which
// should stay silent.
const SCORE_EVENT_RE = /^TRY!|slots the conversion\.|kicks the penalty\./;

// A short (~2.5s) stadium crowd-cheer burst for a qualifying score - never
// the full ~37s recording (real matches don't have 35-second gaps between
// scores). `.play()` is wrapped so a browser blocking autoplay (no prior
// user gesture) is a silent no-op, not an error.
function playCheerSound() {
  try {
    const audio = new Audio("/sfx/crowd_cheer.ogg");
    audio.play().catch(() => {});
    setTimeout(() => { try { audio.pause(); } catch (e) {} }, 2500);
  } catch (e) {}
}

// Whether a just-revealed scoring event should trigger the crowd-cheer sfx:
// - At a neutral venue (`homeAdvantageFor` falsy - no real home side,
//   e.g. Nations Championship finals, most World Cup matches, Friendly/
//   Draft/custom matches), either team's score cheers.
// - In a match with a genuine real-world home side, ONLY that home team's
//   score cheers - the away/visiting side stays silent, matching real
//   stadium atmosphere rather than a blanket "any score cheers" rule.
function shouldPlayCheer(event, homeAdvantageFor) {
  if (!event || !SCORE_EVENT_RE.test(event.text)) return false;
  if (!homeAdvantageFor) return true;
  return event.team === homeAdvantageFor;
}

function formatEventLine(e) {
  return `<div>[${e.minute}'] ${e.text} (${e.score_home}-${e.score_away})</div>`;
}

// The score AS OF the reveal cursor - i.e. the score after the last event
// actually revealed so far, not the match's true/final score. Each
// `CommentaryEvent` already carries a running score snapshot
// (`score_home`/`score_away`, see `match_engine.py`), so this is just
// "whatever the most recently revealed event says the score was", or 0-0
// if nothing has been revealed yet (cursor 0, kickoff).
function scoreAtCursor(events, cursor) {
  if (cursor <= 0 || !events.length) return {home: 0, away: 0};
  const e = events[Math.min(cursor, events.length) - 1];
  return {home: e.score_home, away: e.score_away};
}

// Rebuilds a "Home X - Y Away" scoreline string (the exact format
// `MatchResult.scoreline()` produces server-side) with a different score
// substituted in, by locating the FINAL score's "X - Y" substring and
// swapping it for the in-progress one - avoids needing the home/away team
// names as separate fields when only the finished scoreline string is on
// hand (e.g. `renderReport`'s `data.scoreline`).
function scorelineWithScore(fullScoreline, finalHome, finalAway, curHome, curAway) {
  const finalPattern = `${finalHome} - ${finalAway}`;
  const idx = fullScoreline.indexOf(finalPattern);
  if (idx === -1) return fullScoreline;
  return fullScoreline.slice(0, idx) + `${curHome} - ${curAway}` + fullScoreline.slice(idx + finalPattern.length);
}

/**
 * Drives paced reveal of `events` (starting from `startAt`, so a live
 * match's already-shown events aren't re-revealed) into `eventsEl`.
 * Returns {skipToEnd, skipToNextEvent, setDelay, isDone} for a caller's
 * control buttons to use.
 */
// `onComplete` fires once the reveal cursor first reaches the end of the
// events list - by natural playback, "Skip to end", or "Skip to next
// substitution" happening to land on the last event - whichever happens
// first. This is what lets a caller hide the final score/Player of the
// Match/box score until the viewer has actually watched (or explicitly
// skipped) their way to full time, instead of spoiling the result the
// instant the report loads.
// `homeAdvantageFor`: the match's `home_advantage_for` (the genuine home
// team's name, or null/undefined at a neutral venue - see
// `shouldPlayCheer`) - only consulted during natural tick-by-tick
// playback, never on "skip to next substitution"/"skip to end" (which can
// jump over, or instantly reveal, many events at once - playing a cheer
// per skipped-over score would spam N sounds simultaneously).
function pacedEventReveal(eventsEl, events, startAt, delayMs, onComplete, onScoreUpdate, homeAdvantageFor) {
  let cursor = startAt || 0;
  let delay = delayMs || 650;
  let timer = null;
  let completed = false;

  function paint() {
    eventsEl.innerHTML = events.slice(0, cursor).map(formatEventLine).join("");
    eventsEl.scrollTop = eventsEl.scrollHeight;
    if (onScoreUpdate) {
      const s = scoreAtCursor(events, cursor);
      onScoreUpdate(s.home, s.away);
    }
  }
  function stop() {
    if (timer) { clearInterval(timer); timer = null; }
  }
  function checkComplete() {
    if (!completed && cursor >= events.length) {
      completed = true;
      if (onComplete) onComplete();
    }
  }
  function tick() {
    if (cursor >= events.length) { stop(); return; }
    cursor++;
    if (shouldPlayCheer(events[cursor - 1], homeAdvantageFor)) playCheerSound();
    paint();
    if (cursor >= events.length) stop();
    checkComplete();
  }
  function start() {
    stop();
    if (cursor < events.length) timer = setInterval(tick, delay);
  }

  paint();
  checkComplete();
  start();

  return {
    skipToEnd() { cursor = events.length; paint(); stop(); checkComplete(); },
    skipToNextEvent() {
      let idx = -1;
      for (let i = cursor; i < events.length; i++) {
        if (SUB_EVENT_RE.test(events[i].text)) { idx = i; break; }
      }
      const found = idx >= 0;
      cursor = found ? idx + 1 : events.length;
      paint();
      if (cursor >= events.length) stop();
      checkComplete();
      return found;
    },
    setDelay(ms) { delay = ms; if (timer) start(); },
    isDone() { return cursor >= events.length; },
    stop,
  };
}

const PLAYBACK_SPEEDS = [
  {label: "Slower", ms: 1400},
  {label: "Normal", ms: 650},
  {label: "Faster", ms: 250},
];

// `withSkipButtons` (default true): the plain, already-fully-simulated
// report view (friendly/draft/tournament-detail matches run without the
// live-pause toggle) knows its ENTIRE event list up front, so "skip to next
// substitution"/"skip to end" are unambiguous local operations over that
// full list. The live/pausable view (`renderLiveMatchState`) only ever
// knows the small handful of events in the *current* paused chunk (since
// future minutes haven't been simulated yet) - reusing these same two
// buttons there made "skip to next substitution" and "skip to end" often
// reveal the exact same tiny chunk (confusingly identical), since there's
// nothing meaningfully different to skip *to* within 1-4 minutes of drives.
// The live view instead gets its own, unambiguous backend-driven controls
// (see `renderLiveMatchState`'s "Skip to next substitution point"/"Skip to
// end of match" buttons) and passes `withSkipButtons: false` here to keep
// only the speed selector (still a nice touch for animating a chunk's
// reveal) without the confusing duplicate skip buttons.
function playbackControlsHtml(idPrefix, withSkipButtons) {
  const skipButtons = withSkipButtons === false ? "" : `
      <button id="${idPrefix}-skip-sub">Skip to next substitution</button>
      <button id="${idPrefix}-skip-end">Skip to end</button>`;
  return `
    <div class="row">
      <label class="muted">Playback speed:
        <select id="${idPrefix}-speed">
          ${PLAYBACK_SPEEDS.map((s, i) => `<option value="${s.ms}" ${i === 1 ? "selected" : ""}>${s.label}</option>`).join("")}
        </select>
      </label>${skipButtons}
    </div>`;
}

function wirePlaybackControls(idPrefix, reveal) {
  const speedSel = document.getElementById(`${idPrefix}-speed`);
  const skipSubBtn = document.getElementById(`${idPrefix}-skip-sub`);
  const skipEndBtn = document.getElementById(`${idPrefix}-skip-end`);
  if (speedSel) speedSel.onchange = () => reveal.setDelay(parseInt(speedSel.value, 10));
  if (skipSubBtn) {
    skipSubBtn.onclick = () => {
      const found = reveal.skipToNextEvent();
      const status = document.getElementById(`${idPrefix}-skip-status`);
      if (status) {
        setStatus(status, found ? "" : "No more injuries/substitutions in this match - showing full time.");
      }
    };
  }
  if (skipEndBtn) skipEndBtn.onclick = () => reveal.skipToEnd();
}

// `startRevealed`: true skips the paced-reveal animation entirely, showing
// every event and the final score/stats immediately. Used when a live/
// pausable match (friendly, tournament, or draft) finishes - the user
// already watched it unfold checkpoint by checkpoint (or explicitly chose
// "Skip to end of match"), so re-animating the *entire* match from minute 0
// here would be a confusing, redundant ~30-second replay, not a reveal of
// anything new. A genuinely fresh, never-before-seen report (a plain
// "Run match" with no live toggle, or a tournament match clicked open from
// "Results so far") still animates from 0 by default.
function renderReport(data, targetId, startRevealed) {
  const box = document.getElementById(targetId || "report");
  const statRows = Object.entries(data.stats).map(([name, s]) => `
    <tr><td>${name}</td><td>${s.tries}</td><td>${s.penalty_goals}</td><td>${s.drop_goals}</td>
    <td>${s.turnovers_won}</td><td>${s.handling_errors}</td><td>${s.penalties_conceded}</td>
    <td>${s.yellow_cards}/${s.red_cards}</td><td>${s.territory_pct}%</td>
    <td>${s.injuries}</td><td>${s.substitutions}</td></tr>`).join("");
  const pomLine = data.player_of_the_match
    ? `<p><strong>Player of the Match:</strong> ${data.player_of_the_match.name} (${data.player_of_the_match.nation}, ${data.player_of_the_match.natural_position})</p>`
    : "";
  const scorerRows = (data.top_scorers || []).slice(0, 6).map(s =>
    `<tr><td>${s.name}</td><td>${s.team}</td><td>${s.points}</td><td>${s.tries}</td><td>${s.conversions}</td><td>${s.penalty_goals}</td></tr>`
  ).join("");
  // "Injuries this match" - a clear, standalone section (not just buried in
  // the commentary log, see task notes) built straight from `data.injuries`
  // (`MatchResult.injury_details` server-side - who, which team, which
  // position, at what minute).
  const injuryRows = (data.injuries || []).map(inj => `
    <tr><td>${inj.minute}'</td><td>${inj.team}</td><td>${inj.player}</td><td>${inj.position}</td>
    <td>${inj.severity || ""}</td><td>${layoffText(inj.layoff_matches)}</td></tr>`
  ).join("");
  const injuryHtml = injuryRows
    ? `<h3>Injuries this match</h3><table class="stats">
        <tr><th>Minute</th><th>Team</th><th>Player</th><th>Position</th><th>Severity</th><th>Expected out</th></tr>
        ${injuryRows}
      </table>`
    : "";
  // "Cards this match" - same convention as "Injuries this match" above,
  // built from `data.cards` (`MatchResult.card_details` server-side). A red
  // card that came from a second yellow to the same player is flagged so
  // it doesn't read like an ordinary straight red (see README/engine).
  const cardRows = (data.cards || []).map(c => `
    <tr><td>${c.minute}'</td><td>${c.team}</td><td>${c.player}</td>
    <td>${c.card_type === "red" ? "Red" : "Yellow"}</td>
    <td>${c.escalated_second_yellow ? "2nd yellow - sent off" : ""}</td></tr>`
  ).join("");
  const cardHtml = cardRows
    ? `<h3>Cards this match</h3><table class="stats">
        <tr><th>Minute</th><th>Team</th><th>Player</th><th>Card</th><th>Note</th></tr>
        ${cardRows}
      </table>`
    : "";
  const playbackId = `${targetId || "report"}-playback`;
  const fullEventsHtml = data.events.map(formatEventLine).join("");
  // `reportHtml` (used for the downloadable snapshot) always shows every
  // event - the paced reveal is a live-viewing animation only, never a
  // reason to ship an incomplete snapshot.
  const reportHtml = `
    <div id="scoreline">${data.scoreline}</div>
    ${pomLine}
    <div id="events">${fullEventsHtml}</div>
    <table class="stats">
      <tr><th>Team</th><th>Tries</th><th>Pens</th><th>DGs</th><th>Turnovers</th><th>Errors</th>
      <th>Pens conceded</th><th>Cards Y/R</th><th>Territory</th><th>Injuries</th><th>Subs</th></tr>
      ${statRows}
    </table>
    ${scorerRows ? `<h3>Top scorers</h3><table class="stats">
      <tr><th>Player</th><th>Team</th><th>Pts</th><th>Tries</th><th>Conv</th><th>Pens</th></tr>
      ${scorerRows}
    </table>` : ""}
    ${injuryHtml}
    ${cardHtml}`;
  // The final score/Player of the Match/box score are spoilers - they stay
  // hidden (`spoilersId`, class "hidden") until the paced reveal actually
  // reaches full time (naturally, or via "Skip to end"/"Skip to next
  // substitution" happening to land there), so watching the commentary
  // unfold still has suspense instead of giving the result away instantly.
  const spoilersId = `${playbackId}-spoilers`;
  const liveHtml = `
    ${playbackControlsHtml(playbackId)}
    <div class="row muted" id="${playbackId}-skip-status"></div>
    <div id="${playbackId}-events" class="events"></div>
    <div id="${spoilersId}" class="${startRevealed ? "" : "hidden"}">
      <div id="scoreline">${data.scoreline}</div>
      ${pomLine}
      <table class="stats">
        <tr><th>Team</th><th>Tries</th><th>Pens</th><th>DGs</th><th>Turnovers</th><th>Errors</th>
        <th>Pens conceded</th><th>Cards Y/R</th><th>Territory</th><th>Injuries</th><th>Subs</th></tr>
        ${statRows}
      </table>
      ${scorerRows ? `<h3>Top scorers</h3><table class="stats">
        <tr><th>Player</th><th>Team</th><th>Pts</th><th>Tries</th><th>Conv</th><th>Pens</th></tr>
        ${scorerRows}
      </table>` : ""}
      ${injuryHtml}
    </div>`;
  const snapshotBtnId = `${targetId || "report"}-snapshot-btn`;
  box.innerHTML = liveHtml + snapshotButtonHtml(snapshotBtnId);
  document.getElementById(snapshotBtnId).onclick = () => {
    downloadHtmlSnapshot(data.scoreline, reportHtml, data.scoreline);
  };
  const eventsEl = document.getElementById(`${playbackId}-events`);
  const reveal = startPacedReveal(playbackId, eventsEl, data.events, startRevealed ? data.events.length : 0, undefined, () => {
    const spoilers = document.getElementById(spoilersId);
    if (spoilers) spoilers.classList.remove("hidden");
  }, (h, a) => {
    // The spoilers scoreline stays hidden until the reveal completes (see
    // above), but keep its text in sync with the reveal cursor the whole
    // time anyway, same as the always-visible live-match scoreboard - so
    // the instant it's unhidden (naturally or via a skip) it already shows
    // the right (by then final) score, never a stale one.
    const spoilersScoreline = document.querySelector(`#${spoilersId} #scoreline`);
    if (spoilersScoreline) spoilersScoreline.textContent = scorelineWithScore(data.scoreline, data.score_home, data.score_away, h, a);
  }, data.home_advantage_for);
  wirePlaybackControls(playbackId, reveal);
}

// ===================== Tournament mode =====================

let tournamentOptions = null;
let squadModeEnabled = false; // "fresh squad every match" toggle, see setupTournamentUI
// name -> TeamBuilder (fixed-lineup mode) | {teamId, name} | {squadPlayerIds, name} (squad mode)
const tournamentBuilders = {};

const TOURNAMENT_TYPE_CARDS = [
  {ttype: "real", title: "Real fixture replay", desc: "Replay the actual fixture list for a real competition (Six Nations, Rugby Championship, Nations Championship, Autumn Nations Series) and season."},
  {ttype: "wc2027", title: "2027 Rugby World Cup", desc: "24 teams, the real pool draw - play it out before it's happened for real."},
  {ttype: "historical", title: "Historical Rugby World Cup", desc: "Every real edition, 1995-2023, with that year's real squads."},
  {ttype: "historical_sn", title: "Historical Six Nations", desc: "2009-2021, with that year's real squads."},
  {ttype: "custom", title: "Custom tournament", desc: "Pick any teams yourself - round robin, home & away, or pool + knockout."},
];

async function setupTournamentUI() {
  tournamentOptions = await api("/api/tournament/options");
  renderTournamentTypePicker();
}

function renderTournamentTypePicker() {
  const container = document.getElementById("tournament-section");
  container.innerHTML = `
    <h2>Tournament mode</h2>
    <div class="row">
      <label class="muted"><input type="checkbox" id="squad-mode-toggle" ${squadModeEnabled ? "checked" : ""}> Fresh squad every match
        (auto-draft a new best XV before each match from each team's full pool - an injury/red
        card sidelines that player for the team's next match, instead of one fixed lineup for the
        whole tournament)</label>
    </div>
    <div class="card-grid" id="tournament-type-cards"></div>
    <div id="tournament-config"></div>
    <div id="tournament-teams"></div>
    <div id="tournament-run-area"></div>
    <div id="tournament-report"></div>`;
  document.getElementById("squad-mode-toggle").onchange = (e) => { squadModeEnabled = e.target.checked; };
  const cardsBox = document.getElementById("tournament-type-cards");
  cardsBox.innerHTML = TOURNAMENT_TYPE_CARDS.map(c => `
    <button class="card" data-ttype="${c.ttype}">
      <span class="card-title">${c.title}</span>
      <span class="card-desc">${c.desc}</span>
    </button>`).join("");
  cardsBox.querySelectorAll("[data-ttype]").forEach(btn => {
    btn.onclick = () => {
      const chosen = TOURNAMENT_TYPE_CARDS.find(c => c.ttype === btn.dataset.ttype);
      navTo("tournament-type-" + chosen.ttype, chosen.title, () => {
        showScreen("screen-tournament");
        renderTournamentTypeScreen(chosen.ttype);
      });
    };
  });
}

function renderTournamentTypeScreen(ttype) {
  const container = document.getElementById("tournament-section");
  container.innerHTML = `
    <div class="row"><button id="tournament-back-to-types">&laquo; Choose a different tournament type</button></div>
    <div id="tournament-config"></div>
    <div id="tournament-teams"></div>
    <div id="tournament-run-area"></div>
    <div id="tournament-report"></div>`;
  document.getElementById("tournament-back-to-types").onclick = () => {
    navStack.pop();
    navStack[navStack.length - 1].onShow();
    renderBreadcrumb();
  };
  renderTournamentConfig(ttype);
}

function renderTournamentConfig(ttype) {
  const cfg = document.getElementById("tournament-config");
  document.getElementById("tournament-teams").innerHTML = "";
  document.getElementById("tournament-run-area").innerHTML = "";
  document.getElementById("tournament-report").innerHTML = "";

  if (ttype === "real") {
    cfg.innerHTML = `
      <p class="muted">Pick a competition and season, then pick which team(s)
      you want to draft yourself - every other team auto-drafts its own real
      pool's best XV, so you don't have to build all of them.</p>
      <div class="row">
        <label class="muted">Season: ${seasonSelectHtml("t-real-season", tournamentOptions.default_season)}</label>
      </div>
      <div class="card-grid" id="t-real-cards"></div>
      <span class="muted" id="t-real-status"></span>`;
    const cardsBox = document.getElementById("t-real-cards");
    cardsBox.innerHTML = tournamentOptions.real_keys.map(key => `
      <button class="card" data-key="${key}">
        <span class="card-title">${(tournamentOptions.real_key_names || {})[key] || key}</span>
      </button>`).join("");
    cardsBox.querySelectorAll("[data-key]").forEach(btn => {
      btn.onclick = async () => {
        const key = btn.dataset.key;
        const season = document.getElementById("t-real-season").value || tournamentOptions.default_season;
        const status = document.getElementById("t-real-status");
        setStatus(status, "loading fixture list...");
        try {
          const res = await api(`/api/tournament/real/teams?key=${encodeURIComponent(key)}&season=${encodeURIComponent(season)}`);
          setStatus(status, `${res.teams.length} teams in this competition.`);
          const entries = res.teams.map(name => ({name, code: res.code_by_nation[name], season}));
          buildTournamentTeamPanels(entries);
          renderTournamentRunArea({type: "real", key, season});
        } catch (e) {
          showError(status, "Error: " + e.message);
        }
      };
    });
  } else if (ttype === "wc2027") {
    cfg.innerHTML = `<p class="muted">24 teams, 6 real pools (see README). Pick which team(s)
      you want to draft yourself - the rest auto-draft their own real 2026 pool's best XV.</p>
      <div class="row">
        <label class="muted">Fixture order:
          <select id="t-wc-mode"><option value="specific">Specific (drawn order)</option><option value="random">Random</option></select>
        </label>
      </div>`;
    const wc = tournamentOptions.world_cup_2027;
    const entries = wc.teams.map(name => ({name, code: wc.code_by_nation[name]}));
    buildTournamentTeamPanels(entries);
    renderTournamentRunArea({type: "world_cup_2027"});
  } else if (ttype === "historical") {
    cfg.innerHTML = `
      <div class="row">
        <select id="t-hist-year"></select>
        <button id="t-hist-load">Load this World Cup's real squads</button>
        <span class="muted" id="t-hist-status"></span>
      </div>
      <p class="muted">Real pool draw + every participant's real roster from that edition's
      Wikipedia squads page (pre-2018 ratings are a position-archetype estimate scaled by that
      union's competitiveness, not scouted - see README). Pick which team(s) you want to draft
      yourself; the rest auto-draft their own real squad's best XV.</p>`;
    api("/api/historical_rwc/years").then(res => {
      const sel = document.getElementById("t-hist-year");
      if (!sel) return;
      sel.innerHTML = res.years.map(y => `<option value="${y}">${y}</option>`).join("");
    });
    document.getElementById("t-hist-load").onclick = async () => {
      const year = document.getElementById("t-hist-year").value;
      const status = document.getElementById("t-hist-status");
      setStatus(status, "loading real squads from Wikipedia (first time is network-heavy, ~20 teams - cached after)...");
      try {
        const res = await api(`/api/historical_rwc/${year}`);
        const teamNames = Object.keys(res.squads);
        setStatus(status, `${teamNames.length} teams - pools: ` +
          Object.entries(res.pools).map(([p, ts]) => `${p}: ${ts.join(", ")}`).join(" | "));
        const entries = teamNames.map(name => ({name, fixedPool: res.squads[name]}));
        buildTournamentTeamPanels(entries);
        renderTournamentRunArea({type: "historical_world_cup", year: parseInt(year, 10)});
      } catch (e) {
        showError(status, "Error: " + e.message);
      }
    };
  } else if (ttype === "historical_sn") {
    cfg.innerHTML = `
      <div class="row">
        <select id="t-hsn-year"></select>
        <button id="t-hsn-load">Load this edition's real squads</button>
        <span class="muted" id="t-hsn-status"></span>
      </div>
      <p class="muted">Real squads from that edition's Wikipedia squads page (pre-rugbydata era,
      archetype-based ratings where no real stats cross-reference - see README). Fixture order
      is a synthetic round-robin, not the real historical match order (not recoverable from this
      page). Pick which team(s) you want to draft yourself; the rest auto-draft their best XV.</p>`;
    api("/api/historical_six_nations/years").then(res => {
      const sel = document.getElementById("t-hsn-year");
      if (!sel) return;
      sel.innerHTML = res.years.map(y => `<option value="${y}">${y}</option>`).join("");
    });
    document.getElementById("t-hsn-load").onclick = async () => {
      const year = document.getElementById("t-hsn-year").value;
      const status = document.getElementById("t-hsn-status");
      setStatus(status, "loading real squads from Wikipedia (first time is network-heavy - cached after)...");
      try {
        const res = await api(`/api/historical_six_nations/${year}`);
        const teamNames = Object.keys(res.squads);
        setStatus(status, `${teamNames.length} teams loaded.`);
        const entries = teamNames.map(name => ({name, fixedPool: res.squads[name]}));
        buildTournamentTeamPanels(entries);
        renderTournamentRunArea({type: "historical_six_nations", year: parseInt(year, 10)});
      } catch (e) {
        showError(status, "Error: " + e.message);
      }
    };
  } else if (ttype === "custom") {
    cfg.innerHTML = `
      <div class="row">
        <label class="muted">Total teams: <input type="number" id="t-custom-total" value="4" style="width:60px"></label>
        <label class="muted">How many will you draft yourself: <input type="number" id="t-custom-mine" value="1" style="width:60px"></label>
        <button id="t-custom-setup">Set up teams</button>
      </div>
      <p class="muted">The rest default to a suggested strong union's auto-drafted best XV, but
      each one is editable - pick a different union, a specific season, or the Legends (Hall of
      Fame) roster instead - so you only have to build the ones you care about by hand.</p>
      <div id="t-custom-names-area"></div>
      <div class="row">
        <label class="muted">Order:
          <select id="t-custom-order"><option value="specific">As set up</option><option value="random">Random</option></select>
        </label>
        <label class="muted">Format:
          <select id="t-custom-format">
            <option value="round_robin">Round robin</option>
            <option value="round_robin_home_away">Round robin (home+away)</option>
            <option value="pool_knockout">Pools + knockout</option>
          </select>
        </label>
        <label class="muted">Pools: <input type="number" id="t-custom-pools" value="2" style="width:50px"></label>
      </div>`;
    document.getElementById("t-custom-setup").onclick = () => {
      const total = parseInt(document.getElementById("t-custom-total").value || "4", 10);
      const mine = Math.min(parseInt(document.getElementById("t-custom-mine").value || "1", 10), total);
      const namesArea = document.getElementById("t-custom-names-area");
      namesArea.innerHTML = Array.from({length: mine}, (_, i) =>
        `<input type="text" class="t-custom-myname" placeholder="Your team ${i + 1} name" style="margin:3px">`
      ).join("") + ` <button id="t-custom-confirm">Confirm teams</button>`;
      document.getElementById("t-custom-confirm").onclick = () => {
        const myNames = Array.from(document.querySelectorAll(".t-custom-myname")).map(i => i.value.trim()).filter(Boolean);
        if (myNames.length !== mine) { alert(`Enter all ${mine} of your team names.`); return; }

        const fillOrder = tournamentOptions.strong_unions_fill_order;
        const autoCount = total - mine;
        const autoEntries = [];
        for (let i = 0; i < autoCount; i++) {
          const code = fillOrder[i % fillOrder.length];
          const union = UNIONS.find(u => u.code === code);
          // "auto_pick": auto-drafted for you, but you can change which
          // union/season (or use the Legends roster instead) before it runs -
          // not locked to the suggested fill-order team.
          autoEntries.push({name: union ? union.name : code, code, forceMode: "auto_pick"});
        }
        const manualEntries = myNames.map(n => ({name: n, forceMode: "manual"}));
        buildTournamentTeamPanels([...manualEntries, ...autoEntries]);
        renderTournamentRunArea({type: "custom"});
      };
    };
  }
}

/**
 * entries: [{name, code?, season?, forceMode?: "manual"|"auto"}]
 * Each team defaults to a choice between auto-drafting its own real pool's
 * best XV (one click, instant) or drafting it yourself (expands a normal
 * TeamBuilder panel) - `forceMode` skips straight to one or the other
 * (used by the custom-tournament flow, where that choice was already made
 * by picking "how many will you draft yourself").
 */
/**
 * Squad-mode team panel: pick a union+season (or Legends), fetch that
 * pool's player ids, and register it as this team's squad - no lineup
 * drafting here, `Tournament(squads=...)` auto-drafts a fresh best XV
 * from this exact pool before every match it plays.
 */
function renderSquadPicker(row, entry) {
  const name = entry.name;
  // Placeholder so "still need" correctly lists this team until a pool is
  // actually loaded - without this, a team that never got a pool loaded
  // simply has no key in tournamentBuilders at all, and the hint (which
  // only checks teams it already knows about) wrongly says "All teams
  // ready" even though nothing was registered for it.
  tournamentBuilders[name] = {squadPlayerIds: null, name};
  row.innerHTML = `
    <div class="row">
      <span class="sp-logo">${logoImgHtml(entry.code || name, 24)}</span>
      <strong>${name}</strong>
      <label class="muted"><input type="checkbox" class="sp-legends"> Legends (Hall of Fame) instead</label>
    </div>
    <div class="row sp-union-row">
      <select class="sp-union">${UNIONS.map(u => `<option value="${u.code}" ${u.code === entry.code ? "selected" : ""}>${u.code} - ${u.name}</option>`).join("")}</select>
      ${seasonSelectHtml("", entry.season || "2026").replace('<select id="">', '<select class="sp-season">')}
    </div>
    <div class="row">
      <button class="sp-go">Load pool</button>
      <span class="muted sp-status"></span>
    </div>`;
  const legendsCb = row.querySelector(".sp-legends");
  const unionRow = row.querySelector(".sp-union-row");
  const spLogo = row.querySelector(".sp-logo");
  const spUnion = row.querySelector(".sp-union");
  const status = row.querySelector(".sp-status");
  spUnion.onchange = () => { spLogo.innerHTML = logoImgHtml(spUnion.value, 24); };
  legendsCb.onchange = () => { unionRow.style.display = legendsCb.checked ? "none" : ""; };
  updateTournamentRunHint();
  row.querySelector(".sp-go").onclick = async () => {
    setStatus(status, "loading...");
    try {
      const players = legendsCb.checked
        ? await api("/api/legends")
        : await api(`/api/pool/${spUnion.value}?season=${encodeURIComponent(row.querySelector(".sp-season").value)}`);
      tournamentBuilders[name] = {squadPlayerIds: players.map(p => p.id), name};
      setStatus(status, `${players.length} players in the pool - ready.`);
      updateTournamentRunHint();
    } catch (e) {
      showError(status, "Error: " + e.message);
    }
  };
}

function buildTournamentTeamPanels(entries) {
  const area = document.getElementById("tournament-teams");
  area.innerHTML = `<div id="tournament-panels"></div>`;
  const panelsDiv = document.getElementById("tournament-panels");
  for (const key of Object.keys(tournamentBuilders)) delete tournamentBuilders[key];

  for (const entry of entries) {
    const name = entry.name;
    const rowId = "tt_" + name.replace(/[^A-Za-z0-9]/g, "_") + "_" + Math.random().toString(36).slice(2, 7);
    const row = document.createElement("div");
    row.className = "panel";
    row.id = `panel-${rowId}`;
    panelsDiv.appendChild(row);

    if (squadModeEnabled) {
      if (entry.fixedPool) {
        // Already a known pool (a historical squad, or the 2027 draw's
        // suggested union) - nothing to pick, just use it as the squad.
        tournamentBuilders[name] = {squadPlayerIds: entry.fixedPool.map(p => p.id), name};
        row.innerHTML = `${logoImgHtml(name, 24)}<strong>${name}</strong> ` +
          `<span class="muted">squad ready (${entry.fixedPool.length} players - fresh XV drafted each match)</span>`;
        updateTournamentRunHint();
      } else {
        renderSquadPicker(row, entry);
      }
      continue;
    }

    const runAutoDraft = async () => {
      row.innerHTML = `<strong>${name}</strong> <span class="muted">auto-drafting...</span>`;
      try {
        const res = entry.fixedPool
          ? await api("/api/team/auto_from_ids", {
              method: "POST", headers: {"Content-Type": "application/json"},
              body: JSON.stringify({name, player_ids: entry.fixedPool.map(p => p.id)}),
            })
          : await api("/api/team/auto", {
              method: "POST", headers: {"Content-Type": "application/json"},
              body: JSON.stringify({name, code: entry.code, season: entry.season}),
            });
        tournamentBuilders[name] = {teamId: res.team_id, name};
        row.innerHTML = `${logoImgHtml(res.code || name, 24)}<strong>${name}</strong> <span class="muted">auto-drafted${res.code ? " (" + res.code + ")" : ""}${res.problems.length ? " - " + res.problems.join("; ") : " - ready"}</span>`;
        updateTournamentRunHint();
      } catch (e) {
        row.innerHTML = `<strong>${name}</strong> <span class="muted">Error: ${e.message}</span>`;
      }
    };
    const startManualDraft = () => {
      row.innerHTML = "";
      const builderDiv = document.createElement("div");
      builderDiv.id = `panel-${rowId}_builder`;
      row.appendChild(builderDiv);
      const builder = new TeamBuilder(`${rowId}_builder`, {title: name, fixedName: name, fixedPool: entry.fixedPool || null});
      tournamentBuilders[name] = builder;
    };

    const runAutoDraftFromPicker = async (code, season, useLegends) => {
      row.innerHTML = `<strong>${name}</strong> <span class="muted">auto-drafting...</span>`;
      try {
        let res;
        if (useLegends) {
          const legends = await api("/api/legends");
          res = await api("/api/team/auto_from_ids", {
            method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify({name, player_ids: legends.map(p => p.id)}),
          });
        } else {
          res = await api("/api/team/auto", {
            method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify({name, code, season}),
          });
        }
        tournamentBuilders[name] = {teamId: res.team_id, name};
        row.innerHTML = `${logoImgHtml(res.code || name, 24)}<strong>${name}</strong> <span class="muted">auto-drafted${res.code ? " (" + res.code + ")" : useLegends ? " (Legends)" : ""}${res.problems.length ? " - " + res.problems.join("; ") : " - ready"}</span>
          <button class="redo-pick">Change team/year...</button>`;
        row.querySelector(".redo-pick").onclick = renderAutoPicker;
        updateTournamentRunHint();
      } catch (e) {
        row.innerHTML = `<strong>${name}</strong> <span class="muted">Error: ${e.message}</span> <button class="redo-pick">Try again</button>`;
        row.querySelector(".redo-pick").onclick = renderAutoPicker;
      }
    };

    function renderAutoPicker() {
      tournamentBuilders[name] = {teamId: null, name}; // placeholder so "still need" hints count it until confirmed
      row.innerHTML = `
        <div class="row">
          <strong>${name}</strong> <span class="muted">(auto-fills with a suggested union - change it here if you want a different one, a specific season, or the Legends roster)</span>
        </div>
        <div class="row">
          <label class="muted"><input type="checkbox" class="ap-legends"> Legends (Hall of Fame) instead</label>
        </div>
        <div class="row ap-union-row">
          <span class="ap-logo">${logoImgHtml(entry.code, 24)}</span>
          <select class="ap-union">${UNIONS.map(u => `<option value="${u.code}" ${u.code === entry.code ? "selected" : ""}>${u.code} - ${u.name}</option>`).join("")}</select>
          ${seasonSelectHtml("", "2026").replace('<select id="">', '<select class="ap-season">')}
        </div>
        <div class="row">
          <button class="ap-go">Auto-draft</button>
        </div>`;
      const legendsCb = row.querySelector(".ap-legends");
      const unionRow = row.querySelector(".ap-union-row");
      const apLogo = row.querySelector(".ap-logo");
      const apUnionSel = row.querySelector(".ap-union");
      apUnionSel.onchange = () => { apLogo.innerHTML = logoImgHtml(apUnionSel.value, 24); };
      legendsCb.onchange = () => { unionRow.style.display = legendsCb.checked ? "none" : ""; };
      row.querySelector(".ap-go").onclick = () => {
        const useLegends = legendsCb.checked;
        const code = row.querySelector(".ap-union").value;
        const season = row.querySelector(".ap-season").value;
        runAutoDraftFromPicker(code, season, useLegends);
      };
      updateTournamentRunHint();
    }

    if (entry.forceMode === "auto_pick") {
      renderAutoPicker();
    } else if (entry.forceMode === "auto") {
      runAutoDraft();
    } else if (entry.forceMode === "manual") {
      startManualDraft();
    } else {
      row.innerHTML = `
        <div class="row">
          <strong>${name}</strong>
          <button data-act="auto">Auto-draft (recommended)</button>
          <button data-act="manual">Draft yourself</button>
        </div>`;
      row.querySelector('[data-act="auto"]').onclick = runAutoDraft;
      row.querySelector('[data-act="manual"]').onclick = startManualDraft;
    }
  }
}

function updateTournamentRunHint() {
  const hint = document.getElementById("t-run-hint");
  if (!hint) return;
  const missing = Object.entries(tournamentBuilders)
    .filter(([, b]) => !b.teamId && !b.squadPlayerIds)
    .map(([name]) => name);
  setStatus(hint, missing.length ? `Still need: ${missing.join(", ")}` : "All teams ready.", missing.length > 0);
  updateMyTeamSelect();
}

// The "Which team is mine?" dropdown is (re)built from tournamentBuilders'
// *current* keys every time a team panel changes - buildTournamentTeamPanels
// clears tournamentBuilders and refills it asynchronously as each team gets
// auto-drafted/drafted/loaded, so populating this dropdown only once, right
// after the panels are first rendered, would always see it empty.
function updateMyTeamSelect() {
  const sel = document.getElementById("t-my-team");
  if (!sel) return;
  const previous = sel.value;
  const teamNames = Object.keys(tournamentBuilders);
  sel.innerHTML = `<option value="">(none - just simulate)</option>` +
    teamNames.map(n => `<option value="${n}">${n}</option>`).join("");
  if (teamNames.includes(previous)) sel.value = previous;
}

function tournamentRunBody(params) {
  const team_ids = {};
  const squad_player_ids = {};
  for (const [name, builder] of Object.entries(tournamentBuilders)) {
    if (builder.squadPlayerIds) { squad_player_ids[name] = builder.squadPlayerIds; }
    else if (builder.teamId) { team_ids[name] = builder.teamId; }
    else { throw new Error(`Finish setting up team "${name}" first.`); }
  }
  const seedRaw = document.getElementById("t-seed").value;
  const body = {type: params.type, team_ids, squad_player_ids, seed: seedRaw ? parseInt(seedRaw, 10) : null};
  if (params.type === "real") { body.key = params.key; body.season = params.season; }
  if (params.type === "world_cup_2027") { body.fixture_mode = document.getElementById("t-wc-mode").value; }
  if (params.type === "historical_world_cup") { body.year = params.year; }
  if (params.type === "historical_six_nations") { body.year = params.year; }
  if (params.type === "custom") {
    body.format = document.getElementById("t-custom-format").value;
    body.pool_count = parseInt(document.getElementById("t-custom-pools").value || "2", 10);
  }
  return body;
}

function renderTournamentRunArea(params) {
  const area = document.getElementById("tournament-run-area");
  const teamNames = Object.keys(tournamentBuilders);
  area.innerHTML = `
    <div class="row">
      <label class="muted">Seed (optional): <input type="number" id="t-seed" style="width:90px"></label>
      <button id="t-run">Run tournament</button>
      <label class="muted">Which team is mine?
        <select id="t-my-team">
          <option value="">(none - just simulate)</option>
          ${teamNames.map(n => `<option value="${n}">${n}</option>`).join("")}
        </select>
      </label>
      <button id="t-run-interactive">Play my matches</button>
      <span class="muted" id="t-run-hint"></span>
      <span class="muted" id="t-run-status"></span>
    </div>
    <div id="tournament-stage-banner"></div>
    <div id="tournament-live-area"></div>
    <div id="tournament-progress"></div>`;
  updateTournamentRunHint();

  document.getElementById("t-run").onclick = async () => {
    const status = document.getElementById("t-run-status");
    document.getElementById("tournament-live-area").innerHTML = "";
    let body;
    try {
      body = tournamentRunBody(params);
    } catch (e) {
      showError(status, e.message);
      return;
    }
    setStatus(status, "running...");
    try {
      const report = await api("/api/tournament/run", {
        method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body),
      });
      renderTournamentReport(report);
      setStatus(status, "");
    } catch (e) {
      showError(status, "Error: " + e.message);
    }
  };

  document.getElementById("t-run-interactive").onclick = async () => {
    const status = document.getElementById("t-run-status");
    document.getElementById("tournament-report").innerHTML = "";
    let body;
    try {
      body = tournamentRunBody(params);
    } catch (e) {
      showError(status, e.message);
      return;
    }
    const myTeam = document.getElementById("t-my-team").value || null;
    body.my_team = myTeam;
    setStatus(status, "starting tournament...");
    try {
      const state = await api("/api/tournament/start", {
        method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body),
      });
      handleTournamentSessionState(state, status, myTeam);
    } catch (e) {
      showError(status, "Error: " + e.message);
    }
  };
}

// Drives an interactive tournament session forward: shows the live-match
// UI (same `renderLiveMatchState` the single-friendly live match uses)
// whenever the session is paused on the user's own fixture, resumes the
// tournament once that match is finished, and keeps doing so - fully
// auto-simming everyone else's matches in between, invisibly, on the
// server - until the session reports "finished" (or "error").
// A collapsible section: starts collapsed (`open` false) unless noted
// otherwise, clicking the header toggles it - so a long-running tournament's
// standings/results don't all dump on screen at once.
function collapsibleHtml(id, title, bodyHtml, open) {
  return `
    <div class="collapsible-header" data-collapsible="${id}">
      <span>${title}</span><span class="chevron" data-chevron="${id}">${open ? "▾" : "▸"}</span>
    </div>
    <div class="collapsible-body ${open ? "" : "hidden"}" id="collapsible-body-${id}">${bodyHtml}</div>`;
}

function wireCollapsibles(box) {
  box.querySelectorAll("[data-collapsible]").forEach(header => {
    header.onclick = () => {
      const id = header.dataset.collapsible;
      const body = document.getElementById(`collapsible-body-${id}`);
      const chevron = box.querySelector(`[data-chevron="${id}"]`);
      const nowOpen = body.classList.toggle("hidden") === false;
      if (chevron) chevron.textContent = nowOpen ? "▾" : "▸";
    };
  });
}

// Shared by the interactive tournament's live progress view and the final
// (interactive AND non-interactive /api/tournament/run) report - every
// injury recorded so far, which team, which match (links to that match's
// full report the same way "Results so far" rows already do).
// "Expected out": at the moment the injury happened, this many of that
// team's matches (this match itself doesn't count); 0 ("knock") means it
// never actually cost them a match. See `engine/match_engine.py`'s
// INJURY_SEVERITY_TIERS for the honest, documented severity table this
// number comes from - never a continuous/invented recovery estimate.
function layoffText(matches) {
  if (matches === undefined || matches === null) return "";
  return matches > 0 ? `out ${matches} match${matches === 1 ? "" : "es"}` : "played through";
}

function injuryReportTable(injuryReport) {
  const rows = injuryReport.map(inj => {
    // `matches_remaining` is LIVE (as of right now, in this tournament's
    // current state) - can be less than `layoff_matches` (the original
    // tier roll) if further matches have already been played since the
    // injury happened; it's only present when the server had a running
    // tournament's availability ledger to read it from (see
    // `_injury_report_json` in webapp.py).
    const remaining = inj.matches_remaining;
    const statusText = remaining === undefined
      ? layoffText(inj.layoff_matches)
      : (remaining > 0 ? `out for ${remaining} more match${remaining === 1 ? "" : "es"}` : "available now");
    return `
    <tr><td>${inj.minute}'</td><td>${inj.team}</td><td>${inj.player}</td><td>${inj.position}</td>
    <td>${inj.severity || ""}</td><td>${statusText}</td>
    <td>${matchLink({home: inj.home, away: inj.away, scoreline: inj.scoreline, match_id: inj.match_id})}</td></tr>`;
  }).join("");
  return `<table class="stats">
    <tr><th>Minute</th><th>Team</th><th>Player</th><th>Position</th><th>Severity</th><th>Status</th><th>Match</th></tr>
    ${rows}</table>`;
}

// Tournament-wide card report - same convention as `injuryReportTable`
// above. A red card's `matches_remaining` (only present when the server
// had a running tournament's availability ledger) is a LIVE countdown of
// the next-match suspension it costs - see `_card_report_json` in
// webapp.py. A yellow card never gets a "status" at all: it doesn't carry
// any tournament-level suspension (see README/`tournament/availability.py`).
function cardReportTable(cardReport) {
  const rows = cardReport.map(c => {
    let statusText = "";
    if (c.card_type === "red") {
      const remaining = c.matches_remaining;
      statusText = remaining === undefined
        ? "misses next match"
        : (remaining > 0 ? `out for ${remaining} more match${remaining === 1 ? "" : "es"}` : "available now");
    }
    const cardText = c.card_type === "red"
      ? (c.escalated_second_yellow ? "Red (2nd yellow)" : "Red")
      : "Yellow";
    return `
    <tr><td>${c.minute}'</td><td>${c.team}</td><td>${c.player}</td>
    <td>${cardText}</td><td>${statusText}</td>
    <td>${matchLink({home: c.home, away: c.away, scoreline: c.scoreline, match_id: c.match_id})}</td></tr>`;
  }).join("");
  return `<table class="stats">
    <tr><th>Minute</th><th>Team</th><th>Player</th><th>Card</th><th>Status</th><th>Match</th></tr>
    ${rows}</table>`;
}

// World-Rugby-style team rankings movement (see `tournament/rankings.py`) -
// "change" is net movement versus that team's starting `WR_RANKING_SEED`/
// default baseline point value, not just within this one tournament -
// for a shared Season-mode tracker this reflects the whole season so far.
function teamFormTable(teamForm) {
  const rows = teamForm.map(row => {
    const changeText = row.change > 0 ? `+${row.change}` : `${row.change}`;
    const changeClass = row.change > 0 ? "positive" : (row.change < 0 ? "negative" : "");
    return `
    <tr><td>${logoImgHtml(row.team, 18)}${row.team}</td><td>${row.rating}</td>
    <td class="${changeClass}">${changeText}</td>
    <td>${row.wins}-${row.draws}-${row.losses}</td></tr>`;
  }).join("");
  return `<table class="stats">
    <tr><th>Team</th><th>Rating</th><th>Change</th><th>W-D-L</th></tr>
    ${rows}</table>`;
}

function renderTournamentProgress(resultsSoFar, progress, injuryReport, cardReport, teamForm) {
  const box = document.getElementById("tournament-progress");
  if (!box) return;
  if ((!resultsSoFar || !resultsSoFar.length) && !progress) { box.innerHTML = ""; return; }

  let html = "";
  if (progress && progress.stage) {
    html += `<h4>Current stage: ${progress.stage}</h4>`;
  }
  if (progress && progress.standings) {
    html += collapsibleHtml("standings", "Current standings", standingsTable(progress.standings), true);
  }
  if (progress && progress.pools) {
    const poolsHtml = Object.entries(progress.pools).map(([name, rows]) =>
      `<p class="muted">${name}:</p>${standingsTable(rows)}`).join("");
    html += collapsibleHtml("pools", "Current pool standings", poolsHtml, true);
  }
  if (progress && progress.bracket && progress.bracket.length) {
    const bracketHtml = progress.bracket.map(rnd => `
      <p class="muted">${rnd.stage}:</p>
      ${rnd.matches.map(m => `<div>${m.home} ${matchLink(m)} ${m.away}</div>`).join("")}
    `).join("");
    html += collapsibleHtml("bracket", "Knockout bracket so far", bracketHtml, true);
  }
  if (resultsSoFar && resultsSoFar.length) {
    const rows = resultsSoFar.map(m => `<tr><td>${m.home}</td><td>${matchLink(m)}</td><td>${m.away}</td></tr>`).join("");
    const resultsHtml = `<table class="stats"><tr><th>Home</th><th>Score</th><th>Away</th></tr>${rows}</table>`;
    html += collapsibleHtml("results", `Results so far (${resultsSoFar.length})`, resultsHtml, false);
  }
  if (injuryReport && injuryReport.length) {
    html += collapsibleHtml("injuries", `Injury report (${injuryReport.length})`, injuryReportTable(injuryReport), false);
  }
  if (cardReport && cardReport.length) {
    html += collapsibleHtml("cards", `Card report (${cardReport.length})`, cardReportTable(cardReport), false);
  }
  if (teamForm && teamForm.length) {
    html += collapsibleHtml("form", "Team form / rankings", teamFormTable(teamForm), false);
  }
  html += `<div id="tournament-match-detail-live"></div>`;
  box.innerHTML = html;
  wireCollapsibles(box);
  box.querySelectorAll(".match-link").forEach(btn => {
    btn.onclick = () => showMatchDetail(btn.dataset.matchId, "tournament-match-detail-live");
  });
}

// Drives an interactive tournament session forward: shows the live-match
// UI (same `renderLiveMatchState` the single-friendly live match uses)
// whenever the session is paused on the user's own fixture, resumes the
// tournament once the user explicitly asks to (so the just-finished
// match's full-time scoreline/events/stats stay on screen until they're
// done reviewing it, instead of being replaced the instant it ends) - and
// keeps doing so, fully auto-simming everyone else's matches in between,
// until the session reports "finished" (or "error"). `results_so_far`
// (every fixture resolved up to this point, mine and auto-simmed alike) is
// re-rendered into a persistent, always-visible feed on every state update.
function handleTournamentSessionState(state, status, myTeam) {
  const liveArea = document.getElementById("tournament-live-area");
  const banner = document.getElementById("tournament-stage-banner");
  renderTournamentProgress(state.results_so_far, state.progress, state.injury_report, state.card_report, state.team_form);
  if (state.status === "error") {
    if (banner) banner.innerHTML = "";
    showError(status, "Error: " + state.error);
    return;
  }
  if (state.status === "finished") {
    if (banner) banner.innerHTML = "";
    setStatus(status, "");
    liveArea.innerHTML = "";
    renderTournamentReport(state.report);
    return;
  }
  // paused: it's my_team's turn - play it out with the normal live-match UI.
  // Only my_team's own side gets a "Substitute..." control here - the
  // opponent is whichever auto-drafted/CPU side the tournament is
  // simulating, the user shouldn't be able to make their decisions for them.
  const mySide = myTeam === state.home ? "home" : myTeam === state.away ? "away" : null;
  const stageLabel = state.progress && state.progress.stage ? state.progress.stage : "this fixture";
  if (banner) {
    banner.innerHTML = `<h3>Now playing: ${stageLabel} - ${state.home} v ${state.away}</h3>`;
  }
  setStatus(status, `Your match (${stageLabel}): ${state.home} v ${state.away} - play it out below.`);
  renderLiveMatchState(state.live_match, (finishedState) => {
    // Match just finished - renderLiveMatchState rendered its full-time
    // scoreline/events/stats into #tournament-live-area itself (the explicit
    // `reportTargetId` below - without it, the finished report defaults to
    // the single-friendly-match screen's hidden "#report" div, leaving this
    // area with nothing in it but the "Continue tournament" button). Don't
    // auto-advance; wait for the user to say they're done looking at it.
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `<button id="t-continue-after-my-match">Continue tournament</button>`;
    liveArea.appendChild(row);
    document.getElementById("t-continue-after-my-match").onclick = async () => {
      setStatus(status, "continuing tournament...");
      try {
        const next = await api(`/api/tournament/${state.session_id}/resume`, {method: "POST"});
        handleTournamentSessionState(next, status, myTeam);
      } catch (e) {
        showError(status, "Error: " + e.message);
      }
    };
  }, "tournament-live-area", mySide, "tournament-live-area");
}

function standingsTable(rows) {
  const body = rows.map(r => `
    <tr><td>${r.team}</td><td>${r.played}</td><td>${r.won}</td><td>${r.drawn}</td><td>${r.lost}</td>
    <td>${r.points_for}</td><td>${r.points_against}</td><td>${r.points_diff}</td><td>${r.table_points}</td></tr>`).join("");
  return `<table class="stats"><tr><th>Team</th><th>P</th><th>W</th><th>D</th><th>L</th><th>PF</th><th>PA</th><th>+/-</th><th>Pts</th></tr>${body}</table>`;
}

function teamTournamentStatsTable(rows) {
  const body = rows.map(s => `
    <tr><td>${logoImgHtml(s.team, 18)}${s.team}</td><td>${s.played}</td><td>${s.tries}</td>
    <td>${s.penalty_goals}</td><td>${s.drop_goals}</td><td>${s.turnovers_won}</td>
    <td>${s.handling_errors}</td><td>${s.penalties_conceded}</td>
    <td>${s.yellow_cards}/${s.red_cards}</td><td>${s.avg_territory_pct}%</td>
    <td>${s.injuries}</td><td>${s.substitutions}</td></tr>`).join("");
  return `<table class="stats">
    <tr><th>Team</th><th>Played</th><th>Tries</th><th>Pens</th><th>DGs</th><th>Turnovers</th>
    <th>Errors</th><th>Pens conceded</th><th>Cards Y/R</th><th>Avg territory</th><th>Injuries</th><th>Subs</th></tr>
    ${body}</table>`;
}

function playerTournamentStatsTable(rows, showPosition) {
  const body = rows.map(s => `
    <tr>${showPosition ? `<td>${s.position || ""}</td>` : ""}
    <td>${logoImgHtml(s.team, 18)}${s.name}</td><td>${s.team}</td>
    <td>${s.points}</td><td>${s.tries}</td><td>${s.conversions}</td><td>${s.penalty_goals}</td>
    <td>${s.matches_started}</td><td>${s.average_performance}</td></tr>`).join("");
  return `<table class="stats">
    <tr>${showPosition ? "<th>Slot</th>" : ""}<th>Player</th><th>Team</th><th>Pts</th><th>Tries</th>
    <th>Conv</th><th>Pens</th><th>Starts</th><th>Avg performance</th></tr>
    ${body}</table>`;
}

async function showMatchDetail(matchId, targetId) {
  const box = document.getElementById(targetId);
  if (!box) return;
  box.innerHTML = `<span class="muted">loading...</span>`;
  try {
    const data = await api(`/api/match/${matchId}`);
    renderReport(data, targetId);
    box.scrollIntoView({behavior: "smooth", block: "start"});
  } catch (e) {
    box.innerHTML = `<span class="muted">Could not load match detail: ${e.message}</span>`;
  }
}

function matchLink(m) {
  // Every match - group, bracket, or plain result - carries a match_id
  // from the server, so any line can be clicked to see that match's full
  // minute-by-minute detail (same report as a single friendly).
  return `<button class="match-link" data-match-id="${m.match_id}">${m.scoreline}</button>`;
}

function renderTournamentReport(report) {
  const box = document.getElementById("tournament-report");
  let html = `<h3>${report.name}</h3><div id="tournament-match-detail"></div>`;
  if (report.champion) {
    html += `<p><strong>Champion: ${logoImgHtml(report.champion, 22)}${report.champion}</strong></p>`;
  }
  if (report.player_of_tournament) {
    const p = report.player_of_tournament;
    html += `<p><strong>Player of the Tournament:</strong> ${logoImgHtml(p.team, 20)}${p.name} ` +
      `(${p.team}, ${p.position || ""}) - avg performance ${p.average_performance} over ${p.matches_started} starts` +
      (p.played_late_stage ? " (played in the semi-final/final)" : "") + `</p>`;
  }
  if (report.pools) {
    const poolsHtml = Object.entries(report.pools).map(([poolName, rows]) =>
      `<h4>${poolName}</h4>${standingsTable(rows)}`).join("");
    html += collapsibleHtml("final-pools", "Final pool standings", poolsHtml, false);
  }
  if (report.standings) {
    html += collapsibleHtml("final-standings", "Final standings", standingsTable(report.standings), true);
  }
  if (report.bracket && report.bracket.length) {
    const bracketHtml = report.bracket.map(rnd =>
      `<h4>${rnd.stage}</h4>` + rnd.matches.map(m => `<div>${matchLink(m)}</div>`).join("")).join("");
    html += collapsibleHtml("final-bracket", "Knockout bracket", bracketHtml, false);
  }
  if (report.team_stats && report.team_stats.length) {
    html += collapsibleHtml("final-team-stats", "Team tournament stats", teamTournamentStatsTable(report.team_stats), false);
  }
  if (report.top_scorers && report.top_scorers.length) {
    html += collapsibleHtml("final-top-scorers", "Tournament top scorers", playerTournamentStatsTable(report.top_scorers, false), false);
  }
  if (report.team_of_tournament && report.team_of_tournament.length) {
    const totHtml = `<p class="muted">Best average performance per starting slot across every match played -
      quality at the position they started in, plus a bonus for whatever they personally scored
      that match (see README: this is a heuristic, the engine doesn't track per-player
      tackles/metres).</p>${playerTournamentStatsTable(report.team_of_tournament, true)}`;
    html += collapsibleHtml("final-team-of-tournament", "Team of the Tournament", totHtml, false);
  }
  const resultsHtml = report.results.map(r => `<div>${matchLink(r)}</div>`).join("");
  html += collapsibleHtml("final-all-results", "All results (click any match for the full simulation)", resultsHtml, false);
  if (report.injury_report && report.injury_report.length) {
    html += collapsibleHtml("final-injuries", `Injury report (${report.injury_report.length})`, injuryReportTable(report.injury_report), false);
  }
  if (report.card_report && report.card_report.length) {
    html += collapsibleHtml("final-cards", `Card report (${report.card_report.length})`, cardReportTable(report.card_report), false);
  }
  if (report.team_form && report.team_form.length) {
    html += collapsibleHtml("final-form", "Team form / rankings", teamFormTable(report.team_form), false);
  }
  const snapshotHtml = html; // captured before the match-detail div fills in and before the button itself
  box.innerHTML = html + snapshotButtonHtml("tournament-snapshot-btn");
  wireCollapsibles(box);
  document.getElementById("tournament-snapshot-btn").onclick = () => {
    downloadHtmlSnapshot(report.name, snapshotHtml, report.name);
  };

  box.querySelectorAll(".match-link").forEach(btn => {
    const originalText = btn.textContent;
    btn.onclick = async () => {
      btn.textContent = "loading...";
      try {
        const data = await api(`/api/match/${btn.dataset.matchId}`);
        renderReport(data, "tournament-match-detail");
        document.getElementById("tournament-match-detail").scrollIntoView({behavior: "smooth", block: "start"});
      } catch (e) {
        alert("Could not load match detail: " + e.message);
      } finally {
        btn.textContent = originalText;
      }
    };
  });
}

// ===================== Draft mode =====================
// Pool setup -> coin flip -> alternating picks -> 3-round protect/poach ->
// hand off into the normal TeamBuilder (human side) + auto-draft (AI side).
// All rugby logic (ratings, auto-draft, match sim) stays server-side -
// this is rendering + wiring only, same philosophy as the rest of the UI.
let draftSessionId = null;
let draftShowFitRatings = false; // toggle: show each player's natural-position fit rating while drafting/protecting
let draftPoolPlayers = []; // [{code, players}] chosen so far, just for the running count
let draftHumanBuilder = null;
let draftAiTeamId = null;
let draftSortDir = "desc"; // shared by the remaining-pool list and the protect/poach selects

async function refreshDraftDepthChart(area) {
  if (!draftSessionId || !area) return;
  try {
    const res = await api(`/api/draft/${draftSessionId}/depth_chart`);
    area.innerHTML = draftDepthChartHtml(res.depth_chart);
  } catch (e) {
    area.innerHTML = `<p class="muted">Could not load depth chart: ${e.message}</p>`;
  }
}

// A "tactics board" style sidebar: one slot per real position, top 3
// drafted-so-far candidates ranked by their rating AT that position (not
// just natural_fit) - a preview of who'd play where if the lineup had to
// be locked in right now, not an actual assignment (draft mode deliberately
// doesn't assign positions during the draft - see README).
function draftDepthChartHtml(chart) {
  const rows = POSITIONS.map(pos => {
    const entries = chart[pos] || [];
    const cells = entries.length
      ? entries.map(p => `<div class="depth-entry">${p.name} <span class="fit">${p.fit.toFixed(1)}</span></div>`).join("")
      : `<div class="muted depth-entry">(none yet)</div>`;
    return `<div class="slot depth-slot"><span class="pos">${pos}</span>${cells}</div>`;
  }).join("");
  return `<div class="pitch depth-chart">${rows}</div>`;
}

async function enterDraftMode() {
  navTo("screen-draft-pool", "Draft mode", () => showScreen("screen-draft-pool"));
  randomizeBackground();
  renderDraftPoolScreen();
}

function renderDraftPoolScreen() {
  // Union + season picker: each "Add" click appends one {code, season} pair
  // to `chosenUnionSquads` - deliberately NOT a toggle-button Set keyed by
  // code alone, since that made it impossible to add e.g. "Ireland 2026"
  // AND "Ireland 2025" at once (one global season for every chosen union).
  // Same add-one-at-a-time flow as the historical-squad picker right below
  // it, for the same reason: a season is part of the selection, not a
  // single setting for the whole screen.
  const unionArea = document.getElementById("draft-union-area");
  const unionListBox = document.getElementById("draft-union-list");
  unionArea.innerHTML = `
    <select id="draft-union-code">${UNIONS.map(u => `<option value="${u.code}">${u.code} - ${u.name}</option>`).join("")}</select>
    ${seasonSelectHtml("draft-union-season")}
    <button id="draft-union-add">Add this union's pool</button>`;
  const unionCodeSel = document.getElementById("draft-union-code");
  const unionSeasonSel = document.getElementById("draft-union-season");
  const chosenUnionSquads = []; // [{code, season}]
  const chosenHistorical = []; // [{competition, year, team}]
  const status = document.getElementById("draft-pool-status");
  const updateStatus = () => {
    setStatus(status, `${chosenUnionSquads.length} union+season pick(s) + ${chosenHistorical.length} historical squad(s) selected so far.`);
  };
  const renderUnionList = () => {
    unionListBox.textContent = chosenUnionSquads.length
      ? "Added: " + chosenUnionSquads.map(u => `${u.code} ${u.season}`).join(", ")
      : "";
  };
  document.getElementById("draft-union-add").onclick = () => {
    chosenUnionSquads.push({code: unionCodeSel.value, season: unionSeasonSel.value});
    renderUnionList();
    updateStatus();
  };

  // Historical-squad picker - same data flow as TeamBuilder's "Historical
  // squad" mode (compSel -> yearSel -> teamSel -> "Add this squad"), just
  // collecting selections into `chosenHistorical` instead of one team's pool.
  const histArea = document.getElementById("draft-historical-area");
  const histListBox = document.getElementById("draft-historical-list");
  histArea.innerHTML = `
    <select id="draft-hist-comp">
      <option value="rwc">Rugby World Cup (1995-2023)</option>
      <option value="sn">Six Nations Championship (2009-2021)</option>
    </select>
    <select id="draft-hist-year"></select>
    <select id="draft-hist-team"><option>(load a year first)</option></select>
    <button id="draft-hist-add">Add this squad</button>
    <span class="muted" id="draft-hist-status"></span>`;
  const compSel = document.getElementById("draft-hist-comp");
  const yearSel = document.getElementById("draft-hist-year");
  const teamSel = document.getElementById("draft-hist-team");
  const histStatus = document.getElementById("draft-hist-status");
  let yearData = null;
  const renderHistList = () => {
    histListBox.textContent = chosenHistorical.length
      ? "Historical squads added: " + chosenHistorical.map(h => `${h.team} (${h.competition.toUpperCase()} ${h.year})`).join(", ")
      : "";
  };
  const loadYears = async () => {
    const path = compSel.value === "rwc" ? "/api/historical_rwc/years" : "/api/historical_six_nations/years";
    const res = await api(path);
    yearSel.innerHTML = res.years.map(y => `<option value="${y}">${y}</option>`).join("");
    await loadYearData();
  };
  const loadYearData = async () => {
    const year = yearSel.value;
    setStatus(histStatus, "loading real squads...");
    const path = compSel.value === "rwc" ? `/api/historical_rwc/${year}` : `/api/historical_six_nations/${year}`;
    const res = await api(path);
    yearData = res;
    const teamNames = Object.keys(res.squads).sort();
    teamSel.innerHTML = teamNames.map(n => `<option value="${n}">${n}</option>`).join("");
    setStatus(histStatus, `${teamNames.length} teams loaded for ${year}.`);
  };
  compSel.onchange = loadYears;
  yearSel.onchange = loadYearData;
  document.getElementById("draft-hist-add").onclick = () => {
    if (!yearData) return;
    chosenHistorical.push({competition: compSel.value, year: parseInt(yearSel.value, 10), team: teamSel.value});
    renderHistList();
    updateStatus();
  };
  loadYears();

  document.getElementById("draft-start-btn").onclick = async () => {
    const startStatus = document.getElementById("draft-start-status");
    const seedRaw = document.getElementById("draft-seed").value;
    const legends = document.getElementById("draft-include-legends").checked;
    if (chosenUnionSquads.length === 0 && !legends && chosenHistorical.length === 0) {
      showError(startStatus, "Add at least one union+season, a historical squad, or Legends first.");
      return;
    }
    setStatus(startStatus, "building shared pool and flipping a coin...");
    try {
      const data = await api("/api/draft/start", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          union_squads: chosenUnionSquads, legends, historical: chosenHistorical,
          seed: seedRaw ? parseInt(seedRaw, 10) : null,
        }),
      });
      draftSessionId = data.session_id;
      navTo("screen-draft-coinflip", "Coin flip", () => showScreen("screen-draft-coinflip"));
      renderDraftCoinflip(data);
    } catch (e) {
      showError(startStatus, "Error: " + e.message);
    }
  };
}

function renderDraftCoinflip(state) {
  const area = document.getElementById("draft-coinflip-area");
  const winner = state.first_picker === "human" ? "You" : "The AI";
  area.innerHTML = `
    <p>${state.remaining_pool.length} players in the shared pool.</p>
    <p><strong>${winner} won the coin flip and picks first.</strong></p>
    <button id="draft-to-picking">Start drafting</button>`;
  document.getElementById("draft-to-picking").onclick = () => {
    navTo("screen-draft-picking", "Draft", () => showScreen("screen-draft-picking"));
    renderDraftPicking(state);
  };
}

function renderDraftPicking(state) {
  const area = document.getElementById("draft-picking-area");
  if (state.phase !== "drafting") {
    area.innerHTML = `<p>Draft complete - moving to the protect phase...</p>`;
    navTo("screen-draft-protect", "Protect phase", () => showScreen("screen-draft-protect"));
    renderDraftProtect(state);
    return;
  }
  const turnText = state.turn === "human" ? "Your turn - click a player to draft them." : "AI is picking...";
  const showFit = !!draftShowFitRatings;
  const fitSpan = (p) => showFit ? `<span class="fit">${p.natural_fit.toFixed(1)}</span>` : "";
  const sortedPool = sortPlayersByRating(state.remaining_pool, draftSortDir, "natural_fit");
  area.innerHTML = `
    <div class="row">
      <div style="flex:1">
        <div class="row">
          <div class="muted">You: ${state.human_roster.length}/${state.roster_target} drafted</div>
          <div class="muted">AI: ${state.ai_roster.length}/${state.roster_target} drafted</div>
          <label class="muted"><input type="checkbox" id="draft-show-fit" ${showFit ? "checked" : ""}>
            Show fit rating (natural-position rating)</label>
        </div>
        <p><strong>${turnText}</strong></p>
        <div class="row">${sortToggleHtml("draft-pool-sort")}</div>
        <div class="candidates" id="draft-remaining-list">
          ${sortedPool.map(p => `
            <div class="candidate" data-id="${p.id}">
              <span>${p.name} (${p.nation}${p.era ? ", " + p.era : ""}) - ${p.natural_position}</span>
              ${fitSpan(p)}
            </div>`).join("")}
        </div>
        <div class="row"><strong>Your roster:</strong> ${state.human_roster.map(p => `${p.name}${showFit ? ` (${p.natural_fit.toFixed(1)})` : ""}`).join(", ") || "(none yet)"}</div>
        <div class="row"><strong>AI roster:</strong> ${state.ai_roster.map(p => `${p.name}${showFit ? ` (${p.natural_fit.toFixed(1)})` : ""}`).join(", ") || "(none yet)"}</div>
        <div class="row muted" id="draft-log">${state.log.slice(-5).join("<br>")}</div>
      </div>
      <div style="flex:1">
        <div class="muted">Your depth chart so far (top 3 per position, by rating at that position - a preview, not a lock-in):</div>
        <div id="draft-depth-chart"></div>
      </div>
    </div>`;
  const fitToggle = document.getElementById("draft-show-fit");
  if (fitToggle) {
    fitToggle.onchange = (e) => { draftShowFitRatings = e.target.checked; renderDraftPicking(state); };
  }
  wireSortToggle("draft-pool-sort", () => draftSortDir, (d) => { draftSortDir = d; }, () => renderDraftPicking(state));
  refreshDraftDepthChart(document.getElementById("draft-depth-chart"));
  if (state.turn === "human") {
    area.querySelectorAll(".candidate").forEach(row => {
      row.onclick = async () => {
        try {
          const data = await api(`/api/draft/${draftSessionId}/pick`, {
            method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify({player_id: parseInt(row.dataset.id, 10)}),
          });
          renderDraftPicking(data);
        } catch (e) {
          alert("Could not draft that player: " + e.message);
        }
      };
    });
  } else {
    // It's the AI's turn with nothing pending from the human (this only
    // happens right after the coin flip, if the AI won it) - nudge the
    // server to make the AI's move, then re-render.
    api(`/api/draft/${draftSessionId}/pick`, {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({}),
    }).then(renderDraftPicking);
  }
}

function renderDraftProtect(state) {
  const area = document.getElementById("draft-protect-area");
  if (state.phase !== "protect") {
    area.innerHTML = `<p>Protect phase complete - preparing your lineup builder...</p>`;
    finishDraftIntoBuild(state);
    return;
  }
  const showFit = !!draftShowFitRatings;
  const optLabel = (p) => showFit ? `${p.name} (${p.natural_fit.toFixed(1)})` : p.name;
  const protectOptions = sortPlayersByRating(
    state.human_roster.filter(p => !state.protected_human.includes(p.id)), draftSortDir, "natural_fit");
  const poachOptions = sortPlayersByRating(
    state.ai_roster.filter(p => !state.protected_ai.includes(p.id)), draftSortDir, "natural_fit");
  area.innerHTML = `
    <div class="row">
      <div style="flex:1">
        <h3>Round ${state.protect_round + 1} of ${state.protect_rounds_total}</h3>
        <div class="row">
          <label class="muted"><input type="checkbox" id="draft-show-fit" ${showFit ? "checked" : ""}>
            Show fit rating (natural-position rating)</label>
          ${sortToggleHtml("draft-protect-sort")}
        </div>
        <div class="row"><label class="muted">Protect one of your players:
          <select id="draft-protect-select">
            <option value="">(none)</option>
            ${protectOptions.map(p => `<option value="${p.id}">${optLabel(p)}</option>`).join("")}
          </select>
        </label></div>
        <div class="row"><label class="muted">Poach an unprotected AI player (optional):
          <select id="draft-poach-select">
            <option value="">(none)</option>
            ${poachOptions.map(p => `<option value="${p.id}">${optLabel(p)}</option>`).join("")}
          </select>
        </label></div>
        <div class="row">
          <button id="draft-protect-submit">Confirm round</button>
        </div>
        <div class="row muted">${state.log.slice(-6).join("<br>")}</div>
      </div>
      <div style="flex:1">
        <div class="muted">Your depth chart so far (top 3 per position, by rating at that position):</div>
        <div id="draft-depth-chart"></div>
      </div>
    </div>`;
  document.getElementById("draft-show-fit").onchange = (e) => {
    draftShowFitRatings = e.target.checked;
    renderDraftProtect(state);
  };
  wireSortToggle("draft-protect-sort", () => draftSortDir, (d) => { draftSortDir = d; }, () => renderDraftProtect(state));
  refreshDraftDepthChart(document.getElementById("draft-depth-chart"));
  document.getElementById("draft-protect-submit").onclick = async () => {
    const protectVal = document.getElementById("draft-protect-select").value;
    const poachVal = document.getElementById("draft-poach-select").value;
    const data = await api(`/api/draft/${draftSessionId}/protect_round`, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        protect_id: protectVal ? parseInt(protectVal, 10) : null,
        poach_id: poachVal ? parseInt(poachVal, 10) : null,
      }),
    });
    renderDraftProtect(data);
  };
}

async function finishDraftIntoBuild(state) {
  const finalized = await api(`/api/draft/${draftSessionId}/finalize_ai`, {method: "POST"});
  draftAiTeamId = finalized.team_id;
  navTo("screen-draft-build", "Build your XV", () => showScreen("screen-draft-build"));
  draftHumanBuilder = new TeamBuilder("draft-human", {
    title: "Your drafted XV", fixedPool: finalized.human_roster,
  });
  updateDraftRunButton();
  document.getElementById("draft-run-match").onclick = async () => {
    const seedRaw = document.getElementById("draft-match-seed").value;
    const seed = seedRaw ? parseInt(seedRaw, 10) : null;
    const status = document.getElementById("draft-run-status");
    const isLive = document.getElementById("draft-live-match-toggle").checked;
    setStatus(status, "simulating...");
    try {
      if (isLive) {
        document.getElementById("draft-report").innerHTML = "";
        // Your drafted XV is always `home_team_id` here - only your side
        // gets a "Substitute..." control, never the AI's auto-drafted one
        // (same convention as the interactive tournament's own matches).
        await startLiveMatch(draftHumanBuilder.teamId, draftAiTeamId, seed, "draft-live-match-area", "home", "draft-report");
      } else {
        document.getElementById("draft-live-match-area").innerHTML = "";
        const data = await api("/api/match", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({home_team_id: draftHumanBuilder.teamId, away_team_id: draftAiTeamId, seed}),
        });
        renderReport(data, "draft-report");
      }
      setStatus(status, "");
    } catch (e) {
      showError(status, "Error: " + e.message);
    }
  };
}

function updateDraftRunButton() {
  const btn = document.getElementById("draft-run-match");
  const ready = !!(draftHumanBuilder && draftHumanBuilder.teamId && draftAiTeamId);
  btn.disabled = !ready;
  setStatus(document.getElementById("draft-run-hint"), ready ? "" : "Click \"Save team\" on your drafted XV first.", !ready);
}

// `TeamBuilder.renderFinish`'s "Save team" handler calls the global
// `updateRunButton()` (friendly mode's) unconditionally - wrap it so a
// save from the draft-mode builder also refreshes the draft run button
// without friendly mode's own button needing to exist yet.
const _originalUpdateRunButton = updateRunButton;
updateRunButton = function () {
  try { _originalUpdateRunButton(); } catch (e) { /* friendly mode not initialized yet - fine */ }
  if (draftHumanBuilder) updateDraftRunButton();
};

// ===================== Season mode (12c) =====================
// Thin orchestration layer over existing tournament-mode rendering
// (`renderTournamentProgress`/`renderTournamentReport`,
// `collapsibleHtml`/`wireCollapsibles`) - not a parallel UI. v1 is
// non-interactive: every block is fully auto-simmed server-side
// (`/api/season/<id>/play_block`), one block at a time, with a
// "Continue to <next block>" button driving the season forward.
let seasonSessionId = null;
let seasonInitialized = false;

// 13b: Season mode reworked to be fully interactive, like Tournament mode -
// pick one nation as "my team", draft it from the WIDEST real pool (capped
// internationals + 12d/13a's uncapped club players, via
// `/api/season/start` with no `my_team` yet - that first call just returns
// the plan + pool to draft from), then start the season for real with
// `my_team` + the drafted squad's player ids: every one of that nation's
// own fixtures, across every chained block, pauses on the exact same
// live-match UI (`renderLiveMatchState`) Tournament mode's `my_team`
// fixtures use, while every other nation auto-drafts/auto-sims unattended
// and blocks auto-advance with no manual "play next block" click.
let seasonNation = null; // display name of the drafted nation, once planned
let seasonBuilder = null; // TeamBuilder drafting my_team's matchday-23

async function enterSeasonMode() {
  navTo("screen-season", "Season mode", () => showScreen("screen-season"));
  randomizeBackground();
  if (seasonInitialized) return;
  seasonInitialized = true;

  const nationSel = document.getElementById("season-nation-select");
  nationSel.innerHTML = UNIONS.map(u => `<option value="${u.code}">${u.code} - ${u.name}</option>`).join("");

  document.getElementById("season-plan-btn").onclick = async () => {
    const status = document.getElementById("season-start-status");
    const nationCode = nationSel.value;
    const year = parseInt(document.getElementById("season-year-input").value, 10);
    setStatus(status, "Finding this union's real blocks + widest draft pool...");
    document.getElementById("season-blocks-area").innerHTML = "";
    document.getElementById("season-progress").innerHTML = "";
    document.getElementById("season-report").innerHTML = "";
    document.getElementById("season-live-area").innerHTML = "";
    document.getElementById("season-uncapped-pool").innerHTML = "";
    document.getElementById("season-draft-area").innerHTML = "";
    seasonSessionId = null;
    try {
      const data = await api("/api/season/start", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({nation_code: nationCode, year}),
      });
      seasonNation = UNIONS.find(u => u.code === nationCode).name;
      // 13b: drafting uses the WIDEST pool (capped + uncapped/eligible,
      // merged) - a separate lookup from the plain plan/pool above, which
      // stays capped-only for backward compatibility (see webapp.py).
      const widest = await api(`/api/season/widest_pool?nation=${nationCode}&year=${year}`);
      setStatus(status, `${data.blocks.length} real tournament block(s) found for ${nationCode} ${year} - draft your squad below, then start the season.`);
      renderSeasonBlocksList(data);
      renderSeasonUncappedPool(data, widest);
      renderSeasonDraftArea(widest, nationCode, year);
    } catch (e) {
      showError(status, `Could not plan season: ${e.message || e}`);
    }
  };
}

function renderSeasonBlocksList(data) {
  const area = document.getElementById("season-blocks-area");
  const rows = data.blocks.map((b, i) => {
    const marker = i < data.current_block_index ? "done" : (i === data.current_block_index ? "next" : "");
    return `<li>${b.display_name}${marker ? ` (${marker})` : ""}</li>`;
  }).join("");
  area.innerHTML = `<p class="muted">These blocks play automatically, one after another - your own
    matches pause for you to play live, every other fixture auto-sims in the background.</p><ol>${rows}</ol>`;
}

function uncappedPoolTable(players) {
  const rows = players.map(p => `<tr><td>${p.name}</td><td>${p.natural_position}</td><td>${p.natural_fit}</td><td class="muted">${p.notes}</td></tr>`).join("");
  return `<table><thead><tr><th>Name</th><th>Position</th><th>Fit</th><th>Notes</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function renderSeasonUncappedPool(data, widest) {
  const uncappedBox = document.getElementById("season-uncapped-pool");
  const cappedNames = new Set(data.pool.map(p => p.name));
  const uncapped = (widest.pool || []).filter(p => !cappedNames.has(p.name));
  if (uncapped.length) {
    uncappedBox.innerHTML = collapsibleHtml(
      "season-uncapped", `Uncapped / eligible players in your widest draft pool (${uncapped.length}) - never capped internationally, drawn from club Wikipedia squads`,
      uncappedPoolTable(uncapped), false,
    );
    wireCollapsibles(uncappedBox);
  } else {
    uncappedBox.innerHTML = "";
  }
}

// Drafting my_team's own matchday-23 from the widest pool: a normal
// `TeamBuilder` in `fixedPool` mode (same pattern Draft mode's
// finalize-build step uses, see `panel-draft-human_builder` there) - once
// all 15 starting slots + any bench picks are filled, "Start season" reads
// the builder's own `slots`/`bench` directly (no "Save team" call needed -
// squads mode just wants the pool of ids, not one locked lineup) and kicks
// off the real interactive season.
function renderSeasonDraftArea(planData, nationCode, year) {
  const area = document.getElementById("season-draft-area");
  area.innerHTML = `
    <h3>Draft ${seasonNation}'s matchday-23 (${planData.pool.length} players available)</h3>
    <p class="muted">Pick all 15 starters, then optionally up to 8 bench players - this whole
      squad becomes the pool a fresh best-fit XV is auto-drafted from before every one of
      ${seasonNation}'s matches this season (same "squad, not one fixed XV" mode Tournament
      mode's squads use), so pick broadly, not just one ideal matchday.</p>
    <div id="panel-season_builder"></div>
    <div class="row">
      <button id="season-confirm-draft-btn">Start season with this squad</button>
      <span class="muted" id="season-draft-status"></span>
    </div>`;
  seasonBuilder = new TeamBuilder("season_builder", {
    title: `${seasonNation} - your squad`, fixedName: seasonNation, fixedPool: planData.pool,
  });
  document.getElementById("season-confirm-draft-btn").onclick = async () => {
    const status = document.getElementById("season-draft-status");
    const filled = Object.keys(seasonBuilder.slots).length;
    if (filled < POSITIONS.length) {
      showError(status, `Fill all ${POSITIONS.length} starting positions first (${filled}/${POSITIONS.length} so far).`);
      return;
    }
    const squadIds = Array.from(new Set([...Object.values(seasonBuilder.slots), ...Array.from(seasonBuilder.bench)]));
    setStatus(status, "Starting season...");
    try {
      const body = {
        nation_code: nationCode, year, my_team: seasonNation,
        squad_player_ids: {[seasonNation]: squadIds},
      };
      const state = await api("/api/season/start", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body),
      });
      seasonSessionId = state.session_id;
      setStatus(status, "");
      area.innerHTML = `<p class="muted">Squad locked in (${squadIds.length} players) - season running below.</p>`;
      handleSeasonSessionState(state);
    } catch (e) {
      showError(status, `Could not start season: ${e.message || e}`);
    }
  };
}

// Mirrors `handleTournamentSessionState` exactly, for a season session
// instead of a single tournament: paused -> my_team's live match (via the
// unchanged `renderLiveMatchState`/live-match endpoints); finished -> the
// final block's report; error -> show it. "Continue season" (after my_team's
// match ends) calls `/api/season/<id>/resume`, which auto-advances the
// background thread - possibly straight into the NEXT block with no pause
// at all - until the next my_team fixture pauses it again or the season ends.
function handleSeasonSessionState(state) {
  const liveArea = document.getElementById("season-live-area");
  const progressBox = document.getElementById("season-progress");
  const reportBox = document.getElementById("season-report");
  const status = document.getElementById("season-start-status");

  let html = "";
  if (state.team_form && state.team_form.length) {
    html += collapsibleHtml("season-form", "Team form / rankings (whole season so far)", teamFormTable(state.team_form), true);
  }
  if (state.injury_report && state.injury_report.length) {
    html += collapsibleHtml("season-injuries", `Injury report (${state.injury_report.length})`, injuryReportTable(state.injury_report), false);
  }
  if (state.card_report && state.card_report.length) {
    html += collapsibleHtml("season-cards", `Card report (${state.card_report.length})`, cardReportTable(state.card_report), false);
  }
  if (state.progress && state.progress.stage) {
    html += `<h4>Current block stage: ${state.progress.stage}</h4>`;
  }
  if (state.progress && state.progress.standings) {
    html += collapsibleHtml("season-standings", "Current block standings", standingsTable(state.progress.standings), true);
  }
  if (state.progress && state.progress.pools) {
    const poolsHtml = Object.entries(state.progress.pools).map(([name, rows]) =>
      `<p class="muted">${name}:</p>${standingsTable(rows)}`).join("");
    html += collapsibleHtml("season-pools", "Current block pool standings", poolsHtml, true);
  }
  if (state.results_so_far && state.results_so_far.length) {
    const rows = state.results_so_far.map(m => `<tr><td>${m.home}</td><td>${matchLink(m)}</td><td>${m.away}</td></tr>`).join("");
    html += collapsibleHtml("season-results", `Results so far (${state.results_so_far.length})`,
      `<table class="stats"><tr><th>Home</th><th>Score</th><th>Away</th></tr>${rows}</table>`, false);
  }
  progressBox.innerHTML = html;
  wireCollapsibles(progressBox);
  progressBox.querySelectorAll(".match-link").forEach(btn => {
    btn.onclick = () => showMatchDetail(btn.dataset.matchId, "season-progress");
  });

  if (state.status === "error") {
    showError(status, "Error: " + state.error);
    return;
  }
  if (state.status === "finished") {
    setStatus(status, "Season complete.");
    liveArea.innerHTML = "";
    if (state.latest_block_report) {
      reportBox.innerHTML = `<h3>Final block: ${state.latest_block_report.name}</h3><div id="tournament-report"></div>`;
      renderTournamentReport(state.latest_block_report); // reuses tournament mode's own final-report renderer
    }
    return;
  }
  // paused: it's my_team's own fixture - play it out live, exactly like
  // Tournament mode's my_team fixtures.
  const mySide = seasonNation === state.home ? "home" : seasonNation === state.away ? "away" : null;
  setStatus(status, `Your match: ${state.home} v ${state.away} - play it out below.`);
  renderLiveMatchState(state.live_match, (finishedState) => {
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `<button id="season-continue-btn">Continue season</button>`;
    liveArea.appendChild(row);
    document.getElementById("season-continue-btn").onclick = async () => {
      setStatus(status, "continuing season...");
      try {
        const next = await api(`/api/season/${state.session_id}/resume`, {method: "POST"});
        handleSeasonSessionState(next);
      } catch (e) {
        showError(status, "Error: " + e.message);
      }
    };
  }, "season-live-area", mySide, "season-live-area");
}

// ===================== Classic Matches mode =====================
// Replay one of 25 real, sourced, Tier-A matches (Rugby World Cup 1995-2023,
// Six Nations/Rugby Championship 2018+). No new drafting UI, no new
// live-match mechanism: two normal `TeamBuilder`s in `fixedPool` mode (same
// pattern Season/Draft/Tournament modes already use) draft from that
// match's exact real player pools, then the existing live-match flow
// (`startLiveMatch`/`renderLiveMatchState`) runs unchanged. Only
// `/api/classic_matches/...` is new.

let classicInitialized = false;
let classicFocusBuilder = null;
let classicCurrentMatchId = null;

const TOURNAMENT_LABEL = {
  rwc: "Rugby World Cup",
  six_nations: "Six Nations",
  rugby_championship: "Rugby Championship",
};

function starsHtml(earned, cap) {
  let out = "";
  for (let i = 0; i < cap; i++) out += i < earned ? "★" : "☆";
  return out;
}

async function updateClassicMatchCount() {
  // The home-screen card text used to hardcode "25 real, famous/surprising
  // matches", which went stale the moment the catalog grew via Tier B - now
  // computed from the actual `/api/classic_matches` response so it never
  // needs a manual fix again.
  try {
    const data = await api("/api/classic_matches");
    const count = Object.values(data.tournaments).reduce((sum, matches) => sum + matches.length, 0);
    const el = document.getElementById("classic-match-count");
    if (el) el.textContent = `${count} real, famous/surprising`;
  } catch (e) {
    // leave the fallback text in place - this is a label nicety only
  }
}

async function enterClassicMatchesMode() {
  navTo("screen-classic-matches", "Classic Matches", () => showScreen("screen-classic-matches"));
  randomizeBackground();
  if (classicInitialized) return;
  classicInitialized = true;

  const modeSelect = document.getElementById("classic-mode-select");
  modeSelect.onchange = async () => {
    const status = document.getElementById("classic-settings-status");
    setStatus(status, "saving...");
    try {
      await api("/api/classic_matches/settings", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({mode: modeSelect.value}),
      });
      setStatus(status, "");
      await loadClassicMatchesList();
    } catch (e) {
      showError(status, "Error: " + e.message);
    }
  };

  await loadClassicMatchesList();
}

function classicMatchRowHtml(match, starCap) {
  return `
    <div class="row">
      <button class="classic-match-btn" data-id="${match.id}">${match.display_name}
        (${match.home_name} v ${match.away_name})</button>
      <span class="muted">${starsHtml(match.best_stars, starCap)}</span>
    </div>
    <p class="muted">${match.blurb} Real score: ${match.real_score}.</p>`;
}

async function loadClassicMatchesList() {
  const listBox = document.getElementById("classic-matches-list");
  listBox.innerHTML = `<p class="muted">Loading...</p>`;
  const data = await api("/api/classic_matches");
  document.getElementById("classic-mode-select").value = data.mode;
  const starCap = data.mode === "5" ? 5 : 3;

  const order = ["rwc", "six_nations", "rugby_championship"];
  listBox.innerHTML = order.filter(t => data.tournaments[t]).map(tournament => {
    const matches = data.tournaments[tournament];
    const body = matches.map(m => classicMatchRowHtml(m, starCap)).join("<hr>");
    return collapsibleHtml(`classic-${tournament}`, TOURNAMENT_LABEL[tournament] || tournament, body, false);
  }).join("");
  wireCollapsibles(listBox);
  listBox.querySelectorAll(".classic-match-btn").forEach(btn => {
    btn.onclick = () => startClassicMatch(btn.dataset.id);
  });
}

async function startClassicMatch(matchId) {
  classicCurrentMatchId = matchId;
  const detailBox = document.getElementById("classic-match-detail");
  detailBox.innerHTML = `<p class="muted">Resolving real player pools (first time for a given
    match/season may hit the network)...</p>`;
  try {
    const res = await api(`/api/classic_matches/${matchId}/start`, {method: "POST"});
    renderClassicMatchDraft(res);
  } catch (e) {
    showError(detailBox, `Could not start this match: ${e.message || e}`);
  }
}

function classicAutoLineupHtml(auto) {
  const rows = auto.lineup.map(s => `<tr><td>${s.position}</td><td>${s.name}</td></tr>`).join("");
  const bench = auto.bench.length ? `<p class="muted">Bench: ${auto.bench.join(", ")}</p>` : "";
  return `
    <h4>${auto.name} (auto-drafted from their real pool)</h4>
    <table class="classic-auto-lineup"><tbody>${rows}</tbody></table>
    ${bench}`;
}

function renderClassicMatchDraft(startRes) {
  const match = startRes.match;
  const focus = startRes.focus;
  const auto = startRes.auto;
  const focusIsHome = match.focus_team === "home";
  const detailBox = document.getElementById("classic-match-detail");
  detailBox.innerHTML = `
    <h3>${match.display_name}</h3>
    <p class="muted">${match.blurb} Real score: ${match.real_score}.</p>
    <p class="muted">Base objectives: ${match.base_objectives.join(" / ")}</p>
    <p class="muted">Bonus objectives: ${match.bonus_objectives.join(" / ")}</p>
    <div class="row">
      <div style="flex:1" id="panel-classic_focus"></div>
      <div style="flex:1" id="panel-classic_auto">${classicAutoLineupHtml(auto)}</div>
    </div>
    <div class="row">
      <button id="classic-kickoff-btn">Kick off</button>
      <span class="muted" id="classic-kickoff-status"></span>
    </div>
    <div id="classic-live-area"></div>
    <div id="classic-results-area"></div>`;

  classicFocusBuilder = new TeamBuilder("classic_focus", {
    title: `Draft ${focus.name}'s XV (${focusIsHome ? "home" : "away"})`,
    fixedName: focus.name, fixedPool: focus.pool,
  });

  document.getElementById("classic-kickoff-btn").onclick = async () => {
    const status = document.getElementById("classic-kickoff-status");
    if (!classicFocusBuilder.teamId) {
      showError(status, `Click "Save team" first.`);
      return;
    }
    document.getElementById("classic-results-area").innerHTML = "";
    setStatus(status, "kicking off...");
    try {
      const homeTeamId = focusIsHome ? classicFocusBuilder.teamId : auto.team_id;
      const awayTeamId = focusIsHome ? auto.team_id : classicFocusBuilder.teamId;
      const state = await api("/api/match/live/start", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({home_team_id: homeTeamId, away_team_id: awayTeamId}),
      });
      setStatus(status, "");
      renderLiveMatchState(state, (finishedState) => {
        completeClassicMatch(match.id, finishedState.session_id);
      }, "classic-live-area", null, "classic-live-area");
    } catch (e) {
      showError(status, "Error: " + e.message);
    }
  };
}

function classicObjectiveListHtml(items, passed) {
  if (!items.length) return "<p class=\"muted\">(none in this mode)</p>";
  return `<ul>${items.map(o => `<li>${passed ? "✓" : "✗"} ${o.description}</li>`).join("")}</ul>`;
}

async function completeClassicMatch(matchId, sessionId) {
  const resultsBox = document.getElementById("classic-results-area");
  resultsBox.innerHTML = `<p class="muted">Grading against the real match's story...</p>`;
  try {
    const res = await api(`/api/classic_matches/${matchId}/complete`, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({session_id: sessionId}),
    });
    resultsBox.innerHTML = `
      <h3>Result: ${starsHtml(res.stars, res.star_cap)} (real score: ${res.real_score})</h3>
      <p class="muted">Best ever for this match: ${starsHtml(res.best_stars, res.star_cap)}</p>
      <h4>Objectives met</h4>
      ${classicObjectiveListHtml(res.objectives_passed, true)}
      <h4>Objectives not met</h4>
      ${classicObjectiveListHtml(res.objectives_failed, false)}`;
    await loadClassicMatchesList();
  } catch (e) {
    showError(resultsBox, `Could not grade this match: ${e.message || e}`);
  }
}

boot();
