# Architecture report adapter

The common report shell and real shadcn/ui components live in
`mn-skills/web_report_skill/frontend` (`mirrorneuron-web-report-skill`).
This folder owns only architecture graph controls, filters and playback.
It uses `MNWebReport` primitives and the already loaded shared React runtime.

Node 22+: `npm ci && npm run build && npm test`.
The build emits the small `workspace_assets/report-shell.js` adapter and its
`vendor/report-adapter-provenance.txt` SHA receipt. Shared CSS, fonts, component
source, licenses and the component bundle belong to the skill; publication copies
them using its Python API. A saved report needs no Node server or CDN.

The tests run the actual shared bundle followed by this adapter. Set
`MN_WEB_REPORT_ASSETS` when the shared skill lives outside the normal companion
workspace layout. Graph filter options stay memoized and domain-owned so replay
does not reconcile thousands of function choices.
