// Clickable "what if" team builder - vanilla JS, no build step.
// Talks only to this project's own Flask API (rugby_sim/webapp.py), which
// wraps the real POOLS / get_all_legends / Player.rating_at / MatchEngine -
// nothing rugby-related is computed here, only rendered.

let POSITIONS = [];
let UNIONS = [];
let LOGOS = {};         // code -> "/logos/CODE.png"
let NAME_TO_CODE = {};  // real nation name (incl. historical aliases) -> code

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
        status.textContent = "loading (first time may hit the network)...";
        const players = await api(`/api/pool/${code}?season=${encodeURIComponent(season)}`);
        this.pool = players;
        this.name = this.name || sel.options[sel.selectedIndex].text.split(" - ")[1];
        document.getElementById(`${this.side}-name`).value = this.name;
        status.textContent = `${players.length} players loaded.`;
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
          status.textContent = "loading...";
          const players = await api(`/api/pool/${btn.dataset.code}?season=${encodeURIComponent(season)}`);
          this.pool = this.pool.concat(players);
          btn.classList.add("active");
          status.textContent = `${this.pool.length} players in the mix.`;
        };
      });
    } else if (this.mode === "legends") {
      area.innerHTML = `<div class="row"><button id="${this.side}-load-legends">Load Hall of Fame roster</button>
        <span class="muted" id="${this.side}-load-status"></span></div>`;
      document.getElementById(`${this.side}-load-legends`).onclick = async () => {
        const status = document.getElementById(`${this.side}-load-status`);
        status.textContent = "loading (first time is network-heavy, ~190 pages - cached after)...";
        const players = await api("/api/legends");
        this.pool = players;
        status.textContent = `${players.length} legends loaded.`;
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
        status.textContent = "loading real squads (first time is network-heavy - cached after)...";
        const path = compSel.value === "rwc" ? `/api/historical_rwc/${year}` : `/api/historical_six_nations/${year}`;
        const res = await api(path);
        yearData = res;
        const teamNames = Object.keys(res.squads).sort();
        teamSel.innerHTML = teamNames.map(n => `<option value="${n}">${n}</option>`).join("");
        status.textContent = `${teamNames.length} teams loaded for ${year}.`;
        updateHistLogo();
      };
      compSel.onchange = loadYears;
      yearSel.onchange = loadYearData;
      teamSel.onchange = updateHistLogo;
      document.getElementById(`${this.side}-hist-add`).onclick = () => {
        if (!yearData) return;
        const squad = yearData.squads[teamSel.value] || [];
        this.pool = this.pool.concat(squad);
        status.textContent = `${this.pool.length} players in the mix.`;
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
    const box = document.getElementById(`${this.side}-candidates`);
    box.innerHTML = `<div class="muted">Top candidates for ${pos} (click to assign):</div>` +
      ranked.slice(0, 15).map(p => `
        <div class="candidate" data-id="${p.id}">
          <span>${p.name} (${p.nation}${p.era ? ", " + p.era : ""}) - natural: ${p.natural_position}</span>
          <span class="fit">${p.fit.toFixed(1)}</span>
        </div>`).join("");
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
    const benchCandidates = this.pool.filter(p => !starterIds.has(p.id));
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
      <div class="muted">Bench (optional, click up to 8):</div>
      <div class="row" id="${this.side}-bench-list">
        ${benchCandidates.slice(0, 40).map(p =>
          `<button data-id="${p.id}" class="${this.bench.has(p.id) ? "active" : ""}">${p.name}</button>`
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
      status.textContent = "saving...";
      try {
        const res = await api("/api/team", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            name: this.name, slots: this.slots, captain,
            bench: Array.from(this.bench),
          }),
        });
        this.teamId = res.team_id;
        status.textContent = res.problems.length ? `Saved with issues: ${res.problems.join("; ")}` : "Saved - ready to play.";
        updateRunButton();
      } catch (e) {
        status.textContent = "Error: " + e.message;
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
    hint.textContent = "";
  } else {
    const missing = [];
    if (!homeBuilder.teamId) missing.push("Team A");
    if (!awayBuilder.teamId) missing.push("Team B");
    hint.textContent = `Click "Save team" on ${missing.join(" and ")} first.`;
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
  navTo("screen-mode-select", "What If Rugby Edition", () => showScreen("screen-mode-select"));
}

async function enterFriendlyMode() {
  navTo("screen-friendly", "Friendly match", () => showScreen("screen-friendly"));
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
  if (tournamentInitialized) return;
  tournamentInitialized = true;
  await setupTournamentUI();
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

  navReset();
  document.getElementById("mode-friendly").onclick = enterFriendlyMode;
  document.getElementById("mode-tournament").onclick = enterTournamentMode;

  document.getElementById("run-match").onclick = async () => {
    const seedRaw = document.getElementById("seed").value;
    const status = document.getElementById("run-status");
    const seed = seedRaw ? parseInt(seedRaw, 10) : null;
    const isLive = document.getElementById("live-match-toggle").checked;
    status.textContent = "simulating...";
    try {
      if (isLive) {
        document.getElementById("report").innerHTML = "";
        await startLiveMatch(homeBuilder.teamId, awayBuilder.teamId, seed);
        status.textContent = "";
      } else {
        document.getElementById("live-match-area").innerHTML = "";
        const data = await api("/api/match", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({home_team_id: homeBuilder.teamId, away_team_id: awayBuilder.teamId, seed}),
        });
        renderReport(data);
        status.textContent = "";
      }
    } catch (e) {
      status.textContent = "Error: " + e.message;
    }
  };
}

