# Design System: AgentMint x TeamoRouter Reference

Source reference: https://teamorouter.com/zh

This document adapts the observed TeamoRouter visual language into a reusable design system for AgentMint. It should guide future page redesigns, component styling, copy density, data panels, and responsive behavior.

## 1. Visual Theme & Atmosphere

AgentMint should feel like a modern AI operations workbench rather than a traditional forum or SaaS admin. The reference design is bright, precise, and data-forward: a warm off-white canvas, crisp black typography, red-orange action accents, dense tables, soft white cards, subtle glass navigation, and technical product copy. The page combines marketing confidence with dashboard utility, which fits AgentMint's agent marketplace, question routing, fuel settlement, and owner control panels.

The mood is clean but not sterile. Use large confident headlines and strong data surfaces, then let fine borders, muted gray text, and compact controls carry the operational parts. Avoid decorative gradients as the main identity. The signature detail is "structured intelligence": visible grids, tables, route/status panels, and metric cards that make AI activity feel measurable.

### Key Characteristics

- Warm light canvas with white elevated surfaces and precise neutral borders.
- Black headline typography with restrained negative tracking only for hero-scale titles.
- Red-orange brand accent for primary action, selected tabs, important deltas, and value highlights.
- Data-first sections: tables, rankings, route panels, comparison rows, and token/fuel numbers should look native, not bolted on.
- Soft elevation: cards use thin borders plus low-opacity long shadows, not heavy floating shadows.
- Glass navigation: fixed top bar with translucent canvas and a subtle bottom border.
- Compact, high-trust controls: small pills, segmented tabs, dense inputs, and button groups.
- Background motif may use a faint 40px technical grid near hero areas, fading out quickly.

## 2. Color Palette & Roles

| Role | Semantic Name | Value | Usage |
| --- | --- | --- | --- |
| Canvas | Warm Canvas | `#F7F7F7` | Page background, app shell, neutral sections. |
| Hero Fade | Top Light Wash | `#FCFCFC` to `rgba(246,246,246,0)` | Subtle hero background fade, not full-page gradient branding. |
| Elevated Surface | Paper White | `#FFFFFF` | Cards, tables, popovers, form panels, billing surfaces. |
| Muted Surface | Panel Gray | `#EFEFEF` | Footer, secondary bands, inactive panel areas. |
| Subtle Surface | Control Gray | `#F0F0F0` | Hover fills and compact control backgrounds. |
| Primary Text | Ink Black | `#121212` | Headings, primary labels, key numbers. |
| Secondary Text | Utility Gray | `#525252` | Body copy, nav links, table metadata. |
| Tertiary Text | Quiet Gray | `#737373` | Captions, timestamps, disabled-ish supporting text. |
| Disabled Text | Disabled Gray | `#9E9E9E` | Disabled controls, unavailable states. |
| Border Subtle | Hairline Gray | `#DCDCDC` | Card borders, table row dividers, inputs. |
| Border Default | Control Border | `#C4C4C4` | Secondary buttons, stronger inputs, card emphasis. |
| Border Strong | Ink Border | `#525252` | Rare strong separators or critical outlines. |
| Brand Primary | Router Red | `#D0240F` | Primary CTA, active tabs, selected filters, important highlights. |
| Brand Hover | Router Red Hover | `#BB2009` | Primary button hover. |
| Brand Active | Router Red Active | `#A01B08` | Pressed primary button, active destructive/critical affordances. |
| Brand Muted | Rust Link | `#AE453F` | Text links, focus ring, subtle brand text. |
| Brand Soft | Red Tint | `rgba(208,36,15,0.08)` | Brand hover surfaces and soft selected backgrounds. |
| Brand Selected | Warm Selected | `#FFE8DD` | Active filter chip, selected category background. |
| Data Highlight | Price Cell Wash | `#FFF7F2` / `rgba(255,247,242,0.6)` | Highlighted answer value columns, settlement deltas, owner earnings columns. |
| Success | Green | `#16A34A` | Positive status, available capacity, approved answer signals. |
| Warning | Amber | `#D97706` | Pending pairing, limit warnings, needs-owner-review states. |
| Danger | Red | `#DC2626` | Failed delivery, unavailable service, destructive operations. |

### Primary

- Use `#D0240F` sparingly but decisively. It should identify the next best action or selected state.
- Use `#AE453F` for lower-intensity links and focus rings so primary red does not dominate every interactive element.

### Interactive

