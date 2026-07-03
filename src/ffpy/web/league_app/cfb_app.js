const { createApp } = Vue;

createApp({
  data() {
    return {
      page: "leagues",
      leagueId: null,
      leagues: [],
      league: null,
      teams: [],
      standings: [],
      pool: [],
      draft: null,
      settings: {},
      transactions: [],
      selectedTeamId: "",
      week: 1,
      loading: false,
      error: "",
      status: "",
      newLeagueName: "My CFB League",
      draftEventSource: null,
    };
  },
  computed: {
    selectedTeam() {
      return this.teams.find((t) => t.league_team_id === this.selectedTeamId);
    },
  },
  mounted() {
    this.loadLeagues();
    const m = window.location.pathname.match(/\/cfb\/leagues\/([^/]+)/);
    if (m) {
      this.leagueId = m[1];
      this.page = "home";
      this.loadLeague();
    }
  },
  methods: {
    clearMessages() {
      this.error = "";
      this.status = "";
    },
    async fetchJson(path, opts = {}) {
      const resp = await fetch(path.startsWith("/") ? path : `/api/cfb/${path}`, {
        headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
        ...opts,
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.detail || resp.statusText);
      return data;
    },
    async loadLeagues() {
      this.loading = true;
      try {
        this.leagues = await this.fetchJson("leagues");
      } catch (e) {
        this.error = e.message;
      } finally {
        this.loading = false;
      }
    },
    async createLeague() {
      this.clearMessages();
      try {
        const r = await this.fetchJson("leagues", {
          method: "POST",
          body: JSON.stringify({ name: this.newLeagueName, season: 2024, num_teams: 4 }),
        });
        this.status = `Created ${r.name}`;
        await this.loadLeagues();
        this.openLeague(r.league_id);
      } catch (e) {
        this.error = e.message;
      }
    },
    openLeague(id) {
      this.leagueId = id;
      this.page = "home";
      window.history.pushState({}, "", `/cfb/leagues/${id}`);
      this.loadLeague();
    },
    async loadLeague() {
      if (!this.leagueId) return;
      this.loading = true;
      try {
        this.league = await this.fetchJson(`leagues/${this.leagueId}`);
        this.settings = this.league.settings || {};
        this.teams = await this.fetchJson(`leagues/${this.leagueId}/teams`);
        if (this.teams.length && !this.selectedTeamId) {
          this.selectedTeamId = this.teams[0].league_team_id;
        }
        const st = await this.fetchJson(`leagues/${this.leagueId}/standings?through_week=${this.week}`);
        this.standings = st.standings || [];
      } catch (e) {
        this.error = e.message;
      } finally {
        this.loading = false;
      }
    },
    async loadPool() {
      const r = await this.fetchJson(`leagues/${this.leagueId}/player-pool?week=${this.week}&available_only=true`);
      this.pool = r.players || [];
    },
    async loadDraft() {
      try {
        this.draft = await this.fetchJson(`leagues/${this.leagueId}/draft`);
      } catch {
        this.draft = null;
      }
    },
    async startDraft() {
      this.draft = await this.fetchJson(`leagues/${this.leagueId}/draft/start`, { method: "POST" });
      this.connectDraftEvents();
    },
    connectDraftEvents() {
      if (this.draftEventSource) this.draftEventSource.close();
      this.draftEventSource = new EventSource(`/api/cfb/leagues/${this.leagueId}/draft/events`);
      this.draftEventSource.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.board) this.draft = msg.board;
        } catch {}
      };
    },
    async saveSettings() {
      await this.fetchJson(`leagues/${this.leagueId}`, {
        method: "PATCH",
        body: JSON.stringify(this.settings),
      });
      this.status = "Settings saved";
    },
    async loadTransactions() {
      const r = await this.fetchJson(`leagues/${this.leagueId}/transactions`);
      this.transactions = r.transactions || [];
    },
    go(page) {
      this.page = page;
      this.clearMessages();
      if (page === "players") this.loadPool();
      if (page === "draft") this.loadDraft();
      if (page === "transactions") this.loadTransactions();
      if (page === "settings") this.settings = { ...(this.league.settings || {}) };
    },
  },
  template: `
    <div class="shell">
      <header class="app-header">
        <h1>FFPy College Fantasy</h1>
        <nav>
          <a href="/" class="nav-link">NFL Leagues</a>
          <a href="#" class="nav-link" :class="{ active: page === 'leagues' }" @click.prevent="page='leagues'; loadLeagues()">My Leagues</a>
          <template v-if="leagueId">
            <a href="#" class="nav-link" :class="{ active: page === 'home' }" @click.prevent="go('home')">Home</a>
            <a href="#" class="nav-link" :class="{ active: page === 'players' }" @click.prevent="go('players')">Players</a>
            <a href="#" class="nav-link" :class="{ active: page === 'draft' }" @click.prevent="go('draft')">Draft</a>
            <a href="#" class="nav-link" :class="{ active: page === 'transactions' }" @click.prevent="go('transactions')">Transactions</a>
            <a href="#" class="nav-link" :class="{ active: page === 'settings' }" @click.prevent="go('settings')">Settings</a>
          </template>
        </nav>
      </header>
      <div v-if="error" class="message error">{{ error }}</div>
      <div v-if="status" class="message success">{{ status }}</div>

      <div v-if="page === 'leagues'" class="card">
        <h2 class="card-title">College Leagues</h2>
        <div style="display:flex;gap:8px;margin-bottom:12px">
          <input v-model="newLeagueName" placeholder="League name" />
          <button @click="createLeague">Create League</button>
        </div>
        <div v-if="loading" class="small">Loading…</div>
        <div v-else class="league-grid">
          <div v-for="lg in leagues" :key="lg.league_id" class="league-card" @click="openLeague(lg.league_id)">
            <h3>{{ lg.name }}</h3>
            <div class="league-meta">{{ lg.season }} · {{ lg.num_teams }} teams</div>
          </div>
        </div>
      </div>

      <div v-if="page === 'home' && league" class="card">
        <h2 class="card-title">{{ league.name }}</h2>
        <p class="small">Season {{ league.season }} · Week {{ week }}</p>
        <h4>Standings</h4>
        <table class="data-table">
          <tr v-for="s in standings" :key="s.league_team_id">
            <td>#{{ s.rank }}</td><td>{{ s.team_name }}</td><td>{{ s.points_for }} PF</td>
          </tr>
        </table>
      </div>

      <div v-if="page === 'players'" class="card">
        <h2 class="card-title">Player Pool</h2>
        <table class="data-table">
          <tr v-for="p in pool.slice(0,100)" :key="p.player_id">
            <td>{{ p.full_name }}</td><td>{{ p.position }}</td><td>{{ p.team_key }}</td>
            <td>{{ p.projected_points || '—' }}</td>
          </tr>
        </table>
      </div>

      <div v-if="page === 'draft'" class="card">
        <h2 class="card-title">Draft Room</h2>
        <button v-if="!draft || draft.status === 'none'" @click="startDraft">Start Draft</button>
        <template v-else>
          <p>Status: {{ draft.status }} · Pick {{ draft.current_pick }}/{{ draft.total_picks }}</p>
          <p v-if="draft.on_the_clock_team">On the clock: {{ draft.on_the_clock_team }}</p>
          <ul><li v-for="p in draft.picks" :key="p.pick_number">#{{ p.pick_number }} — {{ p.full_name || 'TBD' }}</li></ul>
        </template>
      </div>

      <div v-if="page === 'transactions'" class="card">
        <h2 class="card-title">Transactions</h2>
        <ul><li v-for="t in transactions" :key="t.transaction_id">{{ t.tx_type }} player {{ t.player_id }} — {{ t.status }}</li></ul>
      </div>

      <div v-if="page === 'settings'" class="card">
        <h2 class="card-title">Commissioner Settings</h2>
        <label>FAAB Budget</label>
        <input type="number" v-model.number="settings.faab_budget" />
        <label>Waiver Type</label>
        <select v-model="settings.waiver_type">
          <option value="none">None</option>
          <option value="faab">FAAB</option>
          <option value="rolling">Rolling</option>
        </select>
        <label>Lineup Lock</label>
        <select v-model="settings.lineup_lock">
          <option value="individual_game">Per Game</option>
          <option value="weekly">Weekly</option>
        </select>
        <button style="margin-top:10px" @click="saveSettings">Save Settings</button>
      </div>
    </div>
  `,
}).mount("#cfb-app");