// ===================== Live (pausable) single match =====================

async function startLiveMatch(homeTeamId, awayTeamId, seed) {
  const state = await api("/api/match/live/start", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({home_team_id: homeTeamId, away_team_id: awayTeamId, seed}),
  });
  renderLiveMatchState(state);
}

// `allowSubsFor`: null/undefined = both sides can substitute (a single
// friendly, where the user built both teams themselves); "home"/"away"
// restricts the "Substitute..." control to just that side (an interactive
// tournament fixture, where the opponent is an auto-drafted/CPU side the
// user shouldn't get to make substitution calls for).
function liveLineupTable(side, lineup, bench, allowSubs) {
  const rows = lineup.map(p => `
    <tr><td>${p.position}</td><td>${p.name}</td>
    <td>${allowSubs ? `<button class="live-sub-btn" data-side="${side}" data-pos="${p.position}">Substitute...</button>` : ""}</td></tr>
  `).join("");
  return `<table class="stats"><tr><th>Position</th><th>Player</th><th></th></tr>${rows}</table>
    <p class="muted">Bench: ${bench.map(p => p.name).join(", ") || "(none left)"}</p>`;
}

function renderLiveMatchState(state, onFinished, boxId, allowSubsFor) {
  const box = document.getElementById(boxId || "live-match-area");
  const homeSubsAllowed = allowSubsFor === undefined || allowSubsFor === null || allowSubsFor === "home";
  const awaySubsAllowed = allowSubsFor === undefined || allowSubsFor === null || allowSubsFor === "away";
  const eventsHtml = state.events.map(e => `<div>[${e.minute}'] ${e.text} (${e.score_home}-${e.score_away})</div>`).join("");
  box.innerHTML = `
    <h3>Live match - paused at ${state.minute}'</h3>
    <div id="scoreline">${state.scoreline}</div>
    <div id="events">${eventsHtml}</div>
    <div class="row">
      <div style="flex:1"><h4>${state.home.name}</h4>${liveLineupTable("home", state.home.lineup, state.home.bench, homeSubsAllowed)}</div>
      <div style="flex:1"><h4>${state.away.name}</h4>${liveLineupTable("away", state.away.lineup, state.away.bench, awaySubsAllowed)}</div>
    </div>
    <div class="row">
      <button id="live-continue">${state.finished ? "Match finished" : "Resume play"}</button>
      <span class="muted" id="live-status"></span>
    </div>
    <div id="live-sub-picker"></div>`;

  box.querySelectorAll(".live-sub-btn").forEach(btn => {
    btn.onclick = () => renderLiveSubPicker(state, btn.dataset.side, btn.dataset.pos, boxId, onFinished, allowSubsFor);
  });

  const continueBtn = document.getElementById("live-continue");
  if (state.finished) {
    continueBtn.disabled = true;
    if (state.result) {
      renderReport(state.result);
    }
    if (onFinished) onFinished(state);
    return;
  }
  continueBtn.onclick = async () => {
    const status = document.getElementById("live-status");
    status.textContent = "resuming...";
    try {
      const next = await api(`/api/match/live/${state.session_id}/continue`, {
        method: "POST", headers: {"Content-Type": "application/json"}, body: "{}",
      });
      renderLiveMatchState(next, onFinished, boxId, allowSubsFor);
    } catch (e) {
      status.textContent = "Error: " + e.message;
    }
  };
}