- Primary button default: `#D0240F`, text `#F7F7F7`, border same as fill.
- Primary hover: `#BB2009`, optional subtle upward movement of `translateY(-1px)` only on marketing-scale buttons.
- Active or pressed: `#A01B08`.
- Secondary controls: white or canvas background, `#C4C4C4` border, `#121212` text.
- Selected pills can use either filled red with white text or warm selected `#FFE8DD` with red border, depending on emphasis.
- Focus rings use `#AE453F`, 2px ring, 2px offset against canvas.

### Neutral Scale

- `#121212`: main content and high-confidence data.
- `#3D3D3D`: chart secondary stroke or dense table text.
- `#525252`: normal body copy and utility labels.
- `#737373`: captions and quiet metadata.
- `#9E9E9E`: disabled or de-emphasized data.
- `#C4C4C4`: stronger borders.
- `#DCDCDC`: subtle borders and table rules.
- `#EFEFEF` / `#F0F0F0`: secondary surfaces.
- `#F7F7F7`: page canvas.
- `#FFFFFF`: elevated panels.

### Surface & Overlay

- Page canvas: `#F7F7F7`.
- Elevated cards: `#FFFFFF`, often with `border: 1px solid #DCDCDC`.
- Popovers: `#FFFFFF`, `8px` radius, `12px` padding, `0 10px 32px rgba(18,18,18,0.08)`.
- Sticky header: `rgba(247,247,247,0.76)` with backdrop blur and a bottom border.
- Overlay: `rgba(18,18,18,0.72)` for modal backdrops.

### Theme Modes

The inspected page primarily renders in light mode. CSS class names suggest dark-mode support, but the live `/zh` page presented the light system. For AgentMint V1 redesign, prioritize this light mode and treat dark mode as a later derivative.

#### Light Mode

- Background: warm gray canvas `#F7F7F7`.
- Surface: white `#FFFFFF`.
- Text: ink `#121212`.
- Accent: router red `#D0240F`.
- Notes: product feels premium because surfaces are restrained and typography is confident, not because of visual decoration.

#### Dark Mode

- Background: not directly observed as the active page mode.
- Surface: inferred class hints include dark neutral panels around `#1A1A1A`.
- Text: inferred inverse `#F7F7F7`.
- Accent: red/orange accents should remain stable.
- Notes: do not implement dark mode by simply inverting everything; preserve the red accent and fine border discipline.

### Shadows & Depth

- Card shadow: `0 10px 32px rgba(18,18,18,0.08)`.
- Header shadow: `0 10px 34px -28px rgba(18,18,18,0.46)`.
- Tiny active chips: `0 1px 2px rgba(0,0,0,0.05)`.
- Most depth comes from border plus subtle shadow. Do not use large blurred blobs or heavy shadow stacks.

## 3. Typography Rules

### Font Family

- Primary: `"IBM Plex Sans", "Noto Sans SC", system-ui, sans-serif`.
- Monospace: use system mono only for code, IDs, request IDs, token traces, and compact technical logs.
- OpenType Features: keep default features; avoid decorative tracking except hero-scale negative tracking.

### Hierarchy

| Role | Font | Size | Weight | Line Height | Letter Spacing | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Desktop hero headline | IBM Plex Sans / Noto Sans SC | `60px` | `700` | `63px` | `-1.2px` | Use for first-screen product promise only. |
| Mobile hero headline | IBM Plex Sans / Noto Sans SC | `32px` | `700` | `33.6px` | `-0.64px` | Two-line layout is expected. |
| Large numeric/value headline | IBM Plex Sans / Noto Sans SC | `78.4px` desktop, `34.4px` mobile | `700` | `0.95em` | `-0.02em` | Use for token/fuel/value statements, not ordinary cards. |
| Section heading | IBM Plex Sans / Noto Sans SC | `30px` | `600-700` | `36px` | `0` or `-0.75px` | Top of major sections and dashboards. |
| Card heading | IBM Plex Sans / Noto Sans SC | `18-24px` | `600` | `28-32px` | `0` | Keep compact inside cards. |
| Table header | IBM Plex Sans / Noto Sans SC | `14px` | `700` | `20px` | `0` | Muted gray or red for highlighted columns. |
| Body | IBM Plex Sans / Noto Sans SC | `16px` | `400` | `24px` | `0` | Primary explanatory copy. |
| Compact control | IBM Plex Sans / Noto Sans SC | `14px` | `500-600` | `20px` | `0` | Buttons, filters, nav links. |
| Caption / Meta | IBM Plex Sans / Noto Sans SC | `12-14px` | `400-500` | `15-20px` | `0` | Time, status details, help text. |

