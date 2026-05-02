# Morningstar CN Design System Reference for Finer OS

**Status**: reference standard
**Created**: 2026-05-02
**Sources**:
- https://www.morningstar.cn/#/
- https://www.morningstar.cn/fund/159895.html

This document extracts the observable Morningstar China visual language and translates it into an implementation standard for Finer OS. It is a design reference, not a license to copy Morningstar trademarks, logos, proprietary icons, illustrations, or exact page composition.

## 1. Design Positioning

Finer OS should adopt the Morningstar China style as an institutional data workstation:

- editorial but not decorative
- dense but not cluttered
- black/white/gray foundation with red as a precise signal
- page sections separated by rules, whitespace, and tab bars rather than soft cards
- data tables and metric grids as primary surfaces
- low ornamentation, high confidence, audit-oriented hierarchy

The target feeling is closer to a fund research terminal than a SaaS marketing dashboard.

## 2. Visual Evidence Summary

### Morningstar CN Home

Observed patterns:

- top black utility bar with white navigation
- large red Morningstar wordmark on white header
- second-level nav with gray text and generous horizontal spacing
- large search pill on the right
- hero uses split editorial layout: left text, right real image
- article cards are divided by vertical hairlines, not floating cards
- strong CTA is black rectangle with white text and arrow
- lower promo block uses deep Morningstar red

### Morningstar CN Fund Detail

Observed patterns:

- white page, no decorative background
- page content constrained around a 1024px inner width
- large fund name headline at 32px, code at 28px lighter weight
- metrics arranged in four-column key-value grid
- labels are bold black; values are gray, red, or black
- active tabs use a thick black underline
- data tables use thin horizontal rules, minimal cell chrome
- buttons are outline pills with gray border and light font weight
- charts/tables dominate below the fold

## 3. Color Tokens

Use these as canonical Finer OS design variables.

```css
:root {
  --ms-bg: #ffffff;
  --ms-bg-subtle: #f7f5f2;
  --ms-ink: #000000;
  --ms-ink-strong: #1e1e1e;
  --ms-ink-muted: #5e5e5e;
  --ms-ink-soft: #808080;
  --ms-border: #cccccc;
  --ms-border-light: #e5e5e5;
  --ms-red: #ff0000;
  --ms-red-deep: #8f0026;
  --ms-blue-action: #0077cf;
  --ms-green: #00b13a;
  --ms-gold: #f5c400;
}
```

Usage rules:

- `--ms-ink` is for titles, table labels, active tabs, and primary text.
- `--ms-ink-muted` is for nav items, values, placeholders, secondary metadata.
- `--ms-red` is for brand emphasis and China-market positive performance values.
- `--ms-green` is for negative/decline or alternate market status where China finance convention applies.
- `--ms-blue-action` is rare; use for confirm dialogs or links only when red would imply market movement.
- Do not use red as a background except for major brand/promo bands. In app surfaces, red should usually be text, underline, border, or small badge.

## 4. Typography

Observed primary stack:

```css
font-family: intrinsic, helvetica, arial, sans-serif;
```

Finer OS implementation stack:

```css
font-family: var(--font-ui-sans), "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", Helvetica, Arial, sans-serif;
```

Type scale:

| Role | Size | Weight | Line height | Usage |
|---|---:|---:|---:|---|
| Page title | 32px | 500 | 32-40px | fund name, workspace title |
| Entity code / secondary title | 28px | 300 | 28-36px | ticker, source id, date range |
| Section title | 24px | 600 | 32px | major data section title |
| Nav / tabs / table base | 16px | 400 | 24-36px | nav, tabs, data cells |
| Table header | 14px | 700 | 20px | dense table labels |
| Metadata | 14px | 400 | 20px | dates, source labels, counters |
| Micro label | 11-12px | 600 | 16px | status tags, stage labels |

Rules:

- Avoid oversized dashboard hero typography.
- Use font weight, underline, and spacing before using color.
- Chinese labels should stay compact; do not add wide letter spacing.
- Numeric columns should use tabular numbers when possible.

## 5. Layout System

Page shell:

- max content width: 1024px for focused analysis views
- app workbench width may expand to 1280-1440px, but data modules must keep stable columns
- background: white or very subtle off-white
- section separation: horizontal rules, tab underlines, whitespace
- avoid nested card stacks

Spacing:

| Token | Value | Usage |
|---|---:|---|
| `--space-1` | 4px | icon/text gap, compact table padding |
| `--space-2` | 8px | button inner gap, dense controls |
| `--space-3` | 12px | table cell padding, small module padding |
| `--space-4` | 16px | header/footer module padding |
| `--space-6` | 24px | section gap |
| `--space-8` | 32px | page section vertical rhythm |
| `--space-12` | 48px | major homepage/editorial gap |

## 6. Component Standards

### Top Utility Bar

- height: 34-36px
- background: `#1f1a18` or `#000`
- text: white, 16px
- used for product switcher, legacy links, account scope, environment indicator

Finer OS adaptation:

