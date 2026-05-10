# Open Design Prompt — FFPy Pick'em Tester

Adapted from `DESIGN-PROMPT.md` for [nexu-io/open-design](https://github.com/nexu-io/open-design),
the FOSS local-first alternative to Claude Design.

Open Design drives your local coding-agent CLIs (Claude Code, Codex, Gemini, etc.)
through skills + design systems. No subscription, no cloud — output lands as real
HTML/CSS in a sandboxed iframe and exports to disk.

---

## 0. One-time setup (outside this repo)

```bash
cd ~/Git
git clone https://github.com/nexu-io/open-design
cd open-design
pnpm install
pnpm tools-dev          # boots daemon + web UI
```

Open the web UI in your browser. It auto-detects Claude Code on your `PATH` —
select it as the agent.

---

## 1. Project setup inside Open Design

When creating the project in the OD welcome dialog:

| Setting              | Value                                                              |
|----------------------|--------------------------------------------------------------------|
| **Skill**            | `tweaks` (component-level redesign — not a full new page)          |
| **Mode**             | `prototype`                                                        |
| **Scenario**         | `engineering` (or `product`)                                       |
| **Design system**    | **None of the built-in 72.** Choose "custom" / "bring your own"    |
| **Agent**            | Claude Code (auto-detected)                                        |
| **Project folder**   | `~/Git/FFPy/design-export/` (so output lands next to the real app) |

> Why `tweaks` and not `saas-landing` / `dashboard`: those skills generate
> standalone pages with their own design system. We want OD to **restyle a
> specific panel inside an existing app**, respecting existing tokens.

> Why "custom" design system: the built-in 72 (Linear, Stripe, Vercel, …) will
> override your warm-cream/teal palette. We provide tokens manually below.

---

## 2. Prompt to paste into the chat surface

```
I'm redesigning the frontend of FFPy Pick'em Strategy Tester — a tool for
backtesting NFL pick'em strategies (e.g. "always pick the favorite") against
historical seasons. This is a tweak/restyle task on an existing Vue app, NOT
a from-scratch generation.

## Stack constraints (hard requirements)

- Vanilla Vue 3 via CDN. No build step, no SFCs, no Tailwind, no PostCSS.
- One stylesheet (styles.css) with CSS custom properties already defined.
- Reuse the existing tokens; do NOT introduce a new palette or font stack.
- No new dependencies. Charts: CSS bars or inline SVG only — do not assume
  Chart.js, D3, or any JS lib.
- Output format: HTML template fragments (drop-in for Vue template strings)
  + a CSS append block for styles.css. No <script> logic.

## Existing design tokens (preserve)

--bg: #f5efe3;          --ink: #1a2f3c;
--surface: rgba(255,252,246,0.86);
--surface-strong: rgba(255,252,246,0.96);
--teal: #0f6776;        --teal-deep: #0a4955;
--gold: #d18f2c;        --rust: #a44621;
--success: #167353;     --danger: #9b2c2c;
--line: rgba(20,53,74,0.14);
--shadow: 0 24px 60px rgba(26,47,60,0.12);
font-family: "Avenir Next", "Segoe UI", "Trebuchet MS", sans-serif;

Aesthetic: warm cream background, deep teal hero, gold/rust accents,
generous radii (~28px hero, ~20px panels), soft shadows.
Think "vintage sports almanac, modernized." NOT generic SaaS.

## App structure (do not reorder — restyle only)

1. Hero — title, subtitle, pills row showing tech/auth state
2. Auth Gate panel — sign-in/sign-up form (Supabase email/password) OR
   signed-in readout with refresh/sign-out actions
3. Test Bench panel — form: strategy picker, season range, week range,
   season type (REG/POST), "require full coverage" toggle, "persist" toggle,
   run button
4. Strategy Compare panel — multi-select of strategies to run together
5. Results panel — CURRENTLY WEAK, this is the main redesign target

## Deliverables (in priority order)

A. **Results panel redesign** (the headline change):
   - Hero metric row: Win Rate big & prominent, then Picks / Correct / ROI
   - Per-week breakdown table: subtle row striping, win/loss color cue
     using --success / --danger
   - Multi-strategy mode: side-by-side cards with a small win-rate bar
     (CSS-only, no chart lib)

B. **Auth state card redesign**:
   - Currently a wall of pills. Replace with a clear binary:
     "Signed in as <email>" with sign-out/refresh actions, OR
     "Sign in to run backtests" with the form.

C. **Light polish on panels 1–4** to match the new Results panel rhythm,
   but do not change layout, spacing tokens, or component order.

## Output structure I expect in the project folder

design-export/
├── results-panel.html        # Vue template fragment for results
├── auth-card.html            # Vue template fragment for auth
├── styles.append.css         # CSS to append to styles.css
└── NOTES.md                  # what changed and why, per section

Do NOT write a new index.html, do NOT scaffold a new Vue app, do NOT
create package.json. This is a tweak, not a generation.
```

---

## 3. Files to attach in the OD chat (drag-drop into the project workspace)

OD's daemon gives the agent real `Read` access against the project folder, so
the cleanest path is to **copy these into the OD project's workspace** before
running the prompt:

```bash
# From the FFPy repo root, after creating the OD project at design-export/:
mkdir -p design-export/_inputs
cp src/ffpy/web/pickem_tester/index.html  design-export/_inputs/
cp src/ffpy/web/pickem_tester/styles.css  design-export/_inputs/
cp src/ffpy/web/pickem_tester/app.js      design-export/_inputs/
```

Then in the prompt, append:

```
Read the current implementation from _inputs/ before designing:
- _inputs/styles.css         — full stylesheet, all tokens defined here
- _inputs/index.html         — shell (just confirms vanilla Vue setup)
- _inputs/app.js             — Vue template string starts around line 537;
                               find `template:` and read the whole literal
```

---

## 4. Sample API payload (paste into chat as a code block)

The Results panel design depends on the actual field shapes. Capture a real
response first:

```bash
make pickem-web PORT=8000 &        # in another terminal
TOKEN="$(make -s pickem-auth-token)"
curl -s -X POST http://127.0.0.1:8000/api/backtests/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy": {"name": "AllFavorites", "params": {}},
    "season_start": 2022, "season_end": 2022,
    "week_start": 1, "week_end": 4,
    "season_type": "REG",
    "require_full_coverage": true,
    "persist": false
  }' | tee design-export/_inputs/sample-response.json
```

Tell the agent in chat: *"The shape of the data the Results panel must
render is in `_inputs/sample-response.json`. Use those exact field names."*

---

## 5. Screenshots

Take after `make pickem-web PORT=8000`:

- `01-signed-out.png` — full page, signed out
- `02-signed-in-empty.png` — signed in, no backtest yet
- `03-results-single.png` — after one backtest
- `04-results-compare.png` — after a compare run with 2+ strategies

Save to `design-export/_inputs/screenshots/` and reference them in chat.

---

## 6. Iterate

OD streams a live `TodoWrite` plan as the agent works. Use it to redirect
mid-flight if the direction is wrong (e.g. "stop — the metric row is too
loud, make Win Rate larger but drop the gradient").

The five-dimensional self-critique runs automatically before the artifact
is finalized; trust it but verify in browser.

---

## 7. Handoff back into FFPy

When OD is done, the artifacts are already at `~/Git/FFPy/design-export/`
(because we set the project folder there in step 1). Then:

1. Show me `design-export/results-panel.html` and `design-export/auth-card.html`.
2. I'll port the markup into the Vue template strings in
   `src/ffpy/web/pickem_tester/app.js`.
3. I'll merge `design-export/styles.append.css` into
   `src/ffpy/web/pickem_tester/styles.css`.
4. Verify in browser with `make pickem-web PORT=8000`.

---

## Notes / gotchas

- **Don't pick a built-in design system in the OD picker.** They're great but
  will fight your existing palette. Custom + explicit tokens in the prompt is
  the cleanest path for a restyle.
- **`tweaks` skill is the right tool.** `saas-landing` / `dashboard` /
  `web-prototype` produce full pages and will ignore your existing structure.
- **OD can import a Claude Design ZIP** (`POST /api/import/claude-design`),
  so if you ever try CD's free tier first, you can move the project into OD
  without redoing the prompt.
- **BYOK note:** since OD is driving Claude Code locally, no Anthropic API key
  is needed beyond what `claude` CLI already uses. The OpenAI-compatible BYOK
  proxy is only relevant if you swap to a non-CLI agent.
