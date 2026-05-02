const { createApp } = Vue;

createApp({
  data() {
    return {
      mode: "single",
      strategies: [],
      coverage: {
        rows: [],
        seasons: [],
        season_summaries: [],
        default_window: {
          season_start: new Date().getFullYear(),
          season_end: new Date().getFullYear(),
          week_start: 1,
          week_end: 18,
          season_type: "REG",
        },
      },
      status: null,
      error: null,
      loading: false,
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
      authSubscription: null,
      singleForm: {
        strategyName: "",
        season_start: new Date().getFullYear(),
        season_end: new Date().getFullYear(),
        week_start: 1,
        week_end: 18,
        season_type: "REG",
        require_full_coverage: true,
        persist: false,
        note: "",
      },
      singleParams: {},
      compareForm: {
        season_start: new Date().getFullYear(),
        season_end: new Date().getFullYear(),
        week_start: 1,
        week_end: 18,
        season_type: "REG",
        require_full_coverage: true,
      },
      compareSelection: [],
      compareParams: {},
      singleResult: null,
      compareResult: null,
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
      if (!this.authRequired) {
        return null;
      }
      if (this.authLoading) {
        return "Checking your current auth session.";
      }
      if (!this.browserAuthAvailable) {
        return "Browser sign-in is unavailable until SUPABASE_URL and SUPABASE_ANON_KEY are configured.";
      }
      if (!this.isAuthenticated) {
        return "Sign in with a verified email to unlock protected backtests.";
      }
      if (!this.isVerifiedUser) {
        return "Verify your email, then refresh your session before running backtests.";
      }
      return null;
    },
    authStateTitle() {
      if (!this.authRequired) {
        return "Open local mode";
      }
      if (this.authLoading) {
        return "Checking session";
      }
      if (!this.browserAuthAvailable) {
        return "Token-only testing";
      }
      if (this.isVerifiedUser) {
        return "Verified and ready";
      }
      if (this.isAuthenticated) {
        return "Signed in, awaiting verification";
      }
      if (this.pendingVerificationEmail) {
        return "Verification email sent";
      }
      return "Sign in required";
    },
    authStateBody() {
      if (!this.authRequired) {
        return "This environment leaves auth off, so the tester behaves like a local sandbox.";
      }
      if (this.authLoading) {
        return "Looking for an existing Supabase session and syncing it with the FastAPI backend.";
      }
      if (!this.browserAuthAvailable) {
        return "The backend auth gate is on, but this page cannot render a Supabase login form without public project config.";
      }
      if (this.isVerifiedUser) {
        return "Your verified session is attached to API requests automatically. Backtests and compare runs are unlocked.";
      }
      if (this.isAuthenticated) {
        return "You are signed in, but the backend still sees this email as unverified. Finish the email confirmation flow, then refresh or sign in again.";
      }
      if (this.pendingVerificationEmail) {
        return `Check ${this.pendingVerificationEmail} for the verification link. Once you confirm, sign in here to unlock protected runs.`;
      }
      return "Create an account or sign in with email/password. Supabase handles the session, and the backend verifies email confirmation before expensive runs.";
    },
    authPillLabel() {
      if (!this.authRequired) {
        return "Auth disabled";
      }
      if (this.isVerifiedUser) {
        return "Verified session";
      }
      return "Auth required";
    },
    authButtonLabel() {
      if (this.authSubmitting) {
        return this.authForm.mode === "signup" ? "Creating account..." : "Signing in...";
      }
      return this.authForm.mode === "signup" ? "Create Account" : "Sign In";
    },
    selectedStrategy() {
      return this.strategies.find((strategy) => strategy.name === this.singleForm.strategyName) || null;
    },
    singleRunDisabled() {
      return this.loading || Boolean(this.authLockedReason);
    },
    compareDisabled() {
      return this.loading || this.compareSelection.length === 0 || Boolean(this.authLockedReason);
    },
  },
  methods: {
    currentAccessToken() {
      return this.authSession ? this.authSession.access_token : null;
    },
    buildHeaders(extraHeaders = {}, includeJsonContentType = true) {
      const headers = { ...extraHeaders };
      const token = this.currentAccessToken();
      if (includeJsonContentType && !headers["Content-Type"]) {
        headers["Content-Type"] = "application/json";
      }
      if (token && !headers.Authorization) {
        headers.Authorization = `Bearer ${token}`;
      }
      return headers;
    },
    async fetchJson(url, options = {}) {
      const includeJsonContentType = options.body !== undefined;
      const response = await fetch(url, {
        ...options,
        headers: this.buildHeaders(options.headers || {}, includeJsonContentType),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || "Request failed");
      }
      return payload;
    },
    syncDefaultWindow(defaultWindow) {
      this.singleForm = {
        ...this.singleForm,
        ...defaultWindow,
      };
      this.compareForm = {
        ...this.compareForm,
        ...defaultWindow,
        require_full_coverage: true,
      };
    },
    initializeParams() {
      if (!this.strategies.length) {
        return;
      }

      const firstStrategy = this.strategies[0];
      this.singleForm.strategyName = this.singleForm.strategyName || firstStrategy.name;

      for (const strategy of this.strategies) {
        const params = {};
        for (const param of strategy.params) {
          params[param.name] = param.default;
        }
        this.compareParams[strategy.name] = { ...params };
        if (strategy.name === this.singleForm.strategyName) {
          this.singleParams = { ...params };
        }
      }

      this.compareSelection = this.strategies.slice(0, 3).map((strategy) => strategy.name);
    },
    onSingleStrategyChange() {
      if (!this.selectedStrategy) {
        return;
      }
      const params = {};
      for (const param of this.selectedStrategy.params) {
        params[param.name] = param.default;
      }
      this.singleParams = params;
    },
    formatPercent(value) {
      return `${(Number(value || 0) * 100).toFixed(1)}%`;
    },
    formatInteger(value) {
      return Number(value || 0).toLocaleString();
    },
    formatParams(params) {
      const entries = Object.entries(params || {});
      if (!entries.length) {
        return ["Default config"];
      }
      return entries.map(([key, value]) => `${key}: ${value}`);
    },
    clearMessages() {
      this.error = null;
      this.status = null;
    },
    async fetchPublicAuthConfig() {
      const response = await fetch("/api/auth/config");
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || "Could not load auth config");
      }
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
        {
          auth: {
            persistSession: true,
            autoRefreshToken: true,
            detectSessionInUrl: true,
          },
        },
      );

      const sessionResult = await this.supabaseClient.auth.getSession();
      if (sessionResult.error) {
        throw sessionResult.error;
      }
      this.authSession = sessionResult.data.session;
      await this.refreshCurrentUser();

      const subscriptionResult = this.supabaseClient.auth.onAuthStateChange((_, session) => {
        this.authSession = session;
        if (!session) {
          this.authUser = null;
          return;
        }
        Promise.resolve()
          .then(() => this.refreshCurrentUser())
          .catch((error) => {
            this.error = error.message || "Could not refresh auth session";
          });
      });
      this.authSubscription = subscriptionResult.data.subscription;
    },
    async refreshCurrentUser() {
      if (!this.authSession) {
        this.authUser = null;
        return;
      }
      const payload = await this.fetchJson("/api/auth/me", { method: "GET" });
      this.authUser = payload.user;
      if (this.authUser && this.authUser.email_confirmed) {
        this.pendingVerificationEmail = null;
      }
    },
    async submitAuthForm() {
      if (!this.supabaseClient) {
        this.error = "Browser sign-in is not configured in this environment.";
        return;
      }

      this.authSubmitting = true;
      this.clearMessages();

      try {
        let result;
        if (this.authForm.mode === "signup") {
          result = await this.supabaseClient.auth.signUp({
            email: this.authForm.email,
            password: this.authForm.password,
            options: {
              emailRedirectTo: this.authConfig.public_app_url || window.location.origin,
            },
          });
        } else {
          result = await this.supabaseClient.auth.signInWithPassword({
            email: this.authForm.email,
            password: this.authForm.password,
          });
        }

        if (result.error) {
          throw result.error;
        }

        this.authSession = result.data.session;
        this.authForm.password = "";

        if (result.data.session) {
          await this.refreshCurrentUser();
          this.pendingVerificationEmail = null;
          this.status = this.isVerifiedUser
            ? "Signed in. Protected backtests are ready."
            : "Signed in, but email verification is still pending.";
          return;
        }

        if (this.authForm.mode === "signup") {
          this.pendingVerificationEmail = this.authForm.email;
          this.status = `Account created. Check ${this.authForm.email} for the verification link, then sign in here.`;
          return;
        }

        this.status = "Sign-in flow completed. Refresh the page if your new session does not appear yet.";
      } catch (error) {
        this.error = error.message || "Authentication failed";
      } finally {
        this.authSubmitting = false;
      }
    },
    async signOut() {
      if (!this.supabaseClient) {
        return;
      }

      this.authSubmitting = true;
      this.clearMessages();

      try {
        const result = await this.supabaseClient.auth.signOut();
        if (result.error) {
          throw result.error;
        }
        this.authSession = null;
        this.authUser = null;
        this.pendingVerificationEmail = null;
        this.status = "Signed out.";
      } catch (error) {
        this.error = error.message || "Could not sign out";
      } finally {
        this.authSubmitting = false;
      }
    },
    async refreshVerificationStatus() {
      if (!this.supabaseClient) {
        this.error = "Browser sign-in is not configured in this environment.";
        return;
      }

      this.authSubmitting = true;
      this.clearMessages();

      try {
        const sessionResult = await this.supabaseClient.auth.getSession();
        if (sessionResult.error) {
          throw sessionResult.error;
        }
        this.authSession = sessionResult.data.session;
        await this.refreshCurrentUser();
        this.status = this.isVerifiedUser
          ? "Email verified. Protected backtests are unlocked."
          : "Verification is still pending. After clicking the email link, sign in again if needed.";
      } catch (error) {
        this.error = error.message || "Could not refresh verification status";
      } finally {
        this.authSubmitting = false;
      }
    },
    ensureProtectedActionReady() {
      if (!this.authLockedReason) {
        return true;
      }
      this.error = this.authLockedReason;
      return false;
    },
    async bootstrap() {
      this.loading = true;
      this.authLoading = true;
      this.clearMessages();
      try {
        this.authConfig = await this.fetchPublicAuthConfig();
        await this.initializeBrowserAuth();
        this.authLoading = false;

        const [strategiesPayload, coveragePayload] = await Promise.all([
          this.fetchJson("/api/strategies"),
          this.fetchJson("/api/coverage"),
        ]);
        this.strategies = strategiesPayload.strategies;
        this.coverage = coveragePayload;
        this.syncDefaultWindow(coveragePayload.default_window);
        this.initializeParams();

        if (this.authLockedReason) {
          this.status = `Loaded ${this.strategies.length} strategies and ${coveragePayload.rows.length} tracked week windows. ${this.authLockedReason}`;
        } else {
          this.status = `Loaded ${this.strategies.length} strategies and ${coveragePayload.rows.length} tracked week windows.`;
        }
      } catch (error) {
        this.error = error.message;
      } finally {
        this.loading = false;
        this.authLoading = false;
      }
    },
    singlePayload() {
      return {
        strategy: {
          name: this.singleForm.strategyName,
          params: this.singleParams,
        },
        season_start: Number(this.singleForm.season_start),
        season_end: Number(this.singleForm.season_end),
        week_start: Number(this.singleForm.week_start),
        week_end: Number(this.singleForm.week_end),
        season_type: this.singleForm.season_type,
        require_full_coverage: this.singleForm.require_full_coverage,
        persist: this.singleForm.persist,
        note: this.singleForm.note || null,
      };
    },
    comparePayload() {
      return {
        strategies: this.compareSelection.map((name) => ({
          name,
          params: this.compareParams[name] || {},
        })),
        season_start: Number(this.compareForm.season_start),
        season_end: Number(this.compareForm.season_end),
        week_start: Number(this.compareForm.week_start),
        week_end: Number(this.compareForm.week_end),
        season_type: this.compareForm.season_type,
        require_full_coverage: this.compareForm.require_full_coverage,
      };
    },
    async runSingle() {
      if (!this.ensureProtectedActionReady()) {
        return;
      }

      this.loading = true;
      this.clearMessages();
      this.compareResult = null;
      try {
        this.singleResult = await this.fetchJson("/api/backtests/run", {
          method: "POST",
          body: JSON.stringify(this.singlePayload()),
        });
        this.status = "Single-strategy backtest complete.";
      } catch (error) {
        this.error = error.message;
      } finally {
        this.loading = false;
      }
    },
    async runCompare() {
      if (!this.ensureProtectedActionReady()) {
        return;
      }

      this.loading = true;
      this.clearMessages();
      this.singleResult = null;
      try {
        this.compareResult = await this.fetchJson("/api/backtests/compare", {
          method: "POST",
          body: JSON.stringify(this.comparePayload()),
        });
        this.status = "Strategy comparison complete.";
      } catch (error) {
        this.error = error.message;
      } finally {
        this.loading = false;
      }
    },
  },
  async mounted() {
    await this.bootstrap();
  },
  beforeUnmount() {
    if (this.authSubscription) {
      this.authSubscription.unsubscribe();
      this.authSubscription = null;
    }
  },
  template: `
    <div class="shell">
      <header class="hero">
        <h1>Pick'em Strategy Tester</h1>
        <p>
          Stress-test historical pick strategies against your local FFPy database with a FastAPI backend
          and a Vue 3 control room tuned for fast iteration.
        </p>
        <div class="hero-strip">
          <span class="pill">Vue 3 frontend</span>
          <span class="pill">FastAPI backend</span>
          <span class="pill">Historical backtests</span>
          <span class="pill">Multi-strategy compare</span>
          <span class="pill">{{ authPillLabel }}</span>
        </div>
      </header>

      <section class="panel auth-panel">
        <div class="panel-header">
          <h2 class="panel-title">Access Gate</h2>
          <p class="panel-subtitle">
            Supabase handles email/password auth in the browser. The FastAPI backend only unlocks expensive backtest routes for verified users.
          </p>
        </div>
        <div class="panel-body">
          <div class="auth-layout">
            <div class="auth-state-card">
              <span class="section-label">Current state</span>
              <h3>{{ authStateTitle }}</h3>
              <p>{{ authStateBody }}</p>
              <div class="hero-strip auth-strip">
                <span class="pill">{{ authPillLabel }}</span>
                <span class="pill" v-if="browserAuthAvailable">Supabase browser sign-in</span>
                <span class="pill" v-if="isVerifiedUser">Protected routes unlocked</span>
              </div>
            </div>

            <div class="auth-card">
              <template v-if="authRequired && browserAuthAvailable">
                <div v-if="isAuthenticated" class="strategy-stack">
                  <div class="field">
                    <label>Signed in as</label>
                    <div class="auth-readout">{{ authUser?.email || authSession?.user?.email || 'Authenticated user' }}</div>
                  </div>
                  <div class="auth-readout auth-readout-soft">
                    {{
                      isVerifiedUser
                        ? 'Email verified. You can run and compare strategies now.'
                        : 'Email verification is still pending. Finish the email confirmation flow, then refresh or sign in again.'
                    }}
                  </div>
                  <div class="inline-actions">
                    <button class="mode-button" type="button" :disabled="authSubmitting" @click="refreshVerificationStatus">
                      {{ authSubmitting ? 'Refreshing...' : 'Refresh Status' }}
                    </button>
                    <button class="mode-button" type="button" :disabled="authSubmitting" @click="signOut">
                      {{ authSubmitting ? 'Working...' : 'Sign Out' }}
                    </button>
                  </div>
                </div>

                <div v-else class="strategy-stack">
                  <div class="mode-switch auth-mode-switch">
                    <button
                      class="mode-button"
                      :class="{ 'is-active': authForm.mode === 'signin' }"
                      type="button"
                      @click="authForm.mode = 'signin'"
                    >
                      Sign In
                    </button>
                    <button
                      class="mode-button"
                      :class="{ 'is-active': authForm.mode === 'signup' }"
                      type="button"
                      @click="authForm.mode = 'signup'"
                    >
                      Create Account
                    </button>
                  </div>

                  <div class="field">
                    <label for="auth-email">Email</label>
                    <input id="auth-email" v-model.trim="authForm.email" type="email" placeholder="you@example.com" />
                  </div>

                  <div class="field">
                    <label for="auth-password">Password</label>
                    <input id="auth-password" v-model="authForm.password" type="password" placeholder="Use a strong password" />
                  </div>

                  <p class="field-help" v-if="authForm.mode === 'signup'">
                    Supabase will send a verification email before protected backtests unlock.
                  </p>
                  <p class="field-help" v-if="pendingVerificationEmail">
                    Waiting on verification for {{ pendingVerificationEmail }}.
                  </p>

                  <button class="action-button" type="button" :disabled="authSubmitting || loading" @click="submitAuthForm">
                    {{ authButtonLabel }}
                  </button>
                </div>
              </template>

              <div v-else-if="authRequired" class="empty-state">
                Browser sign-in is unavailable in this environment. Add SUPABASE_URL and SUPABASE_ANON_KEY for a real Supabase project, or use the local bearer-token workflow.
              </div>

              <div v-else class="empty-state">
                Auth is disabled here, so this page behaves like an open local lab.
              </div>
            </div>
          </div>
        </div>
      </section>

      <div class="content-grid">
        <section class="panel">
          <div class="panel-header">
            <h2 class="panel-title">Test Bench</h2>
            <p class="panel-subtitle">
              Choose a single strategy to inspect week-by-week, or stack several strategies into the same historical window.
            </p>
          </div>
          <div class="panel-body">
            <div class="mode-switch">
              <button
                class="mode-button"
                :class="{ 'is-active': mode === 'single' }"
                type="button"
                @click="mode = 'single'"
              >
                Single Strategy
              </button>
              <button
                class="mode-button"
                :class="{ 'is-active': mode === 'compare' }"
                type="button"
                @click="mode = 'compare'"
              >
                Compare Many
              </button>
            </div>

            <div v-if="authLockedReason" class="empty-state auth-guardrail">
              {{ authLockedReason }}
            </div>

            <div v-if="mode === 'single'" class="strategy-stack">
              <div class="field">
                <label for="single-strategy">Strategy</label>
                <select id="single-strategy" v-model="singleForm.strategyName" @change="onSingleStrategyChange">
                  <option v-for="strategy in strategies" :key="strategy.name" :value="strategy.name">
                    {{ strategy.label }}
                  </option>
                </select>
              </div>

              <div v-if="selectedStrategy" class="strategy-card">
                <div class="strategy-header">
                  <div>
                    <h3>{{ selectedStrategy.label }}</h3>
                    <p>{{ selectedStrategy.description }}</p>
                  </div>
                </div>
                <div class="field-grid" v-if="selectedStrategy.params.length">
                  <div class="field" v-for="param in selectedStrategy.params" :key="param.name">
                    <label :for="'single-' + param.name">{{ param.label }}</label>
                    <input
                      :id="'single-' + param.name"
                      v-model.number="singleParams[param.name]"
                      :min="param.min"
                      :max="param.max"
                      :step="param.step || 'any'"
                      type="number"
                    />
                    <p class="field-help">{{ param.description }}</p>
                  </div>
                </div>
                <p v-else class="field-help">This strategy uses the default pick logic with no tunable parameters.</p>
              </div>

              <div class="field-grid">
                <div class="field">
                  <label for="single-season-start">Season Start</label>
                  <input id="single-season-start" v-model.number="singleForm.season_start" type="number" min="2000" max="2100" />
                </div>
                <div class="field">
                  <label for="single-season-end">Season End</label>
                  <input id="single-season-end" v-model.number="singleForm.season_end" type="number" min="2000" max="2100" />
                </div>
                <div class="field">
                  <label for="single-week-start">Week Start</label>
                  <input id="single-week-start" v-model.number="singleForm.week_start" type="number" min="1" max="25" />
                </div>
                <div class="field">
                  <label for="single-week-end">Week End</label>
                  <input id="single-week-end" v-model.number="singleForm.week_end" type="number" min="1" max="25" />
                </div>
                <div class="field">
                  <label for="single-season-type">Season Type</label>
                  <select id="single-season-type" v-model="singleForm.season_type">
                    <option value="REG">Regular season</option>
                    <option value="POST">Postseason</option>
                    <option value="PRE">Preseason</option>
                  </select>
                </div>
                <div class="field field-full">
                  <label for="single-note">Run Note</label>
                  <textarea id="single-note" v-model="singleForm.note" placeholder="Optional note to save alongside a persisted run"></textarea>
                </div>
              </div>

              <label class="toggle-row">
                <input v-model="singleForm.require_full_coverage" type="checkbox" />
                Require complete weekly spread + score coverage
              </label>

              <label class="toggle-row">
                <input v-model="singleForm.persist" type="checkbox" />
                Persist this run into the backtest tables
              </label>

              <button class="action-button" type="button" :disabled="singleRunDisabled" @click="runSingle">
                {{ loading ? 'Running backtest...' : 'Run Backtest' }}
              </button>
            </div>

            <div v-else class="compare-stack">
              <div class="field-grid">
                <div class="field">
                  <label for="compare-season-start">Season Start</label>
                  <input id="compare-season-start" v-model.number="compareForm.season_start" type="number" min="2000" max="2100" />
                </div>
                <div class="field">
                  <label for="compare-season-end">Season End</label>
                  <input id="compare-season-end" v-model.number="compareForm.season_end" type="number" min="2000" max="2100" />
                </div>
                <div class="field">
                  <label for="compare-week-start">Week Start</label>
                  <input id="compare-week-start" v-model.number="compareForm.week_start" type="number" min="1" max="25" />
                </div>
                <div class="field">
                  <label for="compare-week-end">Week End</label>
                  <input id="compare-week-end" v-model.number="compareForm.week_end" type="number" min="1" max="25" />
                </div>
                <div class="field">
                  <label for="compare-season-type">Season Type</label>
                  <select id="compare-season-type" v-model="compareForm.season_type">
                    <option value="REG">Regular season</option>
                    <option value="POST">Postseason</option>
                    <option value="PRE">Preseason</option>
                  </select>
                </div>
              </div>

              <label class="toggle-row">
                <input v-model="compareForm.require_full_coverage" type="checkbox" />
                Require complete weekly spread + score coverage
              </label>

              <div class="strategy-stack">
                <article class="strategy-card" v-for="strategy in strategies" :key="strategy.name">
                  <div class="strategy-header">
                    <div>
                      <h3>{{ strategy.label }}</h3>
                      <p>{{ strategy.description }}</p>
                    </div>
                    <label class="strategy-toggle">
                      <input :value="strategy.name" v-model="compareSelection" type="checkbox" />
                      Include
                    </label>
                  </div>
                  <div class="field-grid" v-if="compareSelection.includes(strategy.name) && strategy.params.length">
                    <div class="field" v-for="param in strategy.params" :key="param.name">
                      <label :for="'compare-' + strategy.name + '-' + param.name">{{ param.label }}</label>
                      <input
                        :id="'compare-' + strategy.name + '-' + param.name"
                        v-model.number="compareParams[strategy.name][param.name]"
                        :min="param.min"
                        :max="param.max"
                        :step="param.step || 'any'"
                        type="number"
                      />
                    </div>
                  </div>
                </article>
              </div>

              <button class="action-button" type="button" :disabled="compareDisabled" @click="runCompare">
                {{ loading ? 'Comparing strategies...' : 'Compare Strategies' }}
              </button>
            </div>
          </div>
        </section>

        <section class="result-grid">
          <div v-if="status" class="status-banner">{{ status }}</div>
          <div v-if="error" class="error-banner">{{ error }}</div>

          <section class="panel">
            <div class="panel-header">
              <h2 class="panel-title">Coverage Snapshot</h2>
              <p class="panel-subtitle">
                Season and week windows detected in the local database. The default form window follows the latest usable season.
              </p>
            </div>
            <div class="panel-body">
              <div class="coverage-list" v-if="coverage.season_summaries.length">
                <article class="coverage-card" v-for="season in coverage.season_summaries" :key="season.season">
                  <h3>{{ season.season }}</h3>
                  <p>Weeks loaded: {{ season.weeks.join(', ') }}</p>
                  <p>Fully usable: {{ season.fully_usable_weeks.join(', ') || 'None yet' }}</p>
                </article>
              </div>
              <div v-else class="empty-state">
                No historical game coverage was found yet. Load games into the SQLite database, then refresh this page.
              </div>
            </div>
          </section>

          <section v-if="singleResult" class="panel">
            <div class="panel-header">
              <h2 class="panel-title">Single Strategy Results</h2>
              <p class="panel-subtitle">
                Weekly grading and aggregate performance for {{ singleResult.summary.strategy }}.
              </p>
            </div>
            <div class="panel-body">
              <div class="metric-grid">
                <div class="metric-card">
                  <span>Win Rate</span>
                  <strong>{{ formatPercent(singleResult.summary.win_rate) }}</strong>
                </div>
                <div class="metric-card">
                  <span>Correct Picks</span>
                  <strong>{{ formatInteger(singleResult.summary.correct) }}</strong>
                </div>
                <div class="metric-card">
                  <span>Games Graded</span>
                  <strong>{{ formatInteger(singleResult.summary.n_games) }}</strong>
                </div>
                <div class="metric-card">
                  <span>Confidence</span>
                  <strong>{{ formatPercent(singleResult.summary.confidence_pct) }}</strong>
                </div>
              </div>

              <div>
                <span class="param-tag" v-for="tag in formatParams(singleResult.summary.params)" :key="tag">{{ tag }}</span>
                <span v-if="singleResult.summary.run_id" class="param-tag">run_id: {{ singleResult.summary.run_id }}</span>
              </div>

              <div class="table-shell" style="margin-top: 18px;">
                <table>
                  <thead>
                    <tr>
                      <th>Season</th>
                      <th>Week</th>
                      <th>Games</th>
                      <th>Picks</th>
                      <th>Correct</th>
                      <th>Incorrect</th>
                      <th>Ties</th>
                      <th>Win Rate</th>
                      <th>Coverage</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="row in singleResult.weekly_results" :key="row.season + '-' + row.week">
                      <td>{{ row.season }}</td>
                      <td>{{ row.week }}</td>
                      <td>{{ row.n_games }}</td>
                      <td>{{ row.picks_made }}</td>
                      <td>{{ row.correct }}</td>
                      <td>{{ row.incorrect }}</td>
                      <td>{{ row.ties }}</td>
                      <td>{{ formatPercent(row.win_rate) }}</td>
                      <td>{{ formatPercent(row.coverage_rate) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </section>

          <section v-if="compareResult" class="panel">
            <div class="panel-header">
              <h2 class="panel-title">Comparison Leaderboard</h2>
              <p class="panel-subtitle">
                Ranked by win rate, then confidence percentage across {{ compareResult.strategy_count }} strategy runs.
              </p>
            </div>
            <div class="panel-body">
              <div class="table-shell">
                <table>
                  <thead>
                    <tr>
                      <th>Strategy</th>
                      <th>Params</th>
                      <th>Games</th>
                      <th>Correct</th>
                      <th>Incorrect</th>
                      <th>Ties</th>
                      <th>Win Rate</th>
                      <th>Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="row in compareResult.leaderboard" :key="row.strategy + JSON.stringify(row.params)">
                      <td>{{ row.strategy }}</td>
                      <td>{{ formatParams(row.params).join(' | ') }}</td>
                      <td>{{ row.n_games }}</td>
                      <td>{{ row.correct }}</td>
                      <td>{{ row.incorrect }}</td>
                      <td>{{ row.ties }}</td>
                      <td>{{ formatPercent(row.win_rate) }}</td>
                      <td>{{ formatPercent(row.confidence_pct) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </section>

          <section v-if="!singleResult && !compareResult" class="panel">
            <div class="panel-header">
              <h2 class="panel-title">Results Waiting Room</h2>
              <p class="panel-subtitle">
                Run a strategy or a leaderboard compare to populate this side of the dashboard.
              </p>
            </div>
            <div class="panel-body">
              <div class="empty-state">
                The backend is ready. Point the controls at a historical window, launch a test, and the results will land here.
              </div>
            </div>
          </section>
        </section>
      </div>
    </div>
  `,
}).mount("#app");