### Principles

- Use big type only where the content is a true product promise or major metric.
- Keep dashboard/cards tighter: `18-24px` headings and `14px` controls.
- Avoid negative letter spacing outside hero or oversized numeric display.
- Chinese copy should be direct, compact, and product-like. Prefer short declarative sentences.
- Numbers, rankings, and token/fuel amounts should be easy to scan; use tabular alignment where possible.

## 4. Component Stylings

### Buttons and Links

- Primary CTA: `#D0240F` fill, `#F7F7F7` text, `6px` radius for standard buttons, `8px` for larger download/action buttons. Height `40px` standard, `48px` hero.
- Secondary CTA: white fill, `1px #C4C4C4` border, ink text, same height/radius as primary.
- Brand pill: transparent or soft red surface, `1px rgba(208,36,15,0.22)` border, `9999px` radius, `#D0240F` text.
- Filter chip: `34px` height, `6px 12px` padding, pill radius. Selected can be red fill or `#FFE8DD` with red border.
- Text links: `#AE453F`; hover to `#D0240F`.
- Nav links: `14px`, `8px 10px`, `8px` radius. Active is ink; inactive is `#525252`; hover background `#F0F0F0`.
- Motion: `background-color`, `color`, `border-color`, `opacity` around `150-160ms`; optional transform around `120ms`.

### Cards and Containers

- Surface style: white card on warm canvas.
- Radius: `16px` for main cards; `12px` for nested inset panels; `8px` for popovers and compact panels; `6px` for small controls.
- Border: `1px solid #DCDCDC`; use `#C4C4C4` when a card needs stronger enclosure.
- Shadow or elevation: `0 10px 32px rgba(18,18,18,0.08)`.
- Internal spacing: `24px` on desktop cards, `16px` on mobile or tight panels.
- Avoid cards inside cards unless the inner element is a real inset data panel.

### Inputs and Interactive Controls

- Inputs use canvas or white fill, `1px #C4C4C4` border, `6-8px` radius, `8px 12px` padding, `14px` text.
- Search fields should sit inline with filter chips when space allows; on mobile, search spans full width and chips wrap below.
- Focus behavior: 2px rust-red focus ring with 2px offset; never use glowing blue browser-default focus.
- Disabled controls use `#9E9E9E` text, muted surface, and preserve layout dimensions.

### Navigation

- Structure: fixed top nav, `76px` desktop height, `60px` mobile height.
- Background treatment: translucent warm canvas around 76% opacity, backdrop blur, bottom hairline border.
- Desktop: logo left, compact nav items center/right, language selector and login/action controls on far right.
- Mobile: logo left, black compact language button, 38px square menu icon button. Hide full nav.
- Header shadow should be barely visible, used to separate content while scrolling.

### Tables and Data Panels

- Tables are first-class surfaces. Use `14px` text, dense rows, and horizontal scroll on mobile.
- Table wrapper should be a white card with `16px` radius and subtle border/shadow.
- Header cells: `12px 16px` padding, muted gray text, `700` weight.
- Body cells: `12px 16px`, primary data in ink, secondary metadata in gray.
- Highlight important columns with warm red wash `#FFF7F2` or `rgba(255,247,242,0.6)`, and red/rust header text.
- Row dividers: `1px solid rgba(220,220,220,0.7)`.
- Rankings and route/status tables may use tighter horizontal padding when many columns are present.

### Image Treatment

- Product imagery is minimal. The reference relies more on tables, charts, and UI surfaces than large screenshots.
- When screenshots are used, frame them as real product surfaces: white card, subtle border, `16px` radius.
- Icons are simple line icons or small inline glyphs. Use lucide-style icons where possible.

### Distinctive Components

- Technical hero grid: a faint full-width grid of 40px cells behind the hero, each cell using `0.5-1px` gray border and very low opacity. Fade it vertically so it never competes with content.
- Segmented tabs: outer pale container or simple tab group; selected tab filled red with white text, unselected muted text.
- Client tabs: text-only horizontal tabs with red active text and muted inactive text; keep them compact.
- Comparison matrix: two-column product comparison with red-tinted selected side and plain competitor side.
- Metric chart cards: white card, compact title, muted explanatory copy, SVG/chart in neutral gray with red emphasis.
- Tooltip/popover: white, `8px` radius, subtle border, soft shadow, `12px` padding, `12px` text.

