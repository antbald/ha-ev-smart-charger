# Liquid Aurora — Design System

The single design language of the EV Smart Charger dashboard, introduced in v1.11.0 and refined in v1.11.1. **v1.11.2 reverted the custom typography stack (Instrument Serif italic + JetBrains Mono) back to the native system fonts after user feedback** — what remains in v1.11.2+ is the *spatial / color / motion / layout* part of Liquid Aurora, on top of the SF Pro / system sans stack.

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

## Direction (v1.11.2+)

**Native iOS Liquid Glass, dialled up.** System SF Pro sans across the board, but pushed beyond a default admin look through *spatial* and *color* commitments:

- **Generous SOC ring** as the focal point of the hero — large percentage in bold sans, concentric dual arcs (EV outer + Home inner) with saturated aurora accents.
- **Atmospheric background** — three radial gradients + two animated aurora blobs + a subtle grain overlay. The ha-card surface is never a flat solid color.
- **Glass surfaces** — `backdrop-filter: saturate(180%) blur(40px)` on every card, with a lifted hover state on touch‑capable surfaces.
- **Editorial restraint on motion** — slow aurora float (28–36 s), 3.2 s priority pill pulse, no entrance animations. The dashboard breathes, it doesn't perform.
- **Day‑grouped Weekly Planner mobile cards** — full localized weekday names (Mercoledì / Wednesday / Woensdag), TODAY badge, blue accent for today. The information architecture is the differentiator, not the typography.

This is *not* a "minimalist" system — it commits to atmospheric depth and saturated live moments. It is also *not* a "maximalist" or "editorial" system after v1.11.2 — the previous attempt at serif italic display moments was reverted because the user preferred the native look.

**Single moment of strong identity**: the SOC ring. Big percentage, dual aurora arcs, charging pulse dot. If you remove or shrink it, the system loses its anchor. Don't.

---

## Typography

**v1.11.2 update**: the custom typography stack introduced in v1.11.0 (Instrument Serif italic + JetBrains Mono, loaded from Bunny Fonts) has been reverted. The dashboard now uses the **native system sans stack** for everything. The reversion was driven by direct user feedback: the serif italic display moments did not land as intended and the user preferred the v1.10.5 native look.

Single font role, native stack, no external dependencies, no FOUT, no GDPR footprint:

| Role | Family | Used for |
|---|---|---|
| **Sans (everything)** | SF Pro Display / SF Pro Text → BlinkMacSystemFont → Inter → Segoe UI → system‑ui → sans‑serif | All display moments, all numeric readouts, all body copy, all labels |

No `@import`. No external fonts. The dashboard renders fully native on every supported HA client (web, iOS app, Android app), with zero font‑related latency.

### Custom properties

```css
--evsc-font: -apple-system, "SF Pro Display", "SF Pro Text", BlinkMacSystemFont, "Inter", "Segoe UI", system-ui, sans-serif;
```

The `--evsc-font-display` and `--evsc-font-mono` tokens introduced in v1.11.0 have been **removed**. If you re‑introduce a custom face in a future release, add it as a new token here (and update the table below + the [Anti‑patterns](#anti-patterns) section if it changes the rules).

### Type scale (current — v1.11.2+)

| Use | Size | Weight | Style |
|---|---|---|---|
| Hero `<h1>` | `clamp(20px, 1.8vw, 26px)` | 700 | normal |
| SOC ring percentage | 2.2rem | 700 | normal |
| Night Charge time (vv) | 22px | 800 | normal |
| Day card name (mobile) | 18px | 700 | normal |
| Today badge (mobile) | 10px | 700 | uppercase + 0.10em tracking |
| Day kind label (mobile) | 11px | 700 | uppercase + 0.08em tracking |
| Metric card value | `clamp(1.2rem, 2vw, 1.7rem)` | 700 | normal |
| Stepper / time value | 1.1rem | 700 | normal |
| Priority pill label | 0.85rem | 600 | normal |
| Eyebrow / kicker | 0.7rem | 600 | uppercase + 0.14em tracking |
| Ring legend | 0.78rem | 400 | tabular‑nums |
| Ring sub label | 0.78rem | 600 | uppercase + 0.04em tracking |
| Body description | 13px | 400 | line‑height 1.55, max‑width 42ch |

**Tabular numerics**: every numeric readout still uses `font-variant-numeric: tabular-nums` (set globally on `ha-card` via `font-feature-settings: "tnum" on`) so `+ / −` taps nudge the same character slot every time (no horizontal jitter as digits change width).

### Why the reversion is documented (not just removed)

Two reasons:

1. The custom typography stack might be re‑attempted in a future minor (with a different display face, or as an opt‑in). Future maintainers should know it was tried and what the failure mode was (taste, not technical), so the bar for re‑introducing it is "the user specifically asks for an editorial face", not "let's try a serif again".
2. The component recipes in this doc reference the previous structure (e.g. the SOC ring percentage was sized 3rem to look right in serif italic; in sans bold it's 2.2rem). The diff between v1.11.1 and v1.11.2 typography is non‑trivial — anyone reading old PR descriptions or screenshots needs context.

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
| **Re‑introducing custom web fonts casually** | v1.11.0 added Instrument Serif italic + JetBrains Mono via Bunny Fonts. User feedback in v1.11.2 was negative ("non mi piace questo font, preferivo il precedente") and they were removed. Network dependency, FOUT, GDPR considerations, and taste-divergence make custom fonts a real cost. | Stick with the SF Pro / system stack unless the user *specifically* asks for an editorial face. If you do reintroduce one, ship it behind an opt‑in config option, not as the default. |
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
