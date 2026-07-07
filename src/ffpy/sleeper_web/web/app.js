/* global Vue, supabase */

const { createApp, ref, computed, onMounted } = Vue;

function computeSnakeSlots(position, numTeams, rounds = 3) {
  const slots = [];
  for (let r = 1; r <= rounds; r += 1) {
    if (r % 2 === 1) slots.push((r - 1) * numTeams + position);
    else slots.push(r * numTeams - position + 1);
  }
  return slots;
}

createApp({
  setup() {
    const authConfig = ref(null);
    const session = ref(null);
    const profile = ref(null);
    const franchises = ref([]);
    const teams = ref([]);
    const selectedLeague = ref(null);
    const selectedTeamId = ref("");
    const draftResult = ref(null);
    const loading = ref(true);
    const syncing = ref(false);
    const error = ref("");
    const success = ref("");
    const usernameInput = ref("");
    const numTeams = ref(10);
    const pickSlots = ref([1, 20, 21]);
    const showAdvanced = ref(false);
    let supabaseClient = null;

    const authenticated = computed(() => !!session.value?.access_token);
    const authRequired = computed(() => authConfig.value?.auth_required !== false);

    async function api(path, options = {}) {
      const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
      if (session.value?.access_token) {
        headers.Authorization = `Bearer ${session.value.access_token}`;
      }
      const res = await fetch(path, { ...options, headers });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || res.statusText);
      return data;
    }

    async function loadAuth() {
      authConfig.value = await api("/api/auth/config");
      if (authConfig.value.browser_auth_available) {
        supabaseClient = supabase.createClient(
          authConfig.value.supabase_url,
          authConfig.value.supabase_anon_key,
        );
        const { data } = await supabaseClient.auth.getSession();
        session.value = data.session;
        supabaseClient.auth.onAuthStateChange((_event, newSession) => {
          session.value = newSession;
          if (newSession) refreshData();
        });
      }
    }

    async function refreshData() {
      error.value = "";
      if (!authenticated.value && authRequired.value) return;
      try {
        const profileRes = await api("/api/profile/sleeper");
        profile.value = profileRes.profile;
        franchises.value = await api("/api/franchises");
      } catch (err) {
        if (String(err.message).includes("401")) return;
        error.value = err.message;
      }
    }

    async function signUp() {
      error.value = "";
      const email = prompt("Email");
      const password = prompt("Password (min 6 chars)");
      if (!email || !password) return;
      const { error: signErr } = await supabaseClient.auth.signUp({
        email,
        password,
        options: { emailRedirectTo: authConfig.value.auth_redirect_url },
      });
      if (signErr) error.value = signErr.message;
      else success.value = "Check your email to confirm, then sign in.";
    }

    async function signIn() {
      error.value = "";
      const email = prompt("Email");
      const password = prompt("Password");
      if (!email || !password) return;
      const { error: signErr } = await supabaseClient.auth.signInWithPassword({ email, password });
      if (signErr) error.value = signErr.message;
    }

    async function signOut() {
      if (supabaseClient) await supabaseClient.auth.signOut();
      profile.value = null;
      franchises.value = [];
      selectedLeague.value = null;
    }

    async function linkProfile() {
      error.value = "";
      success.value = "";
      try {
        const res = await api("/api/profile/sleeper", {
          method: "PUT",
          body: JSON.stringify({ username: usernameInput.value.trim() }),
        });
        profile.value = res.profile;
        success.value = `Linked @${profile.value.sleeper_username}`;
      } catch (err) {
        error.value = err.message;
      }
    }

    async function syncFranchises() {
      syncing.value = true;
      error.value = "";
      try {
        const res = await api("/api/franchises/sync", { method: "POST" });
        franchises.value = res.franchises;
        success.value = `Synced ${franchises.value.length} franchise(s)`;
      } catch (err) {
        error.value = err.message;
      } finally {
        syncing.value = false;
      }
    }

    async function refreshFranchise(franchiseId) {
      error.value = "";
      try {
        await api(`/api/franchises/${encodeURIComponent(franchiseId)}/refresh`, { method: "POST" });
        franchises.value = await api("/api/franchises");
        success.value = "Franchise refreshed";
      } catch (err) {
        error.value = err.message;
      }
    }

    async function openSeason(franchise, seasonRow) {
      selectedLeague.value = seasonRow;
      draftResult.value = null;
      try {
        const teamRows = await api(`/api/leagues/${encodeURIComponent(seasonRow.league_id)}/teams`);
        teams.value = teamRows;
        const mine = teamRows.find((t) => profile.value && t.owner_name === profile.value.sleeper_username);
        selectedTeamId.value = mine?.team_id || teamRows[0]?.team_id || "";
        if (seasonRow.season >= 2026 && numTeams.value === 10) {
          pickSlots.value = computeSnakeSlots(1, numTeams.value);
        }
      } catch (err) {
        error.value = err.message;
      }
    }

    async function runDraftHelp() {
      error.value = "";
      if (!selectedLeague.value || !selectedTeamId.value) return;
      try {
        draftResult.value = await api(
          `/api/leagues/${encodeURIComponent(selectedLeague.value.league_id)}/draft-help`,
          {
            method: "POST",
            body: JSON.stringify({
              team_id: selectedTeamId.value,
              num_teams: numTeams.value,
              pick_slots: pickSlots.value,
              num_players: 50,
            }),
          },
        );
      } catch (err) {
        error.value = err.message;
      }
    }

    const snakeCells = computed(() => {
      const cells = [];
      for (let pick = 1; pick <= numTeams.value * 3; pick += 1) {
        cells.push({ pick, mine: pickSlots.value.includes(pick) });
      }
      return cells;
    });

    onMounted(async () => {
      try {
        await loadAuth();
        await refreshData();
      } catch (err) {
        error.value = err.message;
      } finally {
        loading.value = false;
      }
    });

    return {
      authConfig,
      authenticated,
      authRequired,
      profile,
      franchises,
      teams,
      selectedLeague,
      selectedTeamId,
      draftResult,
      loading,
      syncing,
      error,
      success,
      usernameInput,
      numTeams,
      pickSlots,
      showAdvanced,
      snakeCells,
      signUp,
      signIn,
      signOut,
      linkProfile,
      syncFranchises,
      refreshFranchise,
      openSeason,
      runDraftHelp,
    };
  },
  template: `
    <div v-if="loading" class="shell shell-loading"><p>Loading...</p></div>
    <div v-else>
      <header class="app-header">
        <h1>FFPy Sleeper Manager</h1>
        <div>
          <span v-if="profile" class="profile-badge">@{{ profile.sleeper_username }}</span>
          <button v-if="authenticated" class="btn secondary" @click="signOut">Sign out</button>
        </div>
      </header>

      <main class="shell">
        <div v-if="error" class="alert error">{{ error }}</div>
        <div v-if="success" class="alert success">{{ success }}</div>

        <section v-if="authRequired && !authenticated" class="card">
          <h2>Sign in</h2>
          <p class="muted">Create an account or sign in to link your Sleeper profile.</p>
          <div class="form-row">
            <button class="btn" @click="signIn">Sign in</button>
            <button class="btn secondary" @click="signUp">Sign up</button>
          </div>
        </section>

        <section v-if="!authRequired || authenticated" class="card">
          <h2>Link Sleeper</h2>
          <p class="muted">Connect your Sleeper username to discover franchises across seasons.</p>
          <div class="form-row">
            <input v-model="usernameInput" placeholder="Sleeper username (e.g. macker1477)" />
            <button class="btn" @click="linkProfile">Link</button>
          </div>
        </section>

        <section v-if="profile" class="card">
          <h2>Franchises</h2>
          <button class="btn" :disabled="syncing" @click="syncFranchises">
            {{ syncing ? 'Syncing…' : 'Sync all leagues' }}
          </button>
          <div v-for="f in franchises" :key="f.franchise_id" class="card" style="margin-top:12px">
            <h3>{{ f.display_name }}</h3>
            <div class="season-chips">
              <span
                v-for="s in f.seasons"
                :key="s.league_id"
                class="chip"
                :class="{ active: selectedLeague && selectedLeague.league_id === s.league_id }"
                @click="openSeason(f, s)"
              >{{ s.season }} · {{ s.status || 'season' }}</span>
            </div>
            <button class="btn secondary" @click="refreshFranchise(f.franchise_id)">Refresh franchise</button>
          </div>
        </section>

        <section v-if="selectedLeague && teams.length" class="card">
          <h2>Draft Help — {{ selectedLeague.league_name || selectedLeague.season }}</h2>
          <label class="muted">Your team</label>
          <select v-model="selectedTeamId">
            <option v-for="t in teams" :key="t.team_id" :value="t.team_id">{{ t.team_name }} ({{ t.owner_name }})</option>
          </select>

          <p class="muted" style="margin-top:12px">Snake board (3 rounds)</p>
          <div class="snake-board">
            <div v-for="cell in snakeCells" :key="cell.pick" class="snake-cell" :class="{ mine: cell.mine }">{{ cell.pick }}</div>
          </div>

          <button class="btn secondary" @click="showAdvanced = !showAdvanced">{{ showAdvanced ? 'Hide' : 'Advanced' }} pick override</button>
          <div v-if="showAdvanced" class="form-row">
            <input v-model="pickSlots" placeholder="1,20,21" @change="pickSlots = pickSlots.toString().split(',').map(Number)" />
          </div>

          <div class="form-row" style="margin-top:12px">
            <button class="btn" @click="runDraftHelp">Generate draft board</button>
          </div>

          <div v-if="draftResult" class="draft-grid" style="margin-top:16px">
            <div>
              <h3>Recommended picks</h3>
              <div v-for="p in draftResult.picks" :key="p.pick_slot" class="rank-row">
                <strong>#{{ p.pick_slot }}</strong>
                <div>{{ p.player || p.player_name }} <span class="muted">({{ p.position }})</span></div>
              </div>
            </div>
            <div>
              <h3>Top board</h3>
              <div v-for="(r, idx) in draftResult.rankings.slice(0, 15)" :key="r.player || r.player_name || idx" class="rank-row">
                <strong>{{ idx + 1 }}</strong>
                <div>
                  {{ r.player || r.player_name }} ({{ r.position }})
                  <div class="reason">{{ (r.reasons || []).join(' · ') }}</div>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  `,
}).mount("#app");