## 5. Layout Principles

### Spacing System

- Base unit: `4px`.
- Repeated spacing values: `6px`, `8px`, `10px`, `12px`, `16px`, `20px`, `24px`, `32px`, `40px`, `48px`, `64px`, `76px`, `120px`.
- Desktop container: `1200px` max content width, centered, with `120px` side padding at 1440px viewport.
- Mobile container: `16px` side padding, content width around `358px` on a 390px viewport.
- Section gap: `64px` between major sections; hero and large value sections may use `48-76px` internal padding.

### Grid & Container

- Hero starts under fixed nav, using negative top offset to align with nav height.
- Main container should feel like one continuous workbench, not isolated page cards.
- Use grid for feature cards: 3 columns desktop, 1 column mobile.
- Use horizontal overflow for dense tables rather than shrinking text until illegible.
- Full-width bands may break out of the container for value/pricing sections; keep inner content constrained.

### Whitespace Philosophy

- Whitespace is generous around major sections but compact inside operational panels.
- Align content to the left for most AgentMint workflows. Centered hero copy is acceptable only for landing/introduction pages.
- Avoid marketing split hero layouts with decorative cards unless the card contains real product or data.

### Border Radius Scale

- Micro: `6px` for standard buttons, selects, compact inputs.
- Standard: `8px` for nav pills, popovers, medium buttons.
- Large: `12px` for nested panels and inset callouts.
- Card: `16px` for main data cards and dashboard panels.
- Pill: `9999px` for filter chips, badges, and invitation/referral pills.

## 6. Depth & Elevation

| Level | Treatment | Use |
| --- | --- | --- |
| Flat | Canvas background, no border | Page base and open layout areas. |
| Hairline | `1px #DCDCDC`, no shadow | Rows, small controls, subtle separators. |
| Control | White/canvas fill, `1px #C4C4C4` border | Buttons, inputs, selects. |
| Card | White fill, `1px #DCDCDC`, `0 10px 32px rgba(18,18,18,0.08)` | Panels, tables, answer cards, billing summaries. |
| Popover | White fill, `8px` radius, same soft shadow | Tooltips, menus, owner notes, pairing help. |
| Header | Translucent canvas, bottom border, `0 10px 34px -28px rgba(18,18,18,0.46)` | Fixed global nav. |
| Focus | `2px #AE453F` ring, 2px offset | Keyboard focus and form active states. |

### Depth Principles

- Use elevation to clarify hierarchy, not as decoration.
- Prefer border plus soft shadow over blurred glass cards.
- Keep nested surfaces rare and purposeful.
- Charts and tables can live inside the same card, but do not wrap every small metric in a separate floating tile.

## 7. Do's and Don'ts

### Do

- Use the warm canvas + white card + red accent system consistently.
- Make token/fuel/agent routing data visually prominent and easy to scan.
- Use dense tables for operational data, with horizontal scroll on mobile.
- Keep navigation compact and fixed.
- Use selected states that are immediately visible: red fill, warm red wash, or red text.
- Let owner/agent/service states read like a serious control panel.
- Preserve stable dimensions for buttons, filters, cards, and table rows.
- Write copy in short, direct claims and measurable benefits.

### Don't

- Do not make the UI dominated by purple/blue gradients, dark slate dashboards, or decorative orb backgrounds.
- Do not use oversized marketing cards for ordinary app workflows.
- Do not make every panel a card inside another card.
- Do not over-round everything; keep cards at `16px` and controls at `6-8px`.
- Do not hide important economics behind vague labels; fuel, token estimate, preauth, settlement, and owner income should be explicit.
- Do not use tiny mobile tables by shrinking columns; preserve min-width and allow horizontal scroll.
- Do not rely on color alone for failure or pairing states; pair red/amber color with clear status text.

## 8. Responsive Behavior

### Breakpoints

| Name | Width | Key Changes |
| --- | --- | --- |
| Mobile | `390px` observed | Header becomes logo + black language button + 38px menu. Container uses 16px side padding. Hero title becomes `32px`. Tables keep `900-1024px` min-width and scroll horizontally. |
| Tablet | Around `768px` inferred | Feature grids move from 3 columns to 1-2 columns. Cards use `16-20px` padding. Header may still hide dense nav. |
| Desktop | `1440px` observed | Fixed 76px header, 1200px content container, hero title `60px`, cards use `24px` padding, tables fill full container. |

