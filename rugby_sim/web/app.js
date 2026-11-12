// Clickable "what if" team builder - vanilla JS, no build step.
// Talks only to this project's own Flask API (rugby_sim/webapp.py), which
// wraps the real POOLS / get_all_legends / Player.rating_at / MatchEngine -
// nothing rugby-related is computed here, only rendered.

let POSITIONS = [];
let UNIONS = [];
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
          <select id="${this.side}-union"></select>
          ${seasonSelectHtml(`${this.side}-season`)}
          <button id="${this.side}-load">Load pool</button>
          <span class="muted" id="${this.side}-load-status"></span>
        </div>`;
      const sel = document.getElementById(`${this.side}-union`);
      sel.innerHTML = UNIONS.map(u => `<option value="${u.code}">${u.code} - ${u.name}</option>`).join("");
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
      list.innerHTML = UNIONS.map(u => `<button data-code="${u.code}">${u.code}</button>`).join("");
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
          <button id="${this.side}-hist-add">Add this squad</button>
          <span class="muted" id="${this.side}-hist-status"></span>
        </div>`;
      const compSel = document.getElementById(`${this.side}-hist-comp`);
      const yearSel = document.getElementById(`${this.side}-hist-year`);
      const teamSel = document.getElementById(`${this.side}-hist-team`);
      const status = document.getElementById(`${this.side}-hist-status`);
      let yearData = null; // {year, squads: {name: [players]}}

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
      };
      compSel.onchange = loadYears;
      yearSel.onchange = loadYearData;
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
    const available = this.pool.filter(p => !used.has(p.id) || this.slots[pos] === p.id);
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

