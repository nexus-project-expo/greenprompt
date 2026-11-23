# UI design

Goal: looks like a real product, not a homework app. Calm, precise, readable on a projector from 3 metres. Built in Next.js (static export in `web/`, served by FastAPI); plain CSS with the tokens below in one global stylesheet, no UI kit.

If a frontend/UI design skill or plugin is available in Claude Code, load it and follow it, then apply the specifics below.

## Concept: the carbon receipt

The signature element is the **receipt**: every answer gets a small card styled like a printed till receipt (monospace figures, dotted leader lines, a torn/perforated edge or dashed top border). It makes the idea instantly legible: "every AI answer has a cost, here is the bill."

```
GREENPROMPT RECEIPT                 14:32:07
route ..................... small (local)
reason ............. p_hard 0.18, no rules
energy ............... 0.012 Wh  MEASURED
vs large model ......... ~0.24 Wh  est.
saved ......................... 95%
CO2 ......................... 0.008 g
water (on-site) ............... 0 mL
latency ....................... 1.8 s
```

## Visual system

- **Palette (light theme, default):** background `#FAFAF7` (warm off-white), surface `#FFFFFF`, text `#111111`, muted text `#6B6B6B`, hairline borders `#E6E4DE`. One accent only: a deep green `#1F7A4D` used for savings and the "measured" tag. Amber `#B7791F` for "estimated" tags. Red `#B42318` only for errors. No gradients, no neon, no emoji in headings.
- **Type:** Inter (or system sans) for UI, JetBrains Mono / IBM Plex Mono for numbers and the receipt. Base 16px, numbers on dashboard tiles 40-48px, tabular figures.
- **Spacing:** 8px grid. Generous whitespace; max content width ~1100px, centred.
- **Shape:** 10-12px radius on cards, 1px hairline borders instead of heavy shadows (at most one very soft shadow on the receipt).
- **Motion:** none except the live power line and a subtle fade-in of the receipt.

## Layout

- **Top bar:** "GreenPrompt" wordmark left; right side: small backend status pills (`Local model: online`, `Cloud: online`, `Grid factor: CEA vX`). Pills turn amber/red when a backend is down; this doubles as a demo talking point.
- **Chat tab (default):** two columns.
  - Left (~60%): conversation, input box at bottom, an `Accuracy mode` toggle next to the input with a one-line hint ("always use the large model").
  - Right (~40%): the receipt for the latest answer, "why this route" (reasons as small chips), and, when the local model runs, a live GPU power sparkline (watts vs seconds) with the idle baseline drawn as a dashed line and the area above it shaded (that area *is* the energy we count).
- **Dashboard tab:** a row of 4 stat tiles (Requests, Cache hit rate, Energy saved Wh and %, CO2 avoided g), then two charts: cumulative Wh (GreenPrompt vs all-large baseline, two lines) and tier split (horizontal stacked bar: cache / small / large / escalated). Hand-drawn SVG with the palette above, no chart junk, no 3D, no pie charts.
- **Evaluation tab:** headline numbers (energy saved, quality retained, router accuracy, cache false-hit rate) as tiles, a 2x2 router confusion grid, and a short "Method" paragraph plus "Limitations" list in plain text.
- **About/Method popover:** sources for every factor (IEA 2025, Google 2025, CEA), shown when hovering the "est." tag.

## Rules

- Every number has a unit and a measured/estimated tag. Round sensibly (Wh to 3 significant figures, % to whole numbers).
- Empty states are designed: before the first question, the receipt area shows a faint example receipt and "Ask anything to see what it costs."
- Errors are calm one-liners in the receipt area, never Python tracebacks.
- Check the UI at 1366x768 (likely projector resolution) and at full HD. Nothing should need scrolling during the demo flow.
- No framework chrome or dev overlays in the demo build (serve the production static export, never `next dev`).