function renderLiveSubPicker(state, side, position, boxId, onFinished, allowSubsFor) {
  const picker = document.getElementById("live-sub-picker");
  const bench = state[side].bench;
  if (!bench.length) {
    picker.innerHTML = `<p class="muted">No bench players left for ${state[side].name}.</p>`;
    return;
  }
  picker.innerHTML = `
    <div class="row">
      <span class="muted">Bring on for ${state[side].name} at ${position}:</span>
      ${bench.map(p => `<button class="live-sub-pick" data-id="${p.id}">${p.name}</button>`).join("")}
    </div>`;
  picker.querySelectorAll(".live-sub-pick").forEach(btn => {
    btn.onclick = async () => {
      try {
        const next = await api(`/api/match/live/${state.session_id}/substitute`, {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({team: side, position, bench_player_id: parseInt(btn.dataset.id, 10)}),
        });
        renderLiveMatchState(next, onFinished, boxId, allowSubsFor);
      } catch (e) {
        alert("Could not make that substitution: " + e.message);
      }
    };
  });
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

function renderReport(data, targetId) {
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
  const reportHtml = `
    <div id="scoreline">${data.scoreline}</div>
    ${pomLine}
    <div id="events">${data.events.map(e => `<div>[${e.minute}'] ${e.text} (${e.score_home}-${e.score_away})</div>`).join("")}</div>
    <table class="stats">
      <tr><th>Team</th><th>Tries</th><th>Pens</th><th>DGs</th><th>Turnovers</th><th>Errors</th>
      <th>Pens conceded</th><th>Cards Y/R</th><th>Territory</th><th>Injuries</th><th>Subs</th></tr>
      ${statRows}
    </table>
    ${scorerRows ? `<h3>Top scorers</h3><table class="stats">
      <tr><th>Player</th><th>Team</th><th>Pts</th><th>Tries</th><th>Conv</th><th>Pens</th></tr>
      ${scorerRows}
    </table>` : ""}`;
  const snapshotBtnId = `${targetId || "report"}-snapshot-btn`;
  box.innerHTML = reportHtml + snapshotButtonHtml(snapshotBtnId);
  document.getElementById(snapshotBtnId).onclick = () => {
    downloadHtmlSnapshot(data.scoreline, reportHtml, data.scoreline);
  };
}

// ===================== Tournament mode =====================

let tournamentOptions = null;
let squadModeEnabled = false; // "fresh squad every match" toggle, see setupTournamentUI
// name -> TeamBuilder (fixed-lineup mode) | {teamId, name} | {squadPlayerIds, name} (squad mode)
const tournamentBuilders = {};

const TOURNAMENT_TYPE_CARDS = [
  {ttype: "real", title: "Real fixture replay", desc: "Replay the actual fixture list for a real competition (Six Nations, Rugby Championship, Autumn Nations Series) and season."},
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
        status.textContent = "loading fixture list...";
        try {
          const res = await api(`/api/tournament/real/teams?key=${encodeURIComponent(key)}&season=${encodeURIComponent(season)}`);
          status.textContent = `${res.teams.length} teams in this competition.`;
          const entries = res.teams.map(name => ({name, code: res.code_by_nation[name], season}));
          buildTournamentTeamPanels(entries);
          renderTournamentRunArea({type: "real", key, season});
        } catch (e) {
          status.textContent = "Error: " + e.message;
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
      status.textContent = "loading real squads from Wikipedia (first time is network-heavy, ~20 teams - cached after)...";
      try {
        const res = await api(`/api/historical_rwc/${year}`);
        const teamNames = Object.keys(res.squads);
        status.textContent = `${teamNames.length} teams - pools: ` +
          Object.entries(res.pools).map(([p, ts]) => `${p}: ${ts.join(", ")}`).join(" | ");
        const entries = teamNames.map(name => ({name, fixedPool: res.squads[name]}));
        buildTournamentTeamPanels(entries);
        renderTournamentRunArea({type: "historical_world_cup", year: parseInt(year, 10)});
      } catch (e) {
        status.textContent = "Error: " + e.message;
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
      status.textContent = "loading real squads from Wikipedia (first time is network-heavy - cached after)...";
      try {
        const res = await api(`/api/historical_six_nations/${year}`);
        const teamNames = Object.keys(res.squads);
        status.textContent = `${teamNames.length} teams loaded.`;
        const entries = teamNames.map(name => ({name, fixedPool: res.squads[name]}));
        buildTournamentTeamPanels(entries);
        renderTournamentRunArea({type: "historical_six_nations", year: parseInt(year, 10)});
      } catch (e) {
        status.textContent = "Error: " + e.message;
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
    status.textContent = "loading...";
    try {
      const players = legendsCb.checked
        ? await api("/api/legends")
        : await api(`/api/pool/${spUnion.value}?season=${encodeURIComponent(row.querySelector(".sp-season").value)}`);
      tournamentBuilders[name] = {squadPlayerIds: players.map(p => p.id), name};
      status.textContent = `${players.length} players in the pool - ready.`;
      updateTournamentRunHint();
    } catch (e) {
      status.textContent = "Error: " + e.message;
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
  hint.textContent = missing.length ? `Still need: ${missing.join(", ")}` : "All teams ready.";
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
      status.textContent = e.message;
      return;
    }
    status.textContent = "running...";
    try {
      const report = await api("/api/tournament/run", {
        method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body),
      });
      renderTournamentReport(report);
      status.textContent = "";
    } catch (e) {
      status.textContent = "Error: " + e.message;
    }
  };

  document.getElementById("t-run-interactive").onclick = async () => {
    const status = document.getElementById("t-run-status");
    document.getElementById("tournament-report").innerHTML = "";
    let body;
    try {
      body = tournamentRunBody(params);
    } catch (e) {
      status.textContent = e.message;
      return;
    }
    const myTeam = document.getElementById("t-my-team").value || null;
    body.my_team = myTeam;
    status.textContent = "starting tournament...";
    try {
      const state = await api("/api/tournament/start", {
        method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body),
      });
      handleTournamentSessionState(state, status, myTeam);
    } catch (e) {
      status.textContent = "Error: " + e.message;
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

function renderTournamentProgress(resultsSoFar, progress) {
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
  renderTournamentProgress(state.results_so_far, state.progress);
  if (state.status === "error") {
    if (banner) banner.innerHTML = "";
    status.textContent = "Error: " + state.error;
    return;
  }
  if (state.status === "finished") {
    if (banner) banner.innerHTML = "";
    status.textContent = "";
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
  status.textContent = `Your match (${stageLabel}): ${state.home} v ${state.away} - play it out below.`;
  renderLiveMatchState(state.live_match, (finishedState) => {
    // Match just finished - renderLiveMatchState already left its full-time
    // scoreline/events/stats in #tournament-live-area. Don't auto-advance;
    // wait for the user to say they're done looking at it.
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `<button id="t-continue-after-my-match">Continue tournament</button>`;
    liveArea.appendChild(row);
    document.getElementById("t-continue-after-my-match").onclick = async () => {
      status.textContent = "continuing tournament...";
      try {
        const next = await api(`/api/tournament/${state.session_id}/resume`, {method: "POST"});
        handleTournamentSessionState(next, status, myTeam);
      } catch (e) {
        status.textContent = "Error: " + e.message;
      }
    };
  }, "tournament-live-area", mySide);
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

boot();
