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
    selectedStrategy() {
      return this.strategies.find((strategy) => strategy.name === this.singleForm.strategyName) || null;
    },
    compareDisabled() {
      return this.loading || this.compareSelection.length === 0;
    },
  },
  methods: {
    async fetchJson(url, options = {}) {
      const response = await fetch(url, {
        headers: { "Content-Type": "application/json" },
        ...options,
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
    async bootstrap() {
      this.loading = true;
      this.clearMessages();
      try {
        const [strategiesPayload, coveragePayload] = await Promise.all([
          this.fetchJson("/api/strategies"),
          this.fetchJson("/api/coverage"),
        ]);
        this.strategies = strategiesPayload.strategies;
        this.coverage = coveragePayload;
        this.syncDefaultWindow(coveragePayload.default_window);
        this.initializeParams();
        this.status = `Loaded ${this.strategies.length} strategies and ${coveragePayload.rows.length} tracked week windows.`;
      } catch (error) {
        this.error = error.message;
      } finally {
        this.loading = false;
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
  mounted() {
    this.bootstrap();
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
        </div>
      </header>

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

              <button class="action-button" type="button" :disabled="loading" @click="runSingle">
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