- left: `Finer OS / F0-F8`
- center: optional command/search scope
- right: sync status, model status, settings/account

### Header Navigation

- white background
- logo/brand left
- icon utilities right
- bottom border: `1px solid --ms-border-light`
- search pill: 30-36px height, border `#808080`, radius 999px

### Tabs

Morningstar fund page tabs:

- inactive text: `--ms-ink-muted`
- active text: `--ms-ink` or `--ms-ink-muted`
- active marker: 4px black underline
- tab height: 36-40px
- no pill background for primary page tabs

Finer OS:

- use underline tabs for major views
- use segmented controls only for local modes such as `回报 / 回撤`

### Buttons

Primary editorial CTA:

- black background
- white text
- rectangular or 2px radius
- arrow icon on right

Utility button:

- white or transparent background
- gray border
- pill radius 24px
- 14-16px text
- icon + text if action is not obvious

Do not use large colored rounded buttons for routine table operations.

### Metric Grid

Use four-column key-value grids for instrument/source metadata.

```text
label: 16px / 600 / black
value: 16px / 400 / muted gray
cell height: 48-58px
column width: stable, no auto-jitter
```

Performance values:

- positive in China-market convention: red
- negative in China-market convention: green
- unknown/missing: em dash in muted gray

### Tables

Morningstar table language is rule-based, not card-based:

- no table container shadow
- no zebra stripes by default
- horizontal rules: `1px solid #e5e5e5`
- table header text: 14px bold muted/black
- body text: 14-16px
- numeric data: right-aligned or column-aligned
- active values may use red/green, but keep row labels black

For Finer OS:

- audit tables should use dense rows and clear source/date columns
- evidence and provenance tables should prioritize line-level scanability
- row hover may use `#f7f5f2`, not blue or purple

### Article / Content Cards

Use cards sparingly. Morningstar home article units are mostly vertical columns separated by hairlines.

Recommended Finer article list:

- unframed row list or column grid
- border-left/right dividers
- category label above title
- title bold black
- date and source in muted gray
- view count or quality signal aligned right

Avoid rounded marketing cards with heavy shadows.

### Charts

Charts should be integrated as data modules:

- black section title
- thin top divider
- toolbar icons on the right
- chart area white
- legend colors restrained
- red/green follow China market convention

Do not put charts inside decorative gradient panels.

## 7. Finer OS Application Pattern

For operational Finer OS pages, use this composition:

```text
Top utility bar
Header with product mark, global search, icon utilities
Page title row
Metric summary grid
Underline tabs
Primary work surface: table / chart / evidence panel
Secondary side panel only when it adds workflow value
```

Recommended module hierarchy:

1. Global status: sync state, selected F-stage, model provider, current source.
2. Entity/source header: name, id, timestamp, quality signal.
3. Metric grid: counts, quality, extraction status, latest activity.
4. Tabs: blocks, topics, anchors, intents, execution, review.
5. Data surface: table, chart, transcript, or evidence viewer.

## 8. Finer OS CSS Token Proposal

Map the reference into project-level variables:

```css
:root {
  --finer-bg: #ffffff;
  --finer-bg-muted: #f7f5f2;
  --finer-ink: #000000;
  --finer-ink-strong: #1e1e1e;
  --finer-ink-muted: #5e5e5e;
  --finer-border: #d8d8d8;
  --finer-border-light: #e8e8e8;
  --finer-red: #e11b22;
  --finer-red-pure: #ff0000;
  --finer-red-deep: #8f0026;
  --finer-action-blue: #0077cf;
  --finer-positive-cn: #ff0000;
  --finer-negative-cn: #00b13a;
}
```

Tailwind usage guidance:

- Prefer `bg-white`, `text-black`, `text-stone-600`, `border-stone-200`.
- Use `text-morningstar-red` for brand/action emphasis.
- Replace cream-heavy dashboard backgrounds with white or `#f7f5f2` only for muted bands.
- Use `rounded-sm` or `rounded-none` for app surfaces; reserve pills for search, back buttons, and segmented controls.

## 9. Implementation Rules for Agents

When building Finer OS frontend screens:

- Do build the actual tool/workbench as the first screen.
- Do use dense tables, metric grids, underline tabs, and restrained dividers.
- Do keep icons thin-line and functional.
- Do make source/provenance and data freshness visible.
- Do not create marketing hero sections for internal tools.
- Do not use gradient blobs, decorative orbs, or purple-blue AI palettes.
- Do not use nested cards.
- Do not let text overflow buttons, tabs, table cells, or cards.
- Do not use Morningstar logo assets or proprietary brand marks.

## 10. Acceptance Checklist

Before shipping a Finer OS frontend page against this standard:

- The first viewport communicates the working object, not a slogan.
- Tables and metric grids are usable without scrolling horizontally at 1280px.
- Active tab state uses a black underline or restrained red accent.
- Red appears as signal, not background decoration.
- Buttons use icons where the action is standard.
- Search input is pill-shaped and visually quiet.
- No nested cards.
- No hero-scale type inside compact panels.
- Page still reads as black/white/gray if red accents are removed.