async function boot() {
  POSITIONS = await api("/api/positions");
  UNIONS = await api("/api/unions");
  homeBuilder = new TeamBuilder("home");
  awayBuilder = new TeamBuilder("away");
  updateRunButton();
  await setupTournamentUI();

  document.getElementById("run-match").onclick = async () => {
    const seedRaw = document.getElementById("seed").value;
    const status = document.getElementById("run-status");
    status.textContent = "simulating...";
    try {
      const data = await api("/api/match", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          home_team_id: homeBuilder.teamId, away_team_id: awayBuilder.teamId,
          seed: seedRaw ? parseInt(seedRaw, 10) : null,
        }),
      });
      renderReport(data);
      status.textContent = "";
    } catch (e) {
      status.textContent = "Error: " + e.message;
    }
  };
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
  box.innerHTML = `
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
}

// ===================== Tournament mode =====================

let tournamentOptions = null;
const tournamentBuilders = {}; // team name -> TeamBuilder

async function setupTournamentUI() {
  tournamentOptions = await api("/api/tournament/options");
  const container = document.getElementById("tournament-section");
  container.innerHTML = `
    <h2>Tournament mode</h2>
    <div class="row">
      <button data-ttype="real">Real fixture replay</button>
      <button data-ttype="wc2027">2027 Rugby World Cup (real draw)</button>
      <button data-ttype="historical">Historical Rugby World Cup (1995-2023)</button>
      <button data-ttype="historical_sn">Historical Six Nations (2009-2021)</button>
      <button data-ttype="custom">Custom tournament</button>
    </div>
    <div id="tournament-config"></div>
    <div id="tournament-teams"></div>
    <div id="tournament-run-area"></div>
    <div id="tournament-report"></div>`;
  container.querySelectorAll("[data-ttype]").forEach(btn => {
    btn.onclick = () => renderTournamentConfig(btn.dataset.ttype);
  });
}

function renderTournamentConfig(ttype) {
  const cfg = document.getElementById("tournament-config");
  document.getElementById("tournament-teams").innerHTML = "";
  document.getElementById("tournament-run-area").innerHTML = "";
  document.getElementById("tournament-report").innerHTML = "";

  if (ttype === "real") {
    cfg.innerHTML = `
      <div class="row">
        <select id="t-real-key">${tournamentOptions.real_keys.map(k => `<option value="${k}">${k}</option>`).join("")}</select>
        <input type="text" id="t-real-season" value="${tournamentOptions.default_season}" style="width:70px" placeholder="season">
        <button id="t-real-load">Load teams</button>
        <span class="muted" id="t-real-status"></span>
      </div>
      <p class="muted">Pick which team(s) you want to draft yourself - every other
      team auto-drafts its own real pool's best XV, so you don't have to build all of them.</p>`;
    document.getElementById("t-real-load").onclick = async () => {
      const key = document.getElementById("t-real-key").value;
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
        row.innerHTML = `<strong>${name}</strong> <span class="muted">auto-drafted${res.code ? " (" + res.code + ")" : ""}${res.problems.length ? " - " + res.problems.join("; ") : " - ready"}</span>`;
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
        row.innerHTML = `<strong>${name}</strong> <span class="muted">auto-drafted${res.code ? " (" + res.code + ")" : useLegends ? " (Legends)" : ""}${res.problems.length ? " - " + res.problems.join("; ") : " - ready"}</span>
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
          <select class="ap-union">${UNIONS.map(u => `<option value="${u.code}" ${u.code === entry.code ? "selected" : ""}>${u.code} - ${u.name}</option>`).join("")}</select>
          ${seasonSelectHtml("", "2026").replace('<select id="">', '<select class="ap-season">')}
        </div>
        <div class="row">
          <button class="ap-go">Auto-draft</button>
        </div>`;
      const legendsCb = row.querySelector(".ap-legends");
      const unionRow = row.querySelector(".ap-union-row");
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
  const missing = Object.entries(tournamentBuilders).filter(([, b]) => !b.teamId).map(([name]) => name);
  hint.textContent = missing.length ? `Still need: ${missing.join(", ")}` : "All teams ready.";
}

function renderTournamentRunArea(params) {
  const area = document.getElementById("tournament-run-area");
  area.innerHTML = `
    <div class="row">
      <label class="muted">Seed (optional): <input type="number" id="t-seed" style="width:90px"></label>
      <button id="t-run">Run tournament</button>
      <span class="muted" id="t-run-hint"></span>
      <span class="muted" id="t-run-status"></span>
    </div>`;
  updateTournamentRunHint();
  document.getElementById("t-run").onclick = async () => {
    const status = document.getElementById("t-run-status");
    const team_ids = {};
    for (const [name, builder] of Object.entries(tournamentBuilders)) {
      if (!builder.teamId) { status.textContent = `Save team "${name}" first.`; return; }
      team_ids[name] = builder.teamId;
    }
    const seedRaw = document.getElementById("t-seed").value;
    const body = {type: params.type, team_ids, seed: seedRaw ? parseInt(seedRaw, 10) : null};
    if (params.type === "real") { body.key = params.key; body.season = params.season; }
    if (params.type === "world_cup_2027") { body.fixture_mode = document.getElementById("t-wc-mode").value; }
    if (params.type === "historical_world_cup") { body.year = params.year; }
    if (params.type === "historical_six_nations") { body.year = params.year; }
    if (params.type === "custom") {
      body.format = document.getElementById("t-custom-format").value;
      body.pool_count = parseInt(document.getElementById("t-custom-pools").value || "2", 10);
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
}

function standingsTable(rows) {
  const body = rows.map(r => `
    <tr><td>${r.team}</td><td>${r.played}</td><td>${r.won}</td><td>${r.drawn}</td><td>${r.lost}</td>
    <td>${r.points_for}</td><td>${r.points_against}</td><td>${r.points_diff}</td><td>${r.table_points}</td></tr>`).join("");
  return `<table class="stats"><tr><th>Team</th><th>P</th><th>W</th><th>D</th><th>L</th><th>PF</th><th>PA</th><th>+/-</th><th>Pts</th></tr>${body}</table>`;
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
  if (report.pools) {
    for (const [poolName, rows] of Object.entries(report.pools)) {
      html += `<h4>${poolName}</h4>${standingsTable(rows)}`;
    }
  }
  if (report.standings) {
    html += standingsTable(report.standings);
  }
  if (report.bracket && report.bracket.length) {
    for (const rnd of report.bracket) {
      html += `<h4>${rnd.stage}</h4>` + rnd.matches.map(m => `<div>${matchLink(m)}</div>`).join("");
    }
  }
  if (report.champion) {
    html += `<p><strong>Champion: ${report.champion}</strong></p>`;
  }
  html += `<h4>All results (click any match for the full simulation)</h4>`
    + report.results.map(r => `<div>${matchLink(r)}</div>`).join("");
  box.innerHTML = html;

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
