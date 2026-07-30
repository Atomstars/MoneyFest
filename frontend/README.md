# Frontend — portfolio UI

React + Vite + Tailwind v4. Consumes the FastAPI JSON API; no state duplicated here.

## Run

Two processes. Backend first:

```bash
python -m app.api
```

Then the UI:

```bash
cd frontend && npm run dev
```

Open http://localhost:5173. Vite proxies `/portfolio`, `/stocks`, etc. to
`127.0.0.1:8000`, so the browser sees one origin and the existing cookie auth
keeps working without CORS. Add new backend prefixes to `proxied` in
`vite.config.ts`.

## Design decisions worth knowing

**Colour is not a free choice here.** The tokens in `src/index.css` are the
validated data-viz reference palette, both modes independently stepped (dark is
*not* an automatic flip of light). The six categorical slots were run through the
palette validator at 6 series in both modes:

| | light | dark |
|---|---|---|
| worst adjacent CVD ΔE | 9.1 | 8.4 |
| worst adjacent normal-vision ΔE | 19.6 | 19.3 |
| contrast vs surface | 3 slots < 3:1 → relief required | all ≥ 3:1 |

Because three light-mode slots fall below 3:1, the **relief rule** applies: the
allocation donut always renders its legend with sector name and weight. That
legend is an accessibility requirement — do not "simplify" it away.

Re-validate if you change any series colour:

```bash
node scripts/validate_palette.js "#2a78d6,#eb6834,#1baf7a,#eda100,#e87ba4,#008300" --mode light
```

**Categorical hues are assigned by entity, in fixed order, never cycled.** A 7th
sector folds into "Other" rather than generating a hue — see `MAX_SLICES` in
`DonutChart.tsx`.

**Green/red is used for money only.** P&L sign is a status, so it uses the
palette's delta steps. Outcome chips stay deliberately neutral: the explanation
layer must never colour like a buy/sell signal. That restraint is inherited from
`DESIGN.md` §0 (no advice) and is the reason this doesn't look like a trading app.

**A missing price renders as `—`, never `0`.** `money(null)` returns an em dash and
unpriced positions are excluded from totals with a visible banner. A data gap must
never be readable as a real loss.

## Structure

```
src/lib/api.ts        typed fetch client
src/lib/format.ts     Indian numbering (lakh/crore), outcome vocabulary
src/components/charts LineChart, DonutChart, Sparkline — hand-built SVG, no chart lib
src/components/ui.tsx chips, cards, theme toggle
src/App.tsx           portfolio dashboard
```

Charts are hand-built SVG rather than a charting library: it keeps the bundle at
~67 kB gzipped, and the mark specs (2px strokes, 2px surface gap between donut
segments, surface-ringed hover markers, no marker on every point) are easier to
honour directly than to fight a library's defaults into.
