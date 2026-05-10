# design-export — FFPy Pick'em Results panel

Three browser-openable design variants of the Results panel, plus a
canonical `theme.css` they all share. Nothing here is wired into the
live app yet — pick a winner first, then we port.

> **Currently chosen:** Variant C · Stadium. Iteration continues there;
> the other two stay parked as references until the port lands.

## How to view

Easiest path — use the slash command:

```
/design-compare
```

That spins up `python -m http.server -d design-export 8080` in the
background and prints all the URLs. Stop it later with `/design-compare stop`.

Or run the server yourself:

```bash
python -m http.server -d design-export 8080
# then open http://localhost:8080/compare.html
```

Direct files (also work via `file://` if you don't want a server):

- `index.html` — landing page with links to all three variants
- `compare.html` — **side-by-side compare** (best for iteration)
- `variant-a-almanac/index.html`
- `variant-b-broadsheet/index.html`
- `variant-c-stadium/index.html`

The pages render statically — they do **not** call FastAPI. Mock data
mirrors the real `POST /api/backtests/run` shape and lives at
`_data/sample-response.json` (referenced for accuracy; not loaded by
the variants — values are inlined into the HTML for portability).

## What's in each file

```
design-export/
├── index.html                    # variant picker (front door)
├── compare.html                  # side-by-side iframe compare (iteration tool)
├── theme.css                     # canonical project theme — single source of truth
├── _data/
│   └── sample-response.json      # real-shape mock backtest payload
├── variant-a-almanac/index.html  # editorial restraint
├── variant-b-broadsheet/index.html
└── variant-c-stadium/index.html  # scoreboard energy ← preferred
```

## Iterating with `compare.html`

Toolbar controls:

- **Width** — Full / 1280 / 1024 / 768 (tablet) / 375 (mobile). Changes
  every pane simultaneously so you're comparing at the same breakpoint.
- **Panes** — 2 or 3. 2-pane mode defaults to A vs C (current preferred).
  Each pane has its own variant dropdown so you can rearrange freely.
- **Sync scroll** — when on, scrolling any pane drives the others by
  ratio (works for different page heights).
- **Reload all** — hard-reload every iframe at once after editing CSS.

Typical loop:

1. Open `/compare.html`, set 2 panes (A vs C) at 1024px.
2. Edit `theme.css` (e.g. tweak `--teal-deep`, type scale, or radius
   tokens). Both panes pick up the change after Reload All.
3. For a variant-only change (markup/layout in C), edit the pane file
   directly.
4. Once happy, port → `src/ffpy/web/pickem_tester/` (see "Verification
   before merging" below).

## What's the same across all three

- Same color tokens — `--bg`, `--ink`, `--teal`, `--teal-deep`,
  `--gold`, `--rust`, `--success`, `--danger`, `--line`, `--shadow`.
- Same font stack — Avenir Next / Segoe UI body, Georgia display, mono
  for scoreboard digits.
- Same data — one strategy run (AllFavorites, 2022 wk 1–4, 41–21–2,
  64.1% win rate) plus a 3-strategy comparison.
- Same backend contract — the field names match
  `POST /api/backtests/run` exactly, so any winning variant ports
  field-for-field with no schema changes.

## What's different

| Aspect          | A · Almanac                    | B · Broadsheet                  | C · Stadium                    |
| --------------- | ------------------------------ | ------------------------------- | ------------------------------ |
| Win-rate hero   | Engraved on cream, with caption| Right-column figure, deck-sized | Massive on deep-teal slab      |
| Numerals        | Old-style in body, lining hero | Lining throughout               | Monospaced everywhere          |
| Per-week ledger | Striped, dotted underlines     | Dense table, color-graded rates | Per-row CSS bar + W/L badges   |
| Compare layout  | 3-up cards, "Leader" tag       | Agate row-list, italic notes    | Scoreboard cards, leader-card  |
| Energy          | Quiet authority                | Editorial / prose-forward       | Live-game, loudest             |
| Best for        | Reading                        | Skimming + reading              | Glance + decide                |

## The theme

`theme.css` codifies the visual system as CSS custom properties:

- **Color** — preserves all existing `styles.css` tokens, adds
  semantic alts (`--success-soft`, `--danger-soft`, `--teal-faint`,
  `--gold-soft`, `--cream-on-teal`).
- **Type** — adds `--font-display` (Georgia) and `--font-mono`,
  publishes a modular scale (`--fs-xs` … `--fs-display`), line-heights,
  and tracking utilities.
- **Spacing** — `--space-1` … `--space-9` (4 → 64px).
- **Radii** — `--r-xs` … `--r-2xl` (8 → 28px).
- **Elevation** — `--elev-1` / `--elev-2` / `--elev-3` (the existing
  `--shadow` aliases `--elev-3`).
- **Motion** — `--ease-out`, `--duration-fast/base/slow`, plus a
  `prefers-reduced-motion` block that flattens all animations.
- **Helper classes** — `.display`, `.eyebrow`, `.tnum`/`.lnum`/`.osnum`,
  `.cell-good`/`.cell-bad`/`.cell-tie`, `.bar-track` + `.bar-fill`.

Once a variant wins, `theme.css` becomes the foundation everywhere:

1. Merge `theme.css` into `src/ffpy/web/pickem_tester/styles.css` at
   the top, deleting the duplicated `:root` block already there.
2. Port the chosen variant's component CSS into the same file (under a
   `/* === Results panel === */` section header).
3. Replace the Results panel block in the `template:` literal of
   `src/ffpy/web/pickem_tester/app.js` with the chosen variant's
   markup, restoring `v-for` / `{{ }}` bindings.

## Verification before merging

- [ ] `make pickem-web PORT=8000` boots without console errors after
      the port.
- [ ] Real backtest run renders end-to-end with the new panel — not
      just the mock.
- [ ] All three auth states still render: none, local-only, Supabase
      signed-out, Supabase signed-in.
- [ ] DevTools mobile preview at 375px — no horizontal scroll, all
      CTAs reachable, hit targets ≥44px.
- [ ] Diff `styles.css` for new hex colors — anything outside the
      `theme.css` tokens should be justified or removed.
- [ ] No new `<script>` tags or CDN imports introduced.
- [ ] `make test` and `make lint` still green.
