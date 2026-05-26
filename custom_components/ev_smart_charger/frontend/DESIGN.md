# Liquid Aurora — Design System

The single design language of the EV Smart Charger dashboard, introduced in v1.11.0 and refined in v1.11.1.

Maintained as a single‑file inline stylesheet inside [ev-smart-charger-dashboard.js](ev-smart-charger-dashboard.js) (function `_inlineStyles()`). This document is the **discoverable surface** of that system — token reference, usage rules, anti‑patterns, and component recipes — so future work can extend the dashboard or build sister cards without re‑deriving the choices.

If you're about to add a new metric tile, a new module accordion, a new device‑frame mockup, or anything visual: read this first. If you're changing existing layout: also read first, then update both the code and this doc in the same PR.

---

## Table of contents

1. [Direction](#direction)
2. [Typography](#typography)
3. [Color](#color)
4. [Motion](#motion)
5. [Spatial system](#spatial-system)
6. [Surface & depth](#surface--depth)
7. [Responsive principles](#responsive-principles)
8. [Component recipes](#component-recipes)
9. [Anti‑patterns](#anti-patterns)
10. [Adding tokens / changing the system](#adding-tokens--changing-the-system)

---

## Direction

**Editorial × Engineering.** A serif italic display font carries the eye; a tabular monospaced face carries the data. System sans carries the body. The combination reads as a *deliberate* dashboard — closer to a magazine technical spread than a generic admin panel.

This is not a "minimalist" system — it commits to a strong typographic voice. It is also not "maximalist" — surfaces stay quiet, color stays restrained, motion stays slow. The differentiation is concentrated in **two moves**:

1. The SOC ring percentage in **Instrument Serif italic** at a generous size.
2. The Weekly Planner mobile cards using full localized weekday names in the same serif italic.

Everything else exists to make those two moments land.

If you remove either, the system stops working. Don't.

---

## Typography

Three font roles, mapped to three font families. Each role has a single justification — no overlap, no "designer's choice" usage.

| Role | Family | Weight / Style | Used for |
|---|---|---|---|
| **Display** | Instrument Serif | 400 italic | SOC ring percentage, hero `<h1>`, Night Charge times, Weekly Planner mobile day names |
| **Mono** | JetBrains Mono | 500 / 600 / 700 | Every numeric readout (kW, A, W, %, kWh), every eyebrow micro‑cap, stepper values, priority pill, ring legend, day‑card kind labels |
| **Body** | SF Pro Display / SF Pro Text → BlinkMacSystemFont → Inter → system | 400 / 500 / 600 | Headings other than hero h1, descriptions, button labels, settings copy, info banners |

Loaded once at the top of `_inlineStyles()`:

```css
@import url('https://fonts.bunny.net/css?family=instrument-serif:400,400i&family=jetbrains-mono:500,600,700&display=swap');
```

[Bunny Fonts](https://fonts.bunny.net) is a GDPR‑friendly Google Fonts mirror. ~50 KB total over both families. `display=swap` ensures FOUT (Flash of Unstyled Text) over FOIT — the dashboard never blocks on the network.

### Custom properties

```css
--evsc-font:         -apple-system, "SF Pro Display", "SF Pro Text", BlinkMacSystemFont, "Inter", "Segoe UI", system-ui, sans-serif;
--evsc-font-display: "Instrument Serif", "Georgia", "Times New Roman", serif;
--evsc-font-mono:    "JetBrains Mono", ui-monospace, "SF Mono", "Menlo", "Consolas", monospace;
```

### Type scale (current)

| Use | Size | Family | Weight | Style |
|---|---|---|---|---|
| Hero `<h1>` | `clamp(24px, 2.2vw, 32px)` | display | 400 | italic |
| SOC ring percentage | 3rem | display | 400 | italic |
| Night Charge time (vv) | 32px | display | 400 | italic |
| Day card name (mobile) | 22px | display | 400 | italic |
| Metric card value | `clamp(1.05rem, 1.8vw, 1.45rem)` | mono | 700 | normal |
| Stepper / time value | 1.05rem | mono | 600 | normal |
| Priority pill label | 0.7rem | mono | 600 | uppercase + 0.16em tracking |
| Eyebrow / kicker | 0.65rem | mono | 500 | uppercase + 0.18em tracking |
| Ring legend | 0.72rem | mono | 500 | tabular‑nums |
| Ring sub label | 0.7rem | mono | 500 | uppercase + 0.18em tracking |
| Body description | 13px | body | 400 | line‑height 1.55, max‑width 42ch |

**Tabular numerics**: every mono numeric readout uses `font-variant-numeric: tabular-nums` so `+ / −` taps nudge the same character slot every time (no horizontal jitter as digits change width).

---

## Color

The base palette is Apple's iOS 18 system colors. On top of that, four **aurora accents** are reserved for *live* / *electric* moments — never for navigation, body text, or anything ambient.

### System colors (muted, ambient)

```css
--evsc-sys-blue:    #007aff;   /* TODAY accent, priority HOME state */
--evsc-sys-green:   #34c759;   /* (reserved fallback)             */
--evsc-sys-mint:    #00c7be;   /* ha-card background blob         */
--evsc-sys-teal:    #30b0c7;   /* metric tile tone                */
--evsc-sys-indigo:  #5856d6;   /* night card illustration         */
--evsc-sys-purple:  #af52de;   /* priority EV_FREE state          */
--evsc-sys-pink:    #ff2d55;   /* (reserved)                      */
--evsc-sys-red:     #ff3b30;   /* (errors, override warnings)     */
--evsc-sys-orange:  #ff9500;   /* metric tile tone (solar)        */
--evsc-sys-yellow:  #ffcc00;   /* (reserved)                      */
--evsc-sys-cyan:    #32ade6;   /* metric tile tone (charging)     */
```

### Aurora accents (saturated, "live")

```css
--evsc-aurora-green:  #00d35a;  /* EV SOC arc, charging pulse dot      */
--evsc-aurora-cyan:   #00d4ff;  /* background aurora blob A            */
--evsc-aurora-violet: #b794ff;  /* Home battery SOC arc, blob B        */
--evsc-aurora-amber:  #ffb84d;  /* reserved for solar warnings (unused) */
```

### Foreground & surface

Light mode (default):

```css
--evsc-bg-1:            #f2f2f7;
--evsc-bg-2:            #e5e5ea;
--evsc-surface:         rgba(255, 255, 255, 0.62);
--evsc-surface-strong:  rgba(255, 255, 255, 0.78);
--evsc-stroke:          rgba(0, 0, 0, 0.07);
--evsc-stroke-strong:   rgba(0, 0, 0, 0.12);
--evsc-fg:              #1c1c1e;
--evsc-fg-mid:          rgba(60, 60, 67, 0.78);
--evsc-fg-low:          rgba(60, 60, 67, 0.55);
```

Dark mode (`@media (prefers-color-scheme: dark)`):

```css
--evsc-bg-1:            #000000;
--evsc-bg-2:            #1c1c1e;
--evsc-surface:         rgba(28, 28, 30, 0.62);
--evsc-surface-strong:  rgba(44, 44, 46, 0.82);
--evsc-stroke:          rgba(255, 255, 255, 0.08);
--evsc-stroke-strong:   rgba(255, 255, 255, 0.16);
--evsc-fg:              #f2f2f7;
--evsc-fg-mid:          rgba(235, 235, 245, 0.6);
--evsc-fg-low:          rgba(235, 235, 245, 0.4);
```

### Use rules

- Aurora accents are **never** used for body text or borders. Only for: ring arcs (`fill`/`stroke`), the charging pulse dot (`background`/`box-shadow`), and the two large background blobs.
- The two background blobs (`aurora-a`, `aurora-b`) are the only place where `--evsc-aurora-cyan` and `--evsc-aurora-violet` appear at scale. Don't add a third blob.
- For "live but ambient" elements (e.g. the priority pill's pulsing dot), use `currentColor` derived from a `.state-*` modifier that maps to a *system* color, not an aurora — keeps the saturated palette rare and meaningful.
- Foreground text uses `--evsc-fg` for primary, `--evsc-fg-mid` for secondary (descriptions, sub labels), `--evsc-fg-low` for tertiary (eyebrows when used alone, hint copy). Never hardcode `#1c1c1e` or `rgba(60,60,67,0.78)` — always reference the token.

---

## Motion

Slow. Atmospheric. Never narrative — the dashboard does not "tell a story" with motion. It breathes.

### Easing

```css
--evsc-spring: cubic-bezier(0.32, 0.72, 0, 1);  /* iOS-spec spring */
```

Used for: card hover lift, switch thumb travel, stepper button press, ring arc stroke‑dashoffset transitions.

### Keyframes

```css
@keyframes floatGlow {
  0%, 100% { transform: translate3d(0, 0, 0) scale(1);   opacity: 0.48; }
  50%      { transform: translate3d(28px, -22px, 0) scale(1.12); opacity: 0.72; }
}
/* 28s on aurora-a, 36s on aurora-b (offset by -11s) */

@keyframes evsc-pulse-slow {
  0%, 100% { opacity: 1;    box-shadow: 0 0 10px currentColor; }
  50%      { opacity: 0.55; box-shadow: 0 0 16px currentColor; }
}
/* 3.2s on .priority-pill::before */

@keyframes evsc-pulse {
  0%, 100% { opacity: 1;    transform: scale(1);    }
  50%      { opacity: 0.55; transform: scale(0.85); }
}
/* 1.4s on .charging-pulse (active charging indicator) */
```

### Reduced motion

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

Universal. Respected.

### What NOT to do

- **No entrance fade‑ins.** The dashboard re-renders on every Home Assistant state update (SOC tick, solar reading, status change, …). With innerHTML replacement, the DOM is rebuilt; CSS entrance animations would replay from scratch on every sensor tick, causing visible flicker every few seconds. The only persistent animations are: aurora floatGlow on pseudo‑elements (which survive innerHTML swaps), and the charging pulse + priority pill pulse, both on elements whose inner state is updated via the live‑update path (no full DOM swap).
- **No scroll‑triggered effects.** Lovelace cards live inside HA's scrollable surface; scroll handlers compete with HA's own.
- **No transitions on `width` / `height`.** Always use `transform` for animation; reflows are expensive inside the HA shell.

---

## Spatial system

### Radii

```css
--evsc-radius:       22px;   /* default — control cards, metric cards, day cards */
--evsc-radius-lg:    28px;   /* large — hero, weekly, night, settings hero       */
--evsc-radius-pill:  999px;  /* fully round — toggles, priority pill, today badge */
```

Small inline elements (steppers, mini buttons, eyebrows) use 8–14 px directly — they are too small to read a 22 px radius.

### Padding scale

```
Compact mobile (≤480 px):  10–14 px
Default mobile / tablet:    14–18 px
Desktop:                    18–26 px
```

Shell padding uses `clamp(14px, 2.6vw, 36px)` — fluid scaling so margins grow proportionally with the viewport up to a cap.

### Gap scale

```css
gap: clamp(14px, 1.6vw, 22px);  /* between top-level cards in the dashboard shell  */
gap: 12px;                       /* between rows inside a card                      */
gap: 10px;                       /* between metric tiles                            */
gap: 8px;                        /* between siblings in a stepper / time control    */
gap: 6px;                        /* between value + small unit inside one readout   */
gap: 2px;                        /* between ring headline and ring sub              */
```

Don't introduce intermediate values. The 6‑step scale covers every case; if you reach for `gap: 11px`, ask yourself which existing step is closer and use that.

---

## Surface & depth

### Glass surface

```css
backdrop-filter:         saturate(180%) blur(40px);
-webkit-backdrop-filter: saturate(180%) blur(40px);
```

Aliased as `--evsc-blur`. Light variant `--evsc-blur-light` = `saturate(160%) blur(20px)` for smaller / nested surfaces.

### Shadows

```css
--evsc-shadow-soft: 0 1px 2px rgba(0, 0, 0, 0.04),
                    0 8px 24px rgba(0, 0, 0, 0.06);
--evsc-shadow-lift: 0 1px 2px rgba(0, 0, 0, 0.06),
                    0 12px 36px rgba(0, 0, 0, 0.1);
```

Dark mode shadows are deeper (see custom properties). Every card uses `--evsc-shadow-soft` at rest, `--evsc-shadow-lift` on hover.

### The aurora background

The `ha-card` element itself carries three radial gradients plus a linear gradient:

```css
background:
  radial-gradient(1200px 600px at 8% -10%,   color-mix(in srgb, var(--evsc-sys-cyan)   22%, transparent), transparent 60%),
  radial-gradient(1000px 500px at 110% 10%,  color-mix(in srgb, var(--evsc-sys-purple) 22%, transparent), transparent 60%),
  radial-gradient(900px  600px at 50% 110%,  color-mix(in srgb, var(--evsc-sys-mint)   18%, transparent), transparent 70%),
  linear-gradient(160deg, var(--evsc-bg-1) 0%, var(--evsc-bg-2) 100%);
```

On top of that, two `.aurora` div blobs animate with `floatGlow`. These are the *only* large color washes in the system; everything else is a glass surface on top.

### The grain overlay

```css
.grain {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.04;
  mix-blend-mode: overlay;
  /* SVG turbulence noise … */
}
```

Adds physical texture under the glass. Subtle (4 % opacity). Removing it makes the dashboard feel "too digital".

---

## Responsive principles

**Cards stack vertically at every viewport.** This is the single most important architectural decision after v1.11.1. Two‑column layouts at top level (`hero | weekly`) compress *both* cards and force the inner content (h1, metric tiles, day cells) into a narrow channel where every element starts to break. Stacking gives each card the full eye‑line.

The shell caps at **`max-width: 1180px`**. On a 32" monitor the dashboard does not stretch to 3000 px — it sits centered with a comfortable reading width, just like Linear / Vercel / Stripe dashboards.

### Breakpoints

```
≤ 600 px      hero collapses to 1 column (ring on top, body below full width)
≤ 768 px      Weekly Planner desktop grid hidden, mobile day-card stack shown
≤ 480 px      compact metric tiles, smaller fonts, reduced padding
```

The dashboard does **not** have a "tablet" breakpoint per se. Anything above 768 px gets the desktop layout, just at different widths.

### Adaptive grids

For collections of variable‑size elements, prefer `auto-fit` + `minmax(<floor>, 1fr)` over hard‑coded column counts:

```css
.evsc-metric-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
}
```

This degrades from 4 → 2 → 1 columns as the parent shrinks, without media queries.

Exception: the Weekly Planner desktop grid is hard‑coded `70px repeat(7, minmax(0, 1fr))` because it represents the days of the week — wrapping a Wednesday to a new row would be semantically wrong.

### Min‑width guards

Every grid container that's nested inside another grid/flex MUST declare `min-width: 0` on itself or `minmax(0, …)` on the parent's track definition. Without it, content with long unbreakable strings (entity IDs, kW values with decimals) can force the track to expand past the viewport — the v1.10.4 fix that took 4 hours to find. Don't undo it.

---

## Component recipes

### Metric card

```html
<div class="metric-card tone-{amber|rose|teal|cyan}">
  <span class="eyebrow">SOLAR POWER</span>
  <strong data-live="metric.solarPower">3.4 kW</strong>
  <!-- v1.11.0+: NO sublabel for hero metric cards. Pass "" or omit. -->
</div>
```

Tone classes set `--evsc-tone` which drives the corner radial gradient on `.metric-card::before`.

The `data-live` attribute lets the live‑update path (`_updateLiveValues()`) mutate only the value text without re‑rendering the DOM tree — critical for flicker‑free sensor ticks.

### Stepper

```html
<div class="control-card tone-{tone}">
  <div class="control-copy">
    <span class="eyebrow">OUTPUT</span>
    <span class="control-label">Boost Amperage</span>
  </div>
  <div class="stepper-shell">
    <button class="stepper-button" data-number="number.evsc_xxx" data-direction="-1">−</button>
    <span class="stepper-value">32.0<small>A</small></span>
    <button class="stepper-button" data-number="number.evsc_xxx" data-direction="1">+</button>
  </div>
</div>
```

The `data-number` + `data-direction` attributes are picked up by `_bindEvents()` (one delegated listener on shadow root).

### Day card (Weekly Planner mobile)

```html
<article class="evsc-wp-day-card {today}">
  <header class="evsc-wp-day-head">
    <div class="evsc-wp-day-name-block">
      <span class="evsc-wp-day-name">Mercoledì</span>
      <span class="evsc-wp-today-badge">OGGI</span>      <!-- only if today -->
    </div>
    <button class="evsc-wp-tog {on}" data-toggle="…"></button>  <!-- Car ready -->
  </header>
  <div class="evsc-wp-day-body">
    <div class="evsc-wp-day-row">
      <span class="evsc-wp-day-kind evsc-wp-kind-ev">EV</span>
      <div class="evsc-wp-soc-row"><!-- stepper --></div>
    </div>
    <div class="evsc-wp-day-row">
      <span class="evsc-wp-day-kind evsc-wp-kind-home">HOME</span>
      <div class="evsc-wp-soc-row"><!-- stepper --></div>
    </div>
  </div>
</article>
```

The desktop grid (`.evsc-wp-grid`) and mobile stack (`.evsc-wp-mobile`) are rendered as siblings; one is `display: none` at any given viewport. This avoids JS‑driven layout switching and keeps the data bindings parallel.

### Priority pill

```html
<span class="priority-pill state-{ev|home|ev_free}">PRIORITY EV</span>
```

The `::before` is a 7 px dot that inherits `currentColor` (which comes from the `.state-*` modifier) and pulses on `evsc-pulse-slow`.

---

## Anti‑patterns

Things that have been tried and explicitly rejected. Don't reach for these without a strong justification.

| Bad pattern | Why it's bad | What to do instead |
|---|---|---|
| **Two‑column top‑level grid (`hero \| weekly`)** | Compresses both cards on any viewport < 1400 px, breaks h1 typography and metric tile layout. | Stack vertically with `max-width: 1180px` on the shell. |
| **Hard‑coded `grid-template-columns: repeat(N, 1fr)` without `minmax(0, …)`** | Long strings (entity IDs, decimal kW) blow out the column track and cause horizontal scrollbars in nested shadow DOM. | Always `minmax(0, 1fr)` or `auto-fit + minmax(<floor>, 1fr)`. |
| **`align-items: baseline` on flex containers with mixed font sizes** | Baseline of a 1.1 rem mono digit lands ~4 px above the cell center; reads as "stuck to the top". | `align-items: center`. |
| **CSS entrance animations (`fade-in`, slide-up)** | Replays on every sensor tick because the dashboard re-renders via innerHTML. Visible flicker. | Persistent animations only (aurora float, pulse dots). Stagger via natural HTML order, not `animation-delay`. |
| **Adding a fourth aurora accent for "variety"** | Dilutes the rule that aurora = live moments only. Quickly devolves into the cliché "rainbow dashboard". | Use a system color from the existing 11. If absolutely needed, propose adding a new aurora here, with a written justification of what live moment it represents. |
| **Loading a fourth font family** | The 50 KB cost of two families is acceptable; a third doubles it and the visual hierarchy collapses (each family carries less unique weight). | Use weight / italic / tracking variations within the three existing families. |
| **Hover‑only interactions** | Touch devices have no hover. The dashboard is used on iPhone / iPad as much as desktop. | Every hover decoration must have a touchable / focus‑visible equivalent. Currently hover effects are purely decorative (shadow lift) — never load‑bearing. |

---

## Adding tokens / changing the system

The CSS is authored inline inside `_inlineStyles()` for two reasons: (1) the file is served as a single Lovelace resource — no build step, no separate CSS file — and (2) shadow DOM scoping makes external stylesheets fragile. The trade‑off is that tokens live in the same file as the rules that consume them.

When adding a token:

1. Add the custom property under `:host` in `_inlineStyles()`. Update the dark‑mode override under `@media (prefers-color-scheme: dark)` if the value differs.
2. Update the relevant table in this `DESIGN.md` document.
3. Bump the version (`const.py` + `manifest.json` + CLAUDE.md entry). The version is used as the `?v=` cache‑buster on the Lovelace resource URL, so users get the new bundle on next reload.

When changing an existing token:

1. Grep for the variable name in `ev-smart-charger-dashboard.js` first — every consumer should still make sense after the change.
2. Update the table in this doc.
3. Update the CHANGELOG entry in CLAUDE.md describing both the visual change and the rationale.

When breaking the system (you should not, but if you must):

1. Read the [Anti‑patterns](#anti-patterns) section first.
2. Write the justification in the PR description.
3. Update the Direction section of this doc — the system's "voice" is allowed to evolve, but only deliberately.

---

## Sister artifacts

This design system is portable to other surfaces inside the integration if/when they're built. Specifically:

- **Settings tab UI** ([_renderSettingsView()](ev-smart-charger-dashboard.js)) — already uses the same tokens but with an accordion pattern not covered here. If extended, document the accordion recipe in this file.
- **Future companion cards** (e.g. a hybrid‑mode diagnostic card, a separate solar‑surplus monitor) should import the same `@import` line and reference the same custom properties to stay visually consistent.
- **Notifications** (mobile push via the integration's notify service) currently render in HA's own template — out of scope here, but the copy tone ("Non in carica" / "Boost session started" / "Aurora green") should match.

If you're starting a new card and want a faster on‑ramp than reading this whole doc: copy the `:host { … }` block and the `@import` line from `_inlineStyles()`, then reference the token names. The visual identity will carry across automatically.
