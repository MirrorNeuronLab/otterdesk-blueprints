D3 7.9.0, ISC license. Vendored from https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js
SHA-256: f2094bbf6141b359722c4fe454eb6c4b0f0e42cc10cc7af921fc158fceb86539
License: https://github.com/d3/d3/blob/v7.9.0/LICENSE
No report data is sent to a CDN.

The shared web report skill owns the pinned Vercel CSS foundation, local Geist
fonts, shadcn/ui, React, Radix and their notices. Publication copies those packaged
assets with `mn_web_report_skill.write_assets`. This directory owns D3, the SVG
sprite used in domain content and the architecture adapter's SHA receipt.

Icons: 15 selected SVGs from official lucide-static@1.59.0, combined into the
local lucide-sprite.svg. Source: https://registry.npmjs.org/lucide-static/-/lucide-static-1.59.0.tgz
License: lucide-LICENSE.txt (ISC and retained Feather MIT notice). Exact member
hashes and sprite hash: lucide-provenance.txt. The report embeds the sprite so
icons work without external requests, including when opening a saved report.

