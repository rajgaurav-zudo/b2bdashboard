# Edvoy CRM Design System v1.0.0

Every page of the web app follows this design system: Business Performance purple, set in Figtree.
The files here are the spec, the decisions behind it and a component gallery. They were vendored
from the original release folder, which has since been removed.

## Where things live

The spec refers to the release folder's own layout. In this repo:

| Spec path | Repo path |
|---|---|
| `css/edvoy-crm-design-tokens.css` | `web/src/design-system/edvoy-crm-design-tokens.css` |
| `css/edvoy-crm-components.css` | `web/src/design-system/edvoy-crm-components.css` |
| `fonts/` | `web/src/design-system/fonts/` |
| `gallery/` | `docs/design-system/gallery/` (open the HTML file directly in a browser) |

`web/src/main.tsx` imports both stylesheets ahead of `web/src/index.css`. That file maps the
app's short names (`--card`, `--line`, `--action`, …) onto `--ecrm-*` tokens and styles the
app's own layouts in the design system's language.

## Rules for new UI

- Use a token, never a hex value. If no token fits, extend the design system first.
- Prefer the canonical `.ecrm-*` components.
- Show state with ARIA attributes or `.is-*` classes.
- Cards are flat: a 1px border on `--ecrm-radius-lg`. Only popovers and the drawer get a shadow.
- Purple marks action, selection and structure, and never means good or bad. Use the
  positive and negative colours for that.
- Keep zero, "No target" and "Unavailable" visually distinct.
- Don't add themes, fonts, palettes or gradients.

## Charts

Charts read token values through `token()` and `chartChrome()` in `web/src/ui/Chart.tsx`,
because a canvas cannot resolve `var()`.

The design system defines a single series colour and no categorical palette. Multi-series charts
therefore keep the palette that was checked for colour-vision deficiency: `SERIES` in
`web/src/dashboards/logDashboard/weeks.ts`, and the ratio lines in `Funnel.tsx`. Bars that mean
good or bad use the positive and negative colours.
