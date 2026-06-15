# VC Assistant SPEC

## What We Want To Achieve

Build a reviewable VC analysis workflow that monitors a folder containing one or more startup document packets, groups those documents by company, performs privacy-safe public research, and writes organized score-only reports.

## Customer Problem

Early-stage startup review is noisy. Pitch decks, notes, founder bios, traction updates, market claims, and technical material arrive in mixed formats. VC analysts need a fast way to compare early opportunities with lightweight heuristics while preserving evidence and avoiding fake precision.

## Design Details

The blueprint is a service-style OtterDesk workflow with five actors:

- `startup_folder_watcher`
- `startup_document_reader`
- `public_market_researcher`
- `vc_heuristic_scorer`
- `vc_report_writer`

The workflow groups first-level input subfolders as companies. Loose files are grouped by inferred company names from filenames or document text. Public research is constrained to privacy-safe queries based on company names, product categories, domains, and public claims.

The online research layer uses `w3m_browser_skill` first for lightweight public source collection and can use `web_browser_skill` as an optional rendered-browser fallback for JavaScript-heavy public sources such as Crunchbase. The workflow records source status, snippets, warnings, and blocked/login/robots outcomes rather than bypassing access controls.

## Input

The prototype accepts local startup documents in PDF, TXT, Markdown, JSON, and CSV formats. Text-like files are read directly. PDF files are recorded as evidence metadata and may require OCR support in fuller deployments.

## Output: Expected Customer Outcome

Each company gets a dedicated output folder with structured JSON, Markdown, source records, and local evidence records. The report covers:

- Berkus Method
- Scorecard / Bill Payne Method
- Risk Factor Summation Method
- Venture Capital Method
- First Chicago Method
- Comparables / Market Multiple Method
- Cost-to-Duplicate Method

If evidence is missing for a method, the method status is `insufficient_evidence`.

## Evaluation Criteria

- Company grouping is explainable and stable.
- All seven method sections are present for every company.
- Scores are included where evidence exists.
- Missing evidence is explicit and not hallucinated.
- Public research avoids confidential local excerpts.
- Public research attempts company website, Crunchbase/profile, founder public profile, funding mention, press, competitor, and market-context verification where configured.
- Outputs are organized into one subfolder per company.
- No investment decision label is emitted.

## Prototype Limits

This is an early heuristic report assistant. Scores are not valuations, investment recommendations, legal advice, or financial advice. Comparable, exit, and rebuild-cost outputs are deliberately conservative when source evidence is thin.

## Upgrade Path To Real Customer Use

Add robust PDF/OCR extraction, richer source citation capture, customer-specific scoring weights, authenticated market-data and funding-data connectors, analyst review annotations, historical calibration against partner decisions, and governance controls for confidential data handling.
