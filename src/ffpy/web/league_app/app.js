const { createApp } = Vue;

createApp({
  template: `
    <div class="shell">
      <header class="app-header">
        <h1>FFPy League Manager</h1>
        <nav>
          <a href="#" class="nav-link" :class="{ active: page === 'dashboard' }" @click.prevent="page='dashboard'; loadLeagues()">Dashboard</a>
          <a href="#" class="nav-link" :class="{ active: page === 'import' }" @click.prevent="page='import'; importStep=1">Import</a>
          <template v-if="isAuthenticated">
            <span class="small">{{ authUser?.email || 'User' }}</span>
            <button class="btn-ghost" @click="signOut">Sign Out</button>
          </template>
          <template v-else>
            <button class="btn-ghost" @click="page='login'">Sign In</button>
          </template>
        </nav>
      </header>

      <div v-if="error" class="message error">{{ error }}</div>
      <div v-if="status" class="message success">{{ status }}</div>

      <!-- LOGIN -->
      <div v-if="page === 'login'" class="card auth-card">
        <div class="auth-toggle">
          <button :class="{ active: authForm.mode === 'signin' }" @click="authForm.mode='signin'">Sign In</button>
          <button :class="{ active: authForm.mode === 'signup' }" @click="authForm.mode='signup'">Create Account</button>
        </div>
        <label>Email</label>
        <input type="email" v-model="authForm.email" placeholder="you@example.com" />
        <label>Password</label>
        <input type="password" v-model="authForm.password" placeholder="••••••••" />
        <button style="margin-top:10px;width:100%" :disabled="authSubmitting" @click="authForm.mode==='signup' ? signUp() : signIn()">
          {{ authSubmitting ? 'Working…' : (authForm.mode==='signup' ? 'Create Account' : 'Sign In') }}
        </button>
        <p v-if="pendingVerificationEmail" class="small" style="margin-top:8px">
          Verification email sent to {{ pendingVerificationEmail }}. Confirm, then sign in.
        </p>
      </div>

      <!-- DASHBOARD -->
      <div v-if="page === 'dashboard'">
        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <h2 class="card-title">Your Leagues</h2>
            <button @click="page='import'; importStep=1">+ Import League</button>
          </div>
          <p v-if="loading" class="small">Loading…</p>
          <div v-else-if="leagues.length === 0" class="small">No leagues imported yet.</div>
          <div v-else class="league-grid">
            <div v-for="league in leagues" :key="league.league_id" class="league-card" @click="viewLeague(league)">
              <h3>{{ league.league_name || 'Unnamed League' }}</h3>
              <div class="league-meta">
                {{ league.provider.toUpperCase() }} · {{ league.season }} · {{ league.scoring_type || 'custom' }}
              </div>
              <div class="league-meta">{{ league.num_teams || '?' }} teams</div>
            </div>
          </div>
        </div>
      </div>

      <!-- IMPORT WIZARD -->
      <div v-if="page === 'import'">
        <div class="card">
          <h2 class="card-title">Import League</h2>
          <div class="wizard-steps">
            <div class="wizard-step" :class="{ active: importStep === 1 }">1. Provider</div>
            <div class="wizard-step" :class="{ active: importStep === 2 }">2. Credentials</div>
            <div class="wizard-step" :class="{ active: importStep === 3 }">3. Import</div>
          </div>

          <!-- Step 1: Provider -->
          <div v-if="importStep === 1">
            <p class="small">Select your fantasy provider</p>
            <div class="provider-grid">
              <div class="provider-btn" :class="{ selected: importProvider === 'espn' }" @click="selectProvider('espn')">ESPN</div>
              <div class="provider-btn" :class="{ selected: importProvider === 'yahoo' }" @click="selectProvider('yahoo')">Yahoo</div>
              <div class="provider-btn" :class="{ selected: importProvider === 'sleeper' }" @click="selectProvider('sleeper')">Sleeper</div>
            </div>
          </div>

          <!-- Step 2: Credentials -->
          <div v-if="importStep === 2">
            <div v-if="importProvider === 'espn'">
              <label>SWID</label>
              <input v-model="importCreds.swid" placeholder="{ABC-123-...}" />
              <label>espn_s2</label>
              <input v-model="importCreds.s2" placeholder="long cookie value" />
            </div>
            <div v-if="importProvider === 'yahoo'">
              <label>Client ID</label>
              <input v-model="importCreds.client_id" placeholder="Yahoo app client id" />
              <label>Client Secret</label>
              <input v-model="importCreds.client_secret" placeholder="Yahoo app client secret" />
              <label>Access Token</label>
              <input v-model="importCreds.access_token" placeholder="OAuth access token" />
              <label>Redirect URI</label>
              <input v-model="importCreds.redirect_uri" placeholder="http://localhost:8001" />
            </div>
            <div v-if="importProvider === 'sleeper'">
              <label>Sleeper Username</label>
              <input v-model="importCreds.username" placeholder="sleeper username" />
              <p class="small">Sleeper does not require credentials for public leagues.</p>
            </div>
            <div style="display:flex;gap:8px;margin-top:12px">
              <button class="btn-ghost" @click="importStep=1">Back</button>
              <button :disabled="importLoading" @click="saveCredentials">Save Credentials</button>
            </div>
          </div>

          <!-- Step 3: League ID & Season -->
          <div v-if="importStep === 3">
            <label>League ID</label>
            <input v-model="importLeagueId" placeholder="e.g. 123456" />
            <label>Season</label>
            <input type="number" v-model.number="importSeason" />
            <div style="display:flex;gap:8px;margin-top:12px">
              <button class="btn-ghost" @click="importStep=2">Back</button>
              <button :disabled="importLoading" @click="runImport">
                {{ importLoading ? 'Importing…' : 'Import League' }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- LEAGUE DETAIL -->
      <div v-if="page === 'league' && selectedLeague">
        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
            <div>
              <h2 class="card-title">{{ selectedLeague.league_name || 'League' }}</h2>
              <div class="small">{{ selectedLeague.provider.toUpperCase() }} · {{ selectedLeague.season }} · {{ selectedLeague.scoring_type || 'custom' }}</div>
            </div>
            <div style="display:flex;gap:8px">
              <button class="btn-danger" @click="deleteLeague(selectedLeague.league_id)">Delete</button>
              <button class="btn-ghost" @click="page='dashboard'">Back</button>
            </div>
          </div>
        </div>

        <div class="tabs">
          <div class="tab" :class="{ active: activeTab === 'standings' }" @click="activeTab='standings'">Standings</div>
          <div class="tab" :class="{ active: activeTab === 'rosters' }" @click="activeTab='rosters'">Rosters</div>
          <div class="tab" :class="{ active: activeTab === 'matchups' }" @click="activeTab='matchups'; loadLeagueMatchups(1)">Matchups</div>
          <div class="tab" :class="{ active: activeTab === 'optimizer' }" @click="activeTab='optimizer'">Optimizer</div>
        </div>

        <!-- Standings -->
        <div v-if="activeTab === 'standings'" class="card">
          <table>
            <thead>
              <tr><th>Rank</th><th>Team</th><th>W</th><th>L</th><th>T</th><th>PF</th><th>PA</th></tr>
            </thead>
            <tbody>
              <tr v-for="t in leagueTeams" :key="t.team_id">
                <td>{{ t.rank || '-' }}</td>
                <td>{{ t.team_name }}</td>
                <td>{{ t.wins }}</td>
                <td>{{ t.losses }}</td>
                <td>{{ t.ties }}</td>
                <td>{{ t.points_for?.toFixed ? t.points_for.toFixed(1) : t.points_for }}</td>
                <td>{{ t.points_against?.toFixed ? t.points_against.toFixed(1) : t.points_against }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Rosters -->
        <div v-if="activeTab === 'rosters'" class="card">
          <div v-for="t in leagueTeams" :key="t.team_id" style="margin-bottom:14px">
            <strong>{{ t.team_name }}</strong>
            <div class="small">Owner: {{ t.owner_name || 'Unknown' }}</div>
            <div class="small" v-if="t.roster_json">
              Roster: {{ JSON.parse(t.roster_json || '[]').length }} players
            </div>
          </div>
        </div>

        <!-- Matchups -->
        <div v-if="activeTab === 'matchups'" class="card">
          <label>Week</label>
          <input type="number" v-model.number="optimizePayload.week" min="1" max="25" @change="loadLeagueMatchups(optimizePayload.week)" />
          <table v-if="leagueMatchups.length" style="margin-top:10px">
            <thead>
              <tr><th>Home</th><th>Score</th><th>Away</th><th>Score</th></tr>
            </thead>
            <tbody>
              <tr v-for="m in leagueMatchups" :key="m.matchup_id">
                <td>{{ m.home_team_id }}</td>
                <td>{{ m.home_score ?? '-' }}</td>
                <td>{{ m.away_team_id }}</td>
                <td>{{ m.away_score ?? '-' }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="small">No matchups for this week.</p>
        </div>

        <!-- Optimizer -->
        <div v-if="activeTab === 'optimizer'" class="card">
          <label>Team</label>
          <select v-model="optimizePayload.team_id">
            <option value="">Select team…</option>
            <option v-for="t in leagueTeams" :key="t.team_id" :value="t.team_id">{{ t.team_name }}</option>
          </select>
          <label>Week</label>
          <input type="number" v-model.number="optimizePayload.week" min="1" max="25" />
          <button style="margin-top:10px" :disabled="optimizeLoading || !optimizePayload.team_id" @click="runOptimize">
            {{ optimizeLoading ? 'Optimizing…' : 'Optimize Lineup' }}
          </button>
          <div v-if="optimizeResult" style="margin-top:14px">
            <strong>Total Projected: {{ optimizeResult.total_projected }}</strong>
            <div v-for="(p, idx) in optimizeResult.lineup" :key="idx" class="lineup-slot">
              <span class="pos">{{ p.position }}</span>
              <span class="name">{{ p.name }}</span>
              <span class="proj">{{ p.projected_points }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  `,
  data() {
    return {
      page: "dashboard",
      leagues: [],
      selectedLeague: null,
      leagueTeams: [],
      leagueMatchups: [],
      activeTab: "standings",
      importStep: 1,
      importProvider: "",
      importCreds: {},
      importSeason: new Date().getFullYear(),
      importLeagueId: "",
      importLoading: false,
      optimizePayload: { team_id: "", week: 1 },
      optimizeResult: null,
      optimizeLoading: false,
      authLoading: true,
      authSubmitting: false,
      authConfig: {
        auth_required: false,
        browser_auth_available: false,
        supabase_url: null,
        supabase_anon_key: null,
        public_app_url: window.location.origin,
      },
      authForm: {
        mode: "signin",
        email: "",
        password: "",
      },
      authSession: null,
      authUser: null,
      pendingVerificationEmail: null,
      supabaseClient: null,
      error: null,
      status: null,
      loading: false,
    };
  },
  computed: {
    authRequired() {
      return Boolean(this.authConfig.auth_required);
    },
    browserAuthAvailable() {
      return Boolean(this.authConfig.browser_auth_available);
    },
    isAuthenticated() {
      return Boolean(this.authSession && this.authSession.access_token);
    },
    isVerifiedUser() {
      return Boolean(this.authUser && this.authUser.email_confirmed);
    },
    authLockedReason() {
      if (!this.authRequired) return null;
      if (this.authLoading) return "Checking session…";
      if (!this.browserAuthAvailable) return "Browser auth unavailable.";
      if (!this.isAuthenticated) return "Sign in required.";
      if (!this.isVerifiedUser) return "Verify your email.";
      return null;
    },
  },
  async mounted() {
    try {
      this.authConfig = await this.fetchPublicAuthConfig();
      await this.initializeBrowserAuth();
    } catch (e) {
      this.error = e.message || "Auth init failed";
    } finally {
      this.authLoading = false;
    }
    if (!this.authLockedReason) {
      await this.loadLeagues();
    }
  },
  methods: {
    currentAccessToken() {
      return this.authSession ? this.authSession.access_token : null;
    },
    buildHeaders(extra = {}, includeJson = true) {
      const h = { ...extra };
      const token = this.currentAccessToken();
      if (includeJson && !h["Content-Type"]) h["Content-Type"] = "application/json";
      if (token && !h.Authorization) h.Authorization = `Bearer ${token}`;
      return h;
    },
    async fetchJson(url, opts = {}) {
      const includeJson = opts.body !== undefined;
      const res = await fetch(url, { ...opts, headers: this.buildHeaders(opts.headers || {}, includeJson) });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(payload.detail || "Request failed");
      return payload;
    },
    async fetchPublicAuthConfig() {
      const res = await fetch("/api/auth/config");
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(payload.detail || "Could not load auth config");
      return payload;
    },
    async initializeBrowserAuth() {
      if (!this.browserAuthAvailable) {
        this.supabaseClient = null;
        this.authSession = null;
        this.authUser = null;
        return;
      }
      if (!globalThis.supabase || typeof globalThis.supabase.createClient !== "function") {
        throw new Error("Supabase browser SDK failed to load.");
      }
      this.supabaseClient = globalThis.supabase.createClient(
        this.authConfig.supabase_url,
        this.authConfig.supabase_anon_key,
        { auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true } },
      );
      const sessionResult = await this.supabaseClient.auth.getSession();
      if (sessionResult.error) throw sessionResult.error;
      this.authSession = sessionResult.data.session;
      await this.refreshCurrentUser();
      this.supabaseClient.auth.onAuthStateChange((_, session) => {
        this.authSession = session;
        if (!session) { this.authUser = null; return; }
        Promise.resolve().then(() => this.refreshCurrentUser()).catch(() => {});
      });
    },
    async refreshCurrentUser() {
      if (!this.authSession) { this.authUser = null; return; }
      const token = this.currentAccessToken();
      const res = await fetch("/api/auth/me", { headers: { Authorization: `Bearer ${token}` } });
      const payload = await res.json().catch(() => ({}));
      this.authUser = payload.user || null;
    },
    _ensureSupabase() {
      if (!this.supabaseClient) {
        if (!this.browserAuthAvailable) {
          throw new Error("Supabase auth is not configured. Set SUPABASE_URL and SUPABASE_BROWSER_KEY.");
        }
        if (!globalThis.supabase || typeof globalThis.supabase.createClient !== "function") {
          throw new Error("Supabase browser SDK failed to load. Check your network connection.");
        }
        throw new Error("Supabase client not initialized. Wait a moment and try again.");
      }
    },
    async signIn() {
      this.clearMessages();
      this.authSubmitting = true;
      try {
        this._ensureSupabase();
        const { data, error } = await this.supabaseClient.auth.signInWithPassword({
          email: this.authForm.email,
          password: this.authForm.password,
        });
        if (error) throw error;
        this.authSession = data.session;
        await this.refreshCurrentUser();
        await this.loadLeagues();
        this.page = "dashboard";
      } catch (e) {
        this.error = e.message || "Sign in failed";
      } finally {
        this.authSubmitting = false;
      }
    },
    async signUp() {
      this.clearMessages();
      this.authSubmitting = true;
      try {
        this._ensureSupabase();
        const { data, error } = await this.supabaseClient.auth.signUp({
          email: this.authForm.email,
          password: this.authForm.password,
        });
        if (error) throw error;
        this.pendingVerificationEmail = this.authForm.email;
        this.status = "Verification email sent. Please confirm and sign in.";
      } catch (e) {
        this.error = e.message || "Sign up failed";
      } finally {
        this.authSubmitting = false;
      }
    },
    async signOut() {
      if (this.supabaseClient) {
        await this.supabaseClient.auth.signOut();
      }
      this.authSession = null;
      this.authUser = null;
      this.leagues = [];
      this.page = "dashboard";
    },
    clearMessages() {
      this.error = null;
      this.status = null;
    },
    async loadLeagues() {
      this.loading = true;
      try {
        this.leagues = await this.fetchJson("/api/leagues");
      } catch (e) {
        this.error = e.message || "Failed to load leagues";
      } finally {
        this.loading = false;
      }
    },
    async viewLeague(league) {
      this.selectedLeague = league;
      this.leagueTeams = [];
      this.leagueMatchups = [];
      this.activeTab = "standings";
      this.optimizeResult = null;
      this.page = "league";
      await this.loadLeagueTeams();
    },
    async loadLeagueTeams() {
      if (!this.selectedLeague) return;
      try {
        this.leagueTeams = await this.fetchJson(`/api/leagues/${this.selectedLeague.league_id}/teams`);
      } catch (e) {
        this.error = e.message || "Failed to load teams";
      }
    },
    async loadLeagueMatchups(week) {
      if (!this.selectedLeague) return;
      try {
        this.leagueMatchups = await this.fetchJson(`/api/leagues/${this.selectedLeague.league_id}/matchups/${week}`);
      } catch (e) {
        this.error = e.message || "Failed to load matchups";
      }
    },
    async deleteLeague(leagueId) {
      if (!confirm("Delete this league?")) return;
      try {
        await this.fetchJson(`/api/leagues/${leagueId}`, { method: "DELETE" });
        this.leagues = this.leagues.filter((l) => l.league_id !== leagueId);
        if (this.selectedLeague && this.selectedLeague.league_id === leagueId) {
          this.page = "dashboard";
          this.selectedLeague = null;
        }
        this.status = "League deleted";
      } catch (e) {
        this.error = e.message || "Delete failed";
      }
    },
    selectProvider(p) {
      this.importProvider = p;
      this.importCreds = {};
      if (p === "sleeper") {
        this.importCreds = { username: "" };
      } else if (p === "espn") {
        this.importCreds = { swid: "", s2: "" };
      } else if (p === "yahoo") {
        this.importCreds = { client_id: "", client_secret: "", access_token: "" };
      }
      this.importStep = 2;
    },
    async saveCredentials() {
      this.clearMessages();
      try {
        await this.fetchJson("/api/leagues/credentials", {
          method: "POST",
          body: JSON.stringify({
            provider: this.importProvider,
            credentials: this.importCreds,
            label: "",
          }),
        });
        this.status = "Credentials saved";
        this.importStep = 3;
      } catch (e) {
        this.error = e.message || "Failed to save credentials";
      }
    },
    async runImport() {
      this.clearMessages();
      this.importLoading = true;
      try {
        const result = await this.fetchJson("/api/leagues/import", {
          method: "POST",
          body: JSON.stringify({
            provider: this.importProvider,
            league_id: this.importLeagueId,
            season: Number(this.importSeason),
          }),
        });
        this.status = `Imported ${result.teams} teams into league ${result.league_id}`;
        this.importStep = 1;
        this.importProvider = "";
        this.importCreds = {};
        this.importLeagueId = "";
        await this.loadLeagues();
        this.page = "dashboard";
      } catch (e) {
        this.error = e.message || "Import failed";
      } finally {
        this.importLoading = false;
      }
    },
    async runOptimize() {
      this.clearMessages();
      this.optimizeLoading = true;
      try {
        const result = await this.fetchJson(`/api/leagues/${this.selectedLeague.league_id}/optimize`, {
          method: "POST",
          body: JSON.stringify(this.optimizePayload),
        });
        this.optimizeResult = result;
      } catch (e) {
        this.error = e.message || "Optimization failed";
      } finally {
        this.optimizeLoading = false;
      }
    },
  },
}).mount("#app");
