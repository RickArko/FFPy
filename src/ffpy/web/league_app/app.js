const { createApp } = Vue;

createApp({
  template: `
    <div class="shell">
      <header class="app-header">
        <h1>FFPy League Manager</h1>
        <nav>
          <a href="#" class="nav-link" :class="{ active: page === 'dashboard' }" @click.prevent="page='dashboard'; loadLeagues()">Dashboard</a>
          <a href="#" class="nav-link" :class="{ active: page === 'import' }" @click.prevent="page='import'; importStep=1">Import</a>
          <a href="/pickem/" class="nav-link" target="_blank">Pick'em</a>
          <a href="/cfb/" class="nav-link">College</a>
          <template v-if="isAuthenticated">
            <span class="small">{{ authUser?.email || 'User' }}</span>
            <button class="btn-ghost" @click="page='account'">Password</button>
            <button class="btn-ghost" @click="signOut">Sign Out</button>
          </template>
          <template v-else-if="browserAuthAvailable">
            <button class="btn-ghost" @click="page='login'">Sign In</button>
          </template>
        </nav>
      </header>

      <div v-if="error" class="message error">{{ error }}</div>
      <div v-if="status" class="message success">{{ status }}</div>

      <!-- LOGIN -->
      <div v-if="page === 'login' || page === 'account'">
        <div v-if="page === 'account' && isAuthenticated" class="card auth-card">
          <h2>Set password</h2>
          <p class="small">Set or change your account password.</p>
          <label>New password</label>
          <input type="password" v-model="authForm.password" placeholder="At least 8 characters" autocomplete="new-password" />
          <label>Confirm password</label>
          <input type="password" v-model="authForm.confirmPassword" placeholder="Repeat password" autocomplete="new-password" />
          <button style="margin-top:10px;width:100%" :disabled="authSubmitting" @click="setPassword()">
            {{ authSubmitting ? 'Saving…' : 'Save password' }}
          </button>
          <button class="btn-ghost" style="margin-top:8px;width:100%" @click="page='dashboard'">Back to dashboard</button>
        </div>
        <div v-else-if="showPasswordRecovery && browserAuthAvailable" class="card auth-card">
          <h2>Choose a new password</h2>
          <p class="small">You opened a password reset link. Set a new password below.</p>
          <label>New password</label>
          <input type="password" v-model="authForm.password" placeholder="At least 8 characters" autocomplete="new-password" />
          <label>Confirm password</label>
          <input type="password" v-model="authForm.confirmPassword" placeholder="Repeat password" autocomplete="new-password" />
          <button style="margin-top:10px;width:100%" :disabled="authSubmitting" @click="completePasswordRecovery()">
            {{ authSubmitting ? 'Saving…' : 'Update password' }}
          </button>
        </div>
        <div v-else-if="browserAuthAvailable" class="card auth-card">
          <div class="auth-toggle">
            <button :class="{ active: authForm.mode === 'signin' }" @click="authForm.mode='signin'">Sign In</button>
            <button :class="{ active: authForm.mode === 'signup' }" @click="authForm.mode='signup'">Create Account</button>
          </div>
          <label>Email</label>
          <input type="email" v-model="authForm.email" placeholder="you@example.com" autocomplete="email" />
          <label>Password</label>
          <input
            type="password"
            v-model="authForm.password"
            :placeholder="authForm.mode === 'signup' ? 'At least 8 characters' : 'Your password'"
            :autocomplete="authForm.mode === 'signup' ? 'new-password' : 'current-password'"
          />
          <template v-if="authForm.mode === 'signup'">
            <label>Confirm password</label>
            <input type="password" v-model="authForm.confirmPassword" placeholder="Repeat password" autocomplete="new-password" />
          </template>
          <button style="margin-top:10px;width:100%" :disabled="authSubmitting" @click="authForm.mode==='signup' ? signUp() : signIn()">
            {{ authSubmitting ? 'Working…' : (authForm.mode==='signup' ? 'Create Account' : 'Sign In') }}
          </button>
          <button
            v-if="authForm.mode === 'signin'"
            class="btn-ghost"
            style="margin-top:8px;width:100%"
            :disabled="authSubmitting || !authForm.email"
            @click="forgotPassword()"
          >
            Forgot password?
          </button>
          <p v-if="pendingVerificationEmail" class="small" style="margin-top:8px">
            Confirmation email sent to {{ pendingVerificationEmail }}. Open the link, then sign in with your password.
          </p>
        </div>
        <div v-else-if="authRequired" class="card auth-card">
          <h2>Authentication Required</h2>
          <p>Browser-based auth is not configured. If you have a dev token, paste it below.</p>
          <input v-model="devToken" placeholder="Paste dev token..." />
          <button style="margin-top:10px;width:100%" :disabled="!devToken.trim()" @click="useDevToken">Authenticate</button>
        </div>
        <div v-else class="card">
          <p>Authentication is not required for this instance.</p>
          <button @click="page='dashboard'">Go to Dashboard</button>
        </div>
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
        <div v-if="authLockedReason" class="card">
          <h2 class="card-title">Sign in to import</h2>
          <p class="small">{{ authLockedReason }}</p>
          <button v-if="browserAuthAvailable" @click="page='login'">Sign In</button>
        </div>
        <div v-else class="card">
          <h2 class="card-title">Import League</h2>
          <div class="wizard-steps">
            <div class="wizard-step" :class="{ active: importStep === 1 }">1. Provider</div>
            <div class="wizard-step" :class="{ active: importStep === 2 }">{{ importProvider === 'sleeper' ? '2. League' : '2. Credentials' }}</div>
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
              <input v-model="importCreds.username" placeholder="macker1477" @keyup.enter="discoverSleeperLeagues" />
              <label>Season</label>
              <input type="number" v-model.number="importSeason" />
              <p class="small">Sleeper is public — no password or API keys needed.</p>
              <button style="margin-top:8px" :disabled="sleeperDiscoverLoading || !importCreds.username" @click="discoverSleeperLeagues">
                {{ sleeperDiscoverLoading ? 'Looking up…' : 'Find my leagues' }}
              </button>
              <div v-if="sleeperLeagues.length" style="margin-top:12px">
                <label>League</label>
                <select v-model="importLeagueId">
                  <option value="">Select league…</option>
                  <option v-for="lg in sleeperLeagues" :key="lg.league_id" :value="String(lg.league_id)">
                    {{ lg.name }} ({{ lg.season }}, {{ lg.status || 'unknown' }})
                  </option>
                </select>
              </div>
              <p v-else-if="sleeperDiscoverAttempted && !sleeperDiscoverLoading" class="small" style="margin-top:8px">
                No leagues for this username/season. Try another season (e.g. 2025 or 2026).
              </p>
            </div>
            <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap;align-items:center">
              <button class="btn-ghost" @click="importStep=1">Back</button>
              <button v-if="importProvider !== 'sleeper'" :disabled="importLoading" @click="saveCredentials">Save Credentials</button>
              <button v-else :disabled="importLoading || sleeperDiscoverLoading" @click="runSleeperImport">
                {{ importLoading ? 'Importing…' : (sleeperDiscoverLoading ? 'Looking up…' : 'Import League') }}
              </button>
              <span v-if="importProvider === 'sleeper' && !importLeagueId && !sleeperDiscoverLoading" class="small">
                Finds your leagues, then imports the selected one.
              </span>
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
              <button class="btn-ghost" @click="refreshLeague()" :disabled="loading">Refresh</button>
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
          <div class="tab" :class="{ active: activeTab === 'draft-help' }" @click="activeTab='draft-help'; ensureDraftHelp()">Draft Help</div>
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
          <div v-for="t in leagueTeams" :key="t.team_id" class="roster-block">
            <strong>{{ t.team_name }}</strong>
            <div class="small">Owner: {{ t.owner_name || 'Unknown' }}</div>
            <table v-if="parseRoster(t.roster_json).length" class="roster-table">
              <thead>
                <tr><th>Player</th><th>Pos</th><th>Team</th></tr>
              </thead>
              <tbody>
                <tr v-for="(p, idx) in parseRoster(t.roster_json)" :key="p.player_id || p.name || idx">
                  <td>{{ p.name }}</td>
                  <td>{{ p.position || '—' }}</td>
                  <td>{{ p.team || '—' }}</td>
                </tr>
              </tbody>
            </table>
            <p v-else class="small">No players on roster.</p>
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
                <td>{{ teamName(m.home_team_id) }}</td>
                <td>{{ m.home_score ?? '-' }}</td>
                <td>{{ teamName(m.away_team_id) }}</td>
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

        <!-- Draft Help -->
        <div v-if="activeTab === 'draft-help'" class="card">
          <h3 class="card-title">Draft Help</h3>
          <p class="small">Top 100 targets ranked by need, ADP value, projections, and weekly correlation with your roster.</p>

          <div class="draft-help-controls">
            <div>
              <label>Your team</label>
              <select v-model="draftHelpPayload.team_id">
                <option value="">Select team…</option>
                <option v-for="t in leagueTeams" :key="t.team_id" :value="t.team_id">
                  {{ t.team_name }} <span v-if="t.owner_name">({{ t.owner_name }})</span>
                </option>
              </select>
            </div>
            <div>
              <label>Pick slots (comma-separated, overrides draft order)</label>
              <input v-model="draftHelpPayload.pick_slots_text" placeholder="1, 20, 21" />
            </div>
            <div>
              <label>Board size</label>
              <input type="number" v-model.number="draftHelpPayload.num_players" min="10" max="200" />
            </div>
          </div>

          <div v-if="draftOrderTeams.length" class="draft-order-section">
            <h4 style="margin-bottom:4px">Draft Order <span class="small">(1st round)</span></h4>
            <div class="draft-order-actions">
              <button class="btn-sm" @click="orderByInverseStandings">Inverse Standings</button>
              <button class="btn-sm" @click="randomizeOrder">Randomize</button>
              <button class="btn-sm" @click="resetDraftOrder">Reset</button>
            </div>
            <table class="draft-order-table">
              <tbody>
                <tr v-for="(t, i) in draftOrderTeams" :key="t.team_id">
                  <td class="pick-num">{{ i + 1 }}.</td>
                  <td class="pick-team">{{ t.team_name }}</td>
                  <td class="pick-record">{{ t.wins }}-{{ t.losses }}{{ t.ties ? '-' + t.ties : '' }}</td>
                  <td class="pick-actions">
                    <button class="btn-icon" @click="moveUp(i)" :disabled="i === 0" title="Move up">▲</button>
                    <button class="btn-icon" @click="moveDown(i)" :disabled="i >= draftOrder.length - 1" title="Move down">▼</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <button style="margin-top:12px" :disabled="draftHelpLoading || !draftHelpPayload.team_id" @click="loadDraftHelp">
            {{ draftHelpLoading ? 'Building board…' : 'Get Draft Recommendations' }}
          </button>

          <div v-if="draftHelpPayload.team_id && parseRoster(selectedTeamRoster).length" class="my-roster-preview">
            <h4>Current roster</h4>
            <div class="roster-chips">
              <span v-for="(p, idx) in parseRoster(selectedTeamRoster)" :key="p.player_id || p.name || idx" class="roster-chip">
                {{ p.name }} <span class="muted">({{ p.position }})</span>
              </span>
            </div>
          </div>

          <div v-if="draftHelp" class="draft-help-results">
            <div v-if="draftHelp.picks && draftHelp.picks.length" class="draft-picks">
              <h4>Recommended picks</h4>
              <div v-for="p in draftHelp.picks" :key="p.pick_slot || p.label" class="draft-pick-card">
                <div class="draft-pick-header">
                  <span class="pick-label">{{ p.label }}</span>
                  <span class="pick-player">{{ p.player }} <span class="muted">({{ p.position }} {{ p.team }})</span></span>
                  <span class="pick-adp muted">ADP {{ p.adp }}</span>
                </div>
                <ul class="reason-list">
                  <li v-for="(reason, i) in p.reasons" :key="i">{{ reason }}</li>
                </ul>
              </div>
            </div>

            <div v-if="draftHelp.roster_needs && draftHelp.roster_needs.length" class="roster-needs">
              <h4>Roster needs</h4>
              <table>
                <thead><tr><th>Slot</th><th>Starters</th><th>Depth</th><th>Gap</th></tr></thead>
                <tbody>
                  <tr v-for="n in draftHelp.roster_needs" :key="n.position">
                    <td>{{ n.position }}</td><td>{{ n.starters }}</td><td>{{ n.depth }}</td><td>{{ n.gap }}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-if="draftHelp.rankings && draftHelp.rankings.length" class="draft-board">
              <h4>Top {{ draftHelp.rankings.length }} targets</h4>
              <table class="draft-board-table">
                <thead>
                  <tr>
                    <th>#</th><th>Player</th><th>Pos</th><th>Team</th><th>ADP</th><th>Proj</th><th>VORP</th><th>Tier</th><th>Why target</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="r in draftHelp.rankings" :key="r.rank" :class="{ 'stack-row': r.stack }">
                    <td>{{ r.rank }}</td>
                    <td>{{ r.player }}</td>
                    <td>{{ r.position }}</td>
                    <td>{{ r.team }}</td>
                    <td>{{ r.adp }}</td>
                    <td>{{ r.projected_ppg }}</td>
                    <td>{{ r.vorp }}</td>
                    <td><span class="tier-badge">{{ r.tier }}</span></td>
                    <td>
                      <ul class="reason-list compact">
                        <li v-for="(reason, i) in r.reasons" :key="i">{{ reason }}</li>
                      </ul>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-if="draftHelp.notes && draftHelp.notes.length" class="draft-notes small">
              <p v-for="(note, i) in draftHelp.notes" :key="i">{{ note }}</p>
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
      sleeperLeagues: [],
      sleeperDiscoverLoading: false,
      sleeperDiscoverAttempted: false,
      optimizePayload: { team_id: "", week: 1 },
      optimizeResult: null,
      optimizeLoading: false,
      draftHelpPayload: { team_id: "", pick_slots_text: "1, 20, 21", num_players: 100 },
      draftHelp: null,
      draftHelpLoading: false,
      draftOrder: [],
      savedDraftOrder: [],
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
        confirmPassword: "",
      },
      authSession: null,
      authUser: null,
      pendingVerificationEmail: null,
      showPasswordRecovery: false,
      devToken: "",
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
    selectedTeamRoster() {
      const team = this.leagueTeams.find((t) => t.team_id === this.draftHelpPayload.team_id);
      return team ? team.roster_json : "[]";
    },
    draftOrderTeams() {
      return this.draftOrder
        .map((tid) => this.leagueTeams.find((t) => t.team_id === tid))
        .filter(Boolean);
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
      if (!res.ok) {
        const detail = payload.detail;
        const message = typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
            : res.status === 401
              ? "Sign in required — use Sign In in the header"
              : `Request failed (HTTP ${res.status})`;
        throw new Error(message);
      }
      return payload;
    },
    async fetchPublicAuthConfig() {
      const res = await fetch("api/auth/config");
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
      this.supabaseClient.auth.onAuthStateChange((event, session) => {
        this.authSession = session;
        if (event === "PASSWORD_RECOVERY") {
          this.showPasswordRecovery = true;
          this.page = "login";
          this.authForm.password = "";
          this.authForm.confirmPassword = "";
        }
        if (!session) {
          this.authUser = null;
          return;
        }
        Promise.resolve().then(() => this.refreshCurrentUser()).catch(() => {});
      });
    },
    async refreshCurrentUser() {
      if (!this.authSession) { this.authUser = null; return; }
      const token = this.currentAccessToken();
      const res = await fetch("api/auth/me", { headers: { Authorization: `Bearer ${token}` } });
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
    _validatePasswordPair() {
      const password = (this.authForm.password || "").trim();
      const confirm = (this.authForm.confirmPassword || "").trim();
      if (password.length < 8) {
        throw new Error("Password must be at least 8 characters.");
      }
      if (password !== confirm) {
        throw new Error("Passwords do not match.");
      }
      return password;
    },
    async signIn() {
      this.clearMessages();
      this.authSubmitting = true;
      try {
        this._ensureSupabase();
        if (!(this.authForm.password || "").trim()) {
          throw new Error("Enter your password.");
        }
        const email = (this.authForm.email || "").trim();
        const password = (this.authForm.password || "").trim();
        const { data, error } = await this.supabaseClient.auth.signInWithPassword({
          email,
          password,
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
    _authRedirectUrl() {
      if (this.authConfig.auth_redirect_url) {
        return this.authConfig.auth_redirect_url;
      }
      const base = (this.authConfig.public_app_url || window.location.origin).replace(/\/$/, "");
      return `${base}/league/`;
    },
    async signUp() {
      this.clearMessages();
      this.authSubmitting = true;
      try {
        this._ensureSupabase();
        const password = this._validatePasswordPair();
        const { data, error } = await this.supabaseClient.auth.signUp({
          email: this.authForm.email.trim(),
          password,
          options: {
            emailRedirectTo: this._authRedirectUrl(),
          },
        });
        if (error) throw error;
        this.authSession = data.session || null;
        this.pendingVerificationEmail = this.authForm.email.trim();
        this.authForm.password = "";
        this.authForm.confirmPassword = "";
        if (data.session) {
          await this.refreshCurrentUser();
          await this.loadLeagues();
          this.page = "dashboard";
          this.status = "Account created. You are signed in.";
          this.pendingVerificationEmail = null;
          return;
        }
        this.status = "Account created. Confirm your email, then sign in with your password.";
      } catch (e) {
        this.error = e.message || "Could not create account";
      } finally {
        this.authSubmitting = false;
      }
    },
    async forgotPassword() {
      this.clearMessages();
      this.authSubmitting = true;
      try {
        this._ensureSupabase();
        const email = (this.authForm.email || "").trim();
        if (!email) throw new Error("Enter your email first.");
        const { error } = await this.supabaseClient.auth.resetPasswordForEmail(email, {
          redirectTo: this._authRedirectUrl(),
        });
        if (error) throw error;
        this.status = `Password reset email sent to ${email}. Open the link to choose a new password.`;
      } catch (e) {
        this.error = e.message || "Could not send reset email";
      } finally {
        this.authSubmitting = false;
      }
    },
    async setPassword() {
      this.clearMessages();
      this.authSubmitting = true;
      try {
        this._ensureSupabase();
        const password = this._validatePasswordPair();
        const { error } = await this.supabaseClient.auth.updateUser({ password });
        if (error) throw error;
        this.authForm.password = "";
        this.authForm.confirmPassword = "";
        this.status = "Password saved. You can sign in with email and password next time.";
        this.page = "dashboard";
      } catch (e) {
        this.error = e.message || "Could not save password";
      } finally {
        this.authSubmitting = false;
      }
    },
    async completePasswordRecovery() {
      this.clearMessages();
      this.authSubmitting = true;
      try {
        this._ensureSupabase();
        const password = this._validatePasswordPair();
        const { error } = await this.supabaseClient.auth.updateUser({ password });
        if (error) throw error;
        this.showPasswordRecovery = false;
        this.authForm.password = "";
        this.authForm.confirmPassword = "";
        await this.refreshCurrentUser();
        await this.loadLeagues();
        this.page = "dashboard";
        this.status = "Password updated. You are signed in.";
      } catch (e) {
        this.error = e.message || "Could not update password";
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
    async useDevToken() {
      this.clearMessages();
      if (!this.devToken.trim()) { this.error = "Enter a dev token"; return; }
      this.authSession = { access_token: this.devToken.trim() };
      this.authUser = null;
      await this.refreshCurrentUser();
      if (this.authUser) {
        this.page = "dashboard";
        await this.loadLeagues();
      } else {
        this.error = "Dev token rejected by server.";
        this.authSession = null;
      }
    },
    clearMessages() {
      this.error = null;
      this.status = null;
    },
    async loadLeagues() {
      this.loading = true;
      try {
        this.leagues = await this.fetchJson("api/leagues");
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
      this.draftHelp = null;
      this.page = "league";
      await this.loadLeagueTeams();
    },
    async loadLeagueTeams() {
      if (!this.selectedLeague) return;
      try {
        this.leagueTeams = await this.fetchJson(`api/leagues/${this.selectedLeague.league_id}/teams`);
      } catch (e) {
        this.error = e.message || "Failed to load teams";
      }
    },
    async loadLeagueMatchups(week) {
      if (!this.selectedLeague) return;
      try {
        this.leagueMatchups = await this.fetchJson(`api/leagues/${this.selectedLeague.league_id}/matchups/${week}`);
      } catch (e) {
        this.error = e.message || "Failed to load matchups";
      }
    },
    async deleteLeague(leagueId) {
      if (!confirm("Delete this league?")) return;
      try {
        await this.fetchJson(`api/leagues/${leagueId}`, { method: "DELETE" });
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
    async refreshLeague() {
      if (!confirm("Refresh league data from the provider?")) return;
      this.loading = true;
      this.status = "";
      this.error = "";
      try {
        const result = await this.fetchJson(
          `api/leagues/${this.selectedLeague.league_id}/refresh`,
          { method: "POST" },
        );
        this.status = `League refreshed — ${result.teams} teams`;
        await this.loadLeagueTeams();
      } catch (e) {
        this.error = e.message || "Refresh failed";
      } finally {
        this.loading = false;
      }
    },
    selectProvider(p) {
      this.importProvider = p;
      this.importCreds = {};
      this.sleeperLeagues = [];
      this.importLeagueId = "";
      this.sleeperDiscoverAttempted = false;
      if (p === "sleeper") {
        this.importCreds = { username: "" };
      } else if (p === "espn") {
        this.importCreds = { swid: "", s2: "" };
      } else if (p === "yahoo") {
        this.importCreds = { client_id: "", client_secret: "", access_token: "" };
      }
      this.importStep = 2;
    },
    async discoverSleeperLeagues() {
      this.clearMessages();
      const username = (this.importCreds.username || "").trim();
      if (!username) {
        this.error = "Enter your Sleeper username";
        return;
      }
      this.sleeperDiscoverLoading = true;
      this.sleeperDiscoverAttempted = true;
      try {
        const season = Number(this.importSeason) || new Date().getFullYear();
        const leagues = await this.fetchJson(
          `api/leagues/sleeper/discover?username=${encodeURIComponent(username)}&season=${season}`,
        );
        this.sleeperLeagues = leagues;
        if (!leagues.length) {
          this.error = `No Sleeper leagues found for ${username} in ${season}. Try 2025 or 2026.`;
          this.importLeagueId = "";
        } else {
          this.importLeagueId = leagues.length === 1 ? String(leagues[0].league_id) : String(this.importLeagueId || "");
          if (leagues.length === 1) {
            this.status = `Found "${leagues[0].name}" — ready to import`;
          } else {
            this.status = `Found ${leagues.length} leagues — pick one from the list`;
          }
        }
        return leagues;
      } catch (e) {
        this.error = e.message || "Could not look up Sleeper leagues";
        return [];
      } finally {
        this.sleeperDiscoverLoading = false;
      }
    },
    async runSleeperImport() {
      this.clearMessages();
      if (!this.importLeagueId) {
        const leagues = await this.discoverSleeperLeagues();
        if (!leagues.length) return;
        if (leagues.length > 1 && !this.importLeagueId) {
          this.error = "Select a league from the list, then click Import League again";
          return;
        }
      }
      await this.runImport();
    },
    async saveCredentials() {
      this.clearMessages();
      try {
        await this.fetchJson("api/leagues/credentials", {
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
        const body = {
          provider: this.importProvider,
          league_id: this.importLeagueId,
          season: Number(this.importSeason),
        };
        if (this.importProvider === "sleeper" && this.importCreds.username) {
          body.sleeper_username = this.importCreds.username.trim();
        }
        const result = await this.fetchJson("api/leagues/import", {
          method: "POST",
          body: JSON.stringify(body),
        });
        this.status = `Imported ${result.teams} teams into league ${result.league_id}`;
        this.importStep = 1;
        this.importProvider = "";
        this.importCreds = {};
        this.importLeagueId = "";
        this.sleeperLeagues = [];
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
        const result = await this.fetchJson(`api/leagues/${this.selectedLeague.league_id}/optimize`, {
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
    ensureDraftHelp() {
      if (!this.draftHelpPayload.team_id && this.leagueTeams.length === 1) {
        this.draftHelpPayload.team_id = this.leagueTeams[0].team_id;
      }
      if (!this.draftHelpPayload.team_id && this.optimizePayload.team_id) {
        this.draftHelpPayload.team_id = this.optimizePayload.team_id;
      }
      if (!this.draftOrder.length && this.leagueTeams.length) {
        this.draftOrder = this.leagueTeams.map((t) => t.team_id);
        this.savedDraftOrder = [...this.draftOrder];
      }
    },
    moveUp(i) {
      if (i <= 0) return;
      const a = this.draftOrder[i];
      this.draftOrder[i] = this.draftOrder[i - 1];
      this.draftOrder[i - 1] = a;
      this.draftOrder = [...this.draftOrder];
    },
    moveDown(i) {
      if (i >= this.draftOrder.length - 1) return;
      const a = this.draftOrder[i];
      this.draftOrder[i] = this.draftOrder[i + 1];
      this.draftOrder[i + 1] = a;
      this.draftOrder = [...this.draftOrder];
    },
    orderByInverseStandings() {
      const sorted = [...this.leagueTeams].sort((a, b) => {
        const wA = a.wins || 0, wB = b.wins || 0;
        if (wA !== wB) return wA - wB;
        return (a.points_for || 0) - (b.points_for || 0);
      });
      this.draftOrder = sorted.map((t) => t.team_id);
    },
    randomizeOrder() {
      const arr = [...this.draftOrder];
      for (let i = arr.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [arr[i], arr[j]] = [arr[j], arr[i]];
      }
      this.draftOrder = arr;
    },
    resetDraftOrder() {
      this.draftOrder = [...this.savedDraftOrder];
    },
    parsePickSlots(text) {
      if (!text || !text.trim()) return null;
      const slots = text.split(",").map((s) => parseInt(s.trim(), 10)).filter((n) => !Number.isNaN(n));
      return slots.length ? slots : null;
    },
    parseRoster(rosterJson) {
      try {
        const entries = JSON.parse(rosterJson || "[]");
        return entries.map((entry) => {
          if (entry && typeof entry === "object") {
            return {
              player_id: entry.player_id,
              name: entry.player || entry.fullName || entry.full_name || "Unknown",
              position: entry.position || "",
              team: entry.team || "",
            };
          }
          return { name: String(entry), position: "", team: "" };
        });
      } catch {
        return [];
      }
    },
    teamName(teamId) {
      const team = this.leagueTeams.find((t) => t.team_id === teamId);
      return team ? team.team_name : teamId;
    },
    async loadDraftHelp() {
      this.clearMessages();
      this.draftHelpLoading = true;
      try {
        const pickSlots = this.parsePickSlots(this.draftHelpPayload.pick_slots_text);
        const body = {
          team_id: this.draftHelpPayload.team_id,
          num_players: this.draftHelpPayload.num_players || 100,
          num_teams: this.leagueTeams.length,
        };
        if (pickSlots) {
          body.pick_slots = pickSlots;
        } else if (this.draftOrder.length) {
          body.draft_order = this.draftOrder;
        }
        const result = await this.fetchJson(
          `api/leagues/${this.selectedLeague.league_id}/draft-help`,
          { method: "POST", body: JSON.stringify(body) },
        );
        this.draftHelp = result;
        this.status = `Draft board ready — ${result.rankings.length} targets`;
      } catch (e) {
        this.error = e.message || "Draft help failed";
      } finally {
        this.draftHelpLoading = false;
      }
    },
  },
}).mount("#app");