### Touch Targets

- Mobile icon buttons: `38px` square minimum.
- Mobile primary buttons: `40-48px` height.
- Pills and filter chips: `34px` height minimum.
- Keep tap targets separated by at least `8px` where controls wrap.

### Collapsing Strategy

- Desktop behavior: full nav, inline filters, wide cards, dense tables.
- Tablet behavior: reduce grids, keep top nav compact, preserve table scroll.
- Mobile behavior: hide full nav, stack content, keep action groups wrapping, maintain table min-width.
- Breakpoint-driven component changes: hero typography compresses sharply; large value text drops from `78.4px` to `34.4px`.
- Touch target and spacing adjustments: side padding becomes `16px`; major section gap remains around `64px` to keep rhythm.

## 9. Interaction Patterns

- Scroll: sticky header remains visible with translucent background and subtle shadow.
- Hover: nav/control hover changes background to `#F0F0F0`; primary hover deepens red.
- Click: selected tabs and chips switch to red or warm selected state.
- Menus: mobile nav opens from menu button; language selector becomes a compact black button on mobile.
- Tooltips: appear as small white cards with border and soft shadow; useful for explaining token economics or service-limit rules.
- Motion: subtle, fast, practical. Use `150-160ms` for color and `120ms` for transform. Avoid slow cinematic effects in app workflows.

## 10. Content & Messaging Patterns

- Headline style: direct product promise with specific technical nouns.
- CTA phrasing: short action verbs such as "获取", "查看", "购买", "发布", "追问", "请求补充".
- Sentence density: compact paragraphs, usually one or two sentences.
- Product framing: emphasize measurable capability, cost, reliability, routing quality, and saved operational effort.
- Trust signals: SLA-like status, token counts, answer delivery state, owner capacity, daily limits, pairing status, settlement history.
- AgentMint copy should say what the platform does, not describe the UI itself.

## 11. Observed Pages

- `https://teamorouter.com/zh`
- Desktop viewport observed at `1440 x 1200`.
- Mobile viewport observed at `390 x 900`.
- Primary evidence came from rendered DOM structure, computed styles, CSS variables, accessibility snapshot, and responsive viewport inspection through `agent-browser`.

## 12. Agent Prompt Guide

### Quick Color Reference

- Primary CTA: `#D0240F`
- Primary hover: `#BB2009`
- Background: `#F7F7F7`
- Surface: `#FFFFFF`
- Heading text: `#121212`
- Body text: `#525252`
- Border or ring: `#DCDCDC` / `#C4C4C4`
- Focus: `#AE453F`
- Highlight cell: `#FFF7F2`
- Selected chip: `#FFE8DD`

### Example Component Prompts

- Hero: "Build a bright AI workbench hero on a warm `#F7F7F7` canvas, fixed translucent header, faint 40px technical grid behind the first screen, 60px black headline, compact body copy, red primary CTA, white secondary CTA."
- Data card: "Create a white `16px` radius card with `1px #DCDCDC` border, `0 10px 32px rgba(18,18,18,0.08)` shadow, 24px padding, compact heading, and dense table rows."
- Question routing panel: "Use a table-like card where selected or best-value columns have a warm red wash `#FFF7F2`; show agent, estimated token cost, preauth, status, and owner capacity as scannable rows."
- Button set: "Use `#D0240F` primary buttons with 6px radius and 40px height, white secondary buttons with `#C4C4C4` border, and pill filters using 34px height and selected red or `#FFE8DD` state."
- Mobile layout: "Collapse nav to logo, compact language pill, and 38px menu button; keep tables horizontally scrollable with 900px+ min-width instead of shrinking data."

### Iteration Guide

- When a page feels too traditional, add data structure first: route status, fuel numbers, answer states, owner limits, ranking, or settlement columns.
- When a page feels too decorative, remove gradients/cards and return to canvas, white surfaces, borders, and red selected states.
- When a page feels too sparse, increase information density inside cards rather than adding more page sections.
- When a page feels too heavy, reduce shadows and rely on hairline borders.

### Quick Summary

Use a bright, warm, data-forward AI workbench style. The visual core is `#F7F7F7` canvas, white soft-shadow cards, black IBM Plex/Noto typography, red-orange primary actions, muted gray operational text, and dense table-like panels. Treat AgentMint as a measurable agent routing and settlement product: every answer, token, owner action, service limit, and fuel movement should feel visible and trustworthy.
