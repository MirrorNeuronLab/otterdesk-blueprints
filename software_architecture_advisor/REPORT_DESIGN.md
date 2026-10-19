# Geist report template

Architecture Advisor is the reference implementation for future blueprint
reports. Blueprint-specific content, evidence policy and publication remain in
the owning blueprint. Other blueprints and the runtime are not migrated here.

## Start with the reader's decision

1. Show one useful recommendation or conclusion, its material coverage limit,
   and one primary action. Do not repeat it as metrics, a finding and a prompt.
2. Keep four common task views visible. Put additional views under More views
   and graph settings under Options. Each tab has one purpose.
3. Reveal exact sources, methods and accounting in place. Keep missing evidence
   honest; no findings is not proof of correctness. Empty reports offer scope
   review without inventing a recommendation, severity or score.

Overview includes one compact architecture score summary and a Full score link.
Show the provisional range and assessed weight when structural evidence exists;
otherwise state that evidence is incomplete or not assessed. Keep dimension
breakdowns, formulas and parser coverage in the Architecture score tab.

## Use actual components

The shared `mirrorneuron-web-report-skill` (`mn-web-report-skill`) owns the
official shadcn/ui New York components, React, Radix UI and Lucide. This is the public component system used by Vercel v0, paired with Geist
fonts and semantic colors. Vercel's private GeistCN npm package is not used.

| Component | Report use |
| --- | --- |
| Button | Header, primary action, copy, playback and evidence actions |
| Dropdown Menu | Actions and graph commands, with standard menu keyboard behavior |
| Tooltip | Accessible icon controls |
| Tabs | Task navigation and selected-state semantics |
| Collapsible | More views |
| Popover | Graph settings |
| Sheet | Non-modal evidence side panel and narrow bottom sheet |
| Input | File/function search |
| Native Select | Large file/function inventories, layouts and baseline choices |
| Textarea | Canonical saved prompt text |

Use the standard components instead of adding custom menu, focus, tooltip or
button implementations. Customize report layout, density and evidence geometry.
Retain the component's semantics and named variants. Keep icons consistently
16px and decorative to assistive technology; name the parent action. Use words
where the operation needs explanation. Icon-only controls receive tooltips.

## Header and navigation

The header contains a bounded report title/source identity and one right-aligned
three-dot Actions dropdown. No logo. All global actions live there even when
there is only one. Snapshot/revision metadata is under Report details. Preserve
the full source identity in a tooltip when visually truncated.

Four primary tabs precede a Collapsible More views group. Opening a saved view
or pressing End must reveal an additional selected tab; Home returns to the
first view. Preserve source selection between related views.

## Evidence Sheet

Keep `modal={false}`, with no overlay or focus trap. The main report remains
interactive. Provide a real Sheet title/description and an X Close button with
an accessible name. Escape closes a nested menu before the Sheet. Closing the
Sheet restores focus to its initiating control.

Lead with full identity and evidence status. Show a useful next step before long
inventories. Expand source lists, methods, limitations and exact records only
when requested. Keep revision-bound before/after links, baseline-only entities,
parser gaps and equivalent evidence tables. Static relationships remain
candidates, not runtime proof.

Opening a saved prompt reveals its canonical text immediately. Copy preserves
those exact bytes. Keep the copy confirmation in a live status region.

## Ownership and performance

- `mn-skills/web_report_skill/`: shared header, navigation, evidence Sheet, controls,
  fonts, Geist theme, component sources, registry provenance and licenses.
- `report_ui/src/main.tsx`: architecture-only graph toolbar, layouts and playback
  adapter over `MNWebReport`. It bundles no second React runtime.
- `workspace_assets/report-shell.css`: responsive report geometry. Avoid
  replacing component interaction behavior in this stylesheet.
- `code-map.html` / `code-map.js`: domain content, evidence and chart adapter.
- `comparison-presentation.js`: pure comparison presentation policy.
- D3 Canvas and worker modules: graph layout, camera and rendering.

The bridge exposes `setView`, inspector visibility/title, playback state, graph
command availability/bindings and component mounting for dynamic content.
Menus and Sheets mount through Radix portals. Do not query a closed menu's
buttons to control a graph: bind named commands and publish their availability.

Native Select options remain domain-owned and memoized so replay does not
reconcile thousands of function names. Exact evidence tables remain plain
semantic tables. The graph filter Popover alone retains its hidden controls;
its source forwards `forceMount` through the Portal and the adapter restores
filter focus. The other menus and Sheet use their normal lifecycle.

## Build and publication

With Node 22+ in `report_ui/`:

```sh
npm ci
npm run build
npm test
```

Commit the adapter package lock, compiled `report-shell.js` and adapter SHA receipt.
Rebuild the shared component package in `mn-skills/web_report_skill/frontend`
when changing common controls. Its package owns `report-ui.js`, component CSS,
fonts, source/output hashes and notices. Publication copies those assets through
`mn_web_report_skill.write_assets`; blueprints do not own duplicate component sources. Users
opening saved reports need no Node build, React server, icon/font CDN or model
call. Browser React is bundled locally.

The shared skill pins the published Vercel CSS foundation and packages it as
`vendor/vercel-brand.css`.
The component stylesheet imports it into a named cascade layer so Tailwind's
actual component variants own controls. Geist Sans/Mono fonts are local with
SIL OFL notices. Lucide and all bundled packages retain their license notices.

Refresh compiled assets and all retained HTML shells together, with content
identities on asset URLs. Keep saved JSON/Markdown immutable. Reuse this
composition from another blueprint's own adapter; do not move report policy or
UI composition into the runtime.

## Review gates

- Main conclusion, coverage cue and next step are clear on the first screen.
- No logo, extra header action, duplicate finding or empty prompt section.
- Actual component keyboard access, menu dismissal, title references and focus
  restoration work; source links and canonical prompt copying remain correct.
- Resizing 992×864 → 600×900 → desktop causes no page overflow or lost controls.
- Empty, rich and partial reports retain honest evidence states.
- RedisRaft, xv6, three layouts, replay and the 10,000-node fixture still work.
- Publication tests preserve frozen data/report artifacts and validate local
  component assets. Run `report_ui` component tests after component changes.
