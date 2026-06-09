const { createApp } = Vue;

const emptyPayload = {
  season: null,
  week: 1,
  source: "historical",
  source_label: "Historical Model",
  fallback_used: false,
  message: null,
  position: "ALL",
  positions: ["QB", "RB", "WR", "TE"],
  summary: {
    total_players: 0,
    average_projected_points: 0,
    median_projected_points: 0,
    top_player: null,
    top_projection: 0,
  },
  position_totals: [],
  position_breakdown: {
    QB: [],
    RB: [],
    WR: [],
    TE: [],
  },
  players: [],
};

createApp({
  data() {
    return {
      loading: false,
      error: null,
      search: "",
      sort: {
        key: "projected_points",
        direction: "desc",
      },
      form: {
        source: "historical",
        week: 1,
        position: "ALL",
        top_n: 25,
      },
      payload: { ...emptyPayload },
    };
  },
  computed: {
    positionOptions() {
      return [
        { value: "ALL", label: "All" },
        ...this.payload.positions.map((position) => ({ value: position, label: position })),
      ];
    },
    sourceLabel() {
      const labels = {
        historical: "Historical Model",
        api: "API Data",
        sample: "Sample Data",
      };
      return labels[this.form.source] || "Historical Model";
    },
    visiblePlayers() {
      const query = this.search.toLowerCase();
      const rows = this.payload.players.filter((player) => {
        if (!query) {
          return true;
        }
        return [player.player, player.team, player.position, player.opponent]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(query));
      });

      const direction = this.sort.direction === "asc" ? 1 : -1;
      return [...rows].sort((left, right) => {
        const leftValue = left[this.sort.key];
        const rightValue = right[this.sort.key];
        if (this.sort.key === "projected_points") {
          return (Number(leftValue || 0) - Number(rightValue || 0)) * direction;
        }
        return String(leftValue || "").localeCompare(String(rightValue || "")) * direction;
      });
    },
    topPlayerLine() {
      if (!this.payload.summary.top_player) {
        return "No projection leader for the current filters.";
      }
      return `${this.payload.summary.top_player} leads this view at ${this.formatPoints(
        this.payload.summary.top_projection,
      )} projected points.`;
    },
    maxPositionProjection() {
      return Math.max(
        1,
        ...this.payload.position_totals.map((position) => Number(position.top_projection || 0)),
      );
    },
  },
  methods: {
    buildProjectionUrl() {
      const params = new URLSearchParams({
        source: this.form.source,
        week: String(this.form.week),
        position: this.form.position,
        top_n: String(this.form.top_n),
      });
      return `/api/projections?${params.toString()}`;
    },
    async loadProjections() {
      this.loading = true;
      this.error = null;

      try {
        const response = await fetch(this.buildProjectionUrl());
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(payload.detail || "Could not load projections");
        }
        this.payload = {
          ...emptyPayload,
          ...payload,
          summary: { ...emptyPayload.summary, ...(payload.summary || {}) },
          position_breakdown: {
            ...emptyPayload.position_breakdown,
            ...(payload.position_breakdown || {}),
          },
        };
      } catch (error) {
        this.error = error.message || "Could not load projections";
      } finally {
        this.loading = false;
      }
    },
    async setPosition(position) {
      this.form.position = position;
      await this.loadProjections();
    },
    sortBy(key) {
      if (this.sort.key === key) {
        this.sort.direction = this.sort.direction === "asc" ? "desc" : "asc";
        return;
      }
      this.sort.key = key;
      this.sort.direction = key === "projected_points" ? "desc" : "asc";
    },
    sortMark(key) {
      if (this.sort.key !== key) {
        return "";
      }
      return this.sort.direction === "asc" ? "up" : "down";
    },
    barWidth(value) {
      return Math.max(4, Math.round((Number(value || 0) / this.maxPositionProjection) * 100));
    },
    formatInteger(value) {
      return Number(value || 0).toLocaleString();
    },
    formatPoints(value) {
      return Number(value || 0).toFixed(1);
    },
    formatStat(value) {
      const numeric = Number(value || 0);
      return numeric ? numeric.toLocaleString() : "--";
    },
  },
  async mounted() {
    await this.loadProjections();
  },
}).mount("#projections-app");
