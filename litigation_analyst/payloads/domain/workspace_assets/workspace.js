"use strict";
const W = JSON.parse(document.getElementById("workspace-data").textContent);
const e = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const sourceById = new Map(W.sources.map(s => [s.source_id, s]));
const evidenceById = new Map(W.evidence.map(p => [p.evidence_id, p]));
const nodeById = new Map(W.graph.nodes.map(n => [n.id, n]));
const edgeById = new Map(W.graph.edges.map(r => [r.id, r]));
const views = [...primaryNavigation.flatMap(group=>group.routes), "Matter settings"];
const defaults = {view:"Overview", query:"", address:"", from:"", to:"", sourceIds:null, finding:null, source:null, sourceIsEvidence:false, graphSeed:"", graphTarget:"", graphPaths:false, graphMode:"case", mapSelection:"", reportId:"counsel-brief", explicit:true, limit:16, comparison:[], supportingOnly:false};
let state = {...defaults, ...(W.saved_state || {})};
let decisions = [...(W.decisions || [])];
let savedViews = [...(W.saved_views || [])];
const btn = (label, action, id="", extra="") => `<button type="button" data-action="${e(action)}" data-id="${e(id)}" ${extra}>${e(label)}</button>`;
const empty = text => `<p class="empty">${e(text)}</p>`;
const pills = (...values) => values.map(v => `<span class="pill">${e(v)}</span>`).join(" ");
const table = (headers, rows) => rows.length ? `<div class="table-wrap"><table><thead><tr>${headers.map(h=>`<th scope="col">${e(h)}</th>`).join("")}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(v=>`<td>${v}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : empty("No matching records in the selected authorized scope. Unavailable or unsearched records cannot establish absence.");
function notice(text) {document.getElementById("notice").textContent = text;}
function goto(update) {state={...state,...update};const next=encodeURIComponent(JSON.stringify(state));if(location.hash.slice(1)===next)render();else location.hash=next;}
window.addEventListener("hashchange", () => {try {state={...defaults,...JSON.parse(decodeURIComponent(location.hash.slice(1)))};} catch {state={...defaults};} render();});
function eventIncluded(event) {
  const raw = event.time.earliest;
  if ((state.from || state.to) && !raw) return false;
  const day = raw?.slice(0,10);
  return (!state.from || day>=state.from) && (!state.to || day<=state.to);
}
function visibleSources() {
  const matchingEvents = W.temporal.events.filter(eventIncluded);
  const allowedDates = new Set(matchingEvents.flatMap(x=>x.source_ids));
  const allowedAddress = new Set(W.temporal.events.filter(x=>Object.values(x.fields.headers).flat().includes(state.address)).flatMap(x=>x.source_ids));
  return W.sources.filter(s => (!state.sourceIds || state.sourceIds.includes(s.source_id)) &&
    (!state.address || allowedAddress.has(s.source_id)) && (!(state.from||state.to) || allowedDates.has(s.source_id)) &&
    (!state.query || (s.text ?? W.evidence.filter(p=>p.source_id===s.source_id).map(p=>p.text).join("\n")).toLocaleLowerCase().includes(state.query.toLocaleLowerCase()) || s.relative_path.toLocaleLowerCase().includes(state.query.toLocaleLowerCase())));
}
function visibleFindings() {const ids=new Set(visibleSources().map(s=>s.source_id)); return W.findings.filter(f=>!W.reading_review?.withheld_finding_ids.includes(f.id)&&f.supporting_evidence.concat(f.counter_evidence).some(id=>ids.has(evidenceById.get(id)?.source_id)));}
function evidenceButtons(ids) {return ids.map(id=>{const p=evidenceById.get(id);return p?btn(sourceById.get(p.source_id)?.relative_path || p.source_id,"evidence",id,`class="source-link" title="${e(sourceById.get(p.source_id)?.relative_path||p.source_id)}"`):'<span>Citation unavailable—verification required</span>';}).join(" ") || '<p class="muted">No matching retained passage. Search coverage is limited.</p>';}
function currentReview(f) {if(W.reading_review?.withheld_finding_ids.includes(f.id))return {...f,review_state:"Needs correction"};const items=f.review_history.concat(decisions.filter(d=>d.finding_id===f.id));const current=items.filter(d=>d.material_digest===f.material_digest);const byActor=new Map(current.map(d=>[d.actor,d]));const disagree=new Set([...byActor.values()].map(d=>JSON.stringify([d.action,d.text]))).size>1;const latest=items.at(-1);return latest?{...f,review_state:disagree?"Reviewers disagree":latest.material_digest===f.material_digest?latest.action:"Needs reassessment",reviewed_text:latest.text}:f;}
function findingCard(original, full=false) {
  const f=currentReview(original), scoped=new Set(visibleSources().map(s=>s.source_id));
  const outside=f.counter_evidence.filter(id=>!scoped.has(evidenceById.get(id)?.source_id));
  const hasReviewedWording=f.reviewed_text&&["Reviewed with qualification","Revised"].includes(f.review_state);
  return `<article class="card ${state.finding===f.id?"selected":""}"><div class="row">${pills(f.review_state, f.evidentiary_assessment, `Revision ${f.revision}`)}</div><h3>${e(f.title)}</h3><p>${e(hasReviewedWording?f.reviewed_text:f.assessment)}</p>${hasReviewedWording?`<details><summary>Original model draft</summary><p>${e(f.assessment)}</p></details>`:""}<small>${e(f.source_basis)} · ${e(f.model_review)}</small>
    <div class="section"><strong>Supporting records</strong><div class="actions">${evidenceButtons(f.supporting_evidence)}</div></div>
    ${state.supportingOnly?'<p class="warning">One-sided analytical subset. Restore counterevidence before preparing work product.</p>':`<div class="section"><strong>Counterevidence and alternatives</strong><div class="actions">${evidenceButtons(f.counter_evidence)}</div>${f.alternatives.map(a=>`<p>${e(a)}</p>`).join("")}</div>`}
    ${outside.length?`<p class="warning">${outside.length} linked counterevidence passage(s) fall outside the analytical filter. They remain inspectable above.</p>`:""}
    <p class="qualification"><strong>Limitations:</strong> ${e(f.limitations)}</p>
    <div class="actions">${btn(full?"Close finding":"Open finding","finding",full?"":f.id)} ${btn("Compare sources","compare-finding",f.id)} ${btn("Review wording","review",f.id)} ${btn("Missing information","finding-gaps",f.id)}</div>
    ${full?`<details><summary>Revision, source basis and review history</summary><p>Stable finding: ${e(f.id)} · ${e(f.origin)}</p><p>Source basis digest: ${e(f.material_digest)}</p>${table(["Actor / time","Action","Rationale / preserved wording"],f.review_history.concat(decisions.filter(d=>d.finding_id===f.id)).map(d=>[`${e(d.actor)}<br>${e(d.at)}`,e(d.action),`${e(d.rationale)}<p>${e(d.text)}</p>`]))}</details>`:""}</article>`;
}
function reviewAllowance() {
  const p=W.analysis.review_plan;if(!p)return "";
  return `<section class="card"><h3>${e(p.profile)} review allowance</h3><p>Up to ${p.max_rounds} round(s), ${p.max_decisions} investigation/readiness decisions, ${p.relationship_call_ceiling} separate relationship extraction decisions. Planning-boundary time allowance: ${p.seconds} seconds; in-flight requests can extend elapsed time.</p><p>${e(p.definition)}</p><p>${W.analysis.partial_review?"Partial review; sources and issues can remain unexamined.":"A workflow result does not certify exhaustive review."}</p></section>`;
}
function transactionReview() {
  const f=W.financial_review;if(!f||W.package_mode==="approved_excerpt_briefing")return "";
  return `<h3>Transaction reconciliation</h3><p>${e(f.status)}. Event type, ledger grouping and any supplied dates are counsel annotations; quotations and recorded numbers are verified.</p>${table(["Transaction / currency / ledger","Posting and reversal net","Recorded net / check","Request less approval / basis"],f.transactions.map(t=>[`${e(t.transaction_ref)} · ${e(t.currency)}<p>${e(t.ledger_id)}</p>`,e(t.posting_reversal_net??"Not supplied"),`${e(t.recorded_net_values.join(", ")||"Not supplied")}<p>${t.net_matches_recorded===null?"No comparable recorded net":t.net_matches_recorded?"Matches selected recorded net":"CONFLICT: inspect records"}</p>`,`${e(t.request_minus_approval??"Not established")}<p>${e(t.qualification)}</p>${evidenceButtons(t.evidence_ids)}`]))}${table(["Annotated event","Recorded amount","Date / basis","Exact source"],f.events.map(t=>[e(t.event_type),`${e(t.amount)} ${e(t.currency)}`,`${e(t.event_date||"Unresolved")}<p>${e(t.date_basis)}</p>`,evidenceButtons(t.evidence_ids)]))}`;
}
function overview() {
  if(W.reading_reports?.length)return readingOverview();
  const sources=visibleSources(), findings=visibleFindings();
  return `<h2>What needs review</h2><p>${e(W.goal)}</p>${reviewAllowance()}<div class="metrics">${btn(`${findings.length} findings · exact matching ledger`,"view","Findings")}${btn(`${sources.length} authorized source records`,"sources")}${W.package_mode==="approved_excerpt_briefing"?"":btn(`${W.gaps.length} open evidence gaps`,"view","Issues & evidence")}</div>
    ${findings.map(f=>findingCard(f)).join("") || empty("No evidence-grounded finding was retained. Inspect the sources and incomplete enquiries.")}
    <div class="grid"><section class="card"><h3>Decision-critical gaps</h3>${W.gaps.slice(0,4).map(g=>`<p>${btn(g.question,"gap",g.id)}</p>`).join("") || (W.package_mode==="approved_excerpt_briefing"?'<p>Unreviewed gap register is not included. Finding qualifications retain material limitations.</p>':'<p>No structured gap recorded. This does not certify completeness.</p>')}</section><section class="card"><h3>Since the previous snapshot</h3><p>${e(W.changes.mode)}</p><p>${W.changes.previous_snapshot?`${W.changes.items.length} change records; categories can overlap.`:"No comparable earlier authorized snapshot is available."}</p>${btn("Inspect changes","view","Since last review")}</section></div>
    <details><summary>Scope, coverage and counting basis</summary><p>${e(W.coverage.definition)}</p>${W.package_mode==="approved_excerpt_briefing"?'<p>Full sources and processing coverage are not included in this briefing.</p>':`${btn(`${sources.filter(s=>s.text!==null).length} readable records`,"readable")}${btn(`${sources.filter(s=>s.text===null).length} unreadable records`,"unreadable")}<p>Readable does not mean fully extracted or reviewed. Every count opens its exact records.</p>`}</details>`;
}
function findings() {return findingsView();}
function sourceGraphView() {
  const ids=new Set(visibleSources().map(s=>s.source_id));
  let matching=W.graph.edges.filter(r=>r.evidence_refs.every(p=>ids.has(p.source_id)) && (!state.explicit || !["model_proposal","hypothesis"].includes(r.kind)));
  const seed=state.graphSeed;
  if(seed) matching=matching.filter(r=>r.source===seed || r.target===seed);
  const edges=matching.slice(0,state.limit), nodes=[...new Set(edges.flatMap(r=>[r.source,r.target]))].map(id=>nodeById.get(id)).filter(Boolean);
  const positions=new Map(nodes.map((n,i)=>[n.id,{x:420+Math.cos(i*2*Math.PI/Math.max(1,nodes.length))*260,y:170+Math.sin(i*2*Math.PI/Math.max(1,nodes.length))*120}]));
  const svg=`<svg class="graph" viewBox="0 0 840 340" role="img" aria-label="Bounded directed relationship graph; equivalent node and edge tables follow"><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="#789d97"/></marker></defs>${edges.map(r=>{const a=positions.get(r.source),b=positions.get(r.target);return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" marker-end="url(#arrow)" class="${r.kind==="model_proposal"?"proposed":""}"/>`;}).join("")}${nodes.map(n=>{const p=positions.get(n.id);return `<circle cx="${p.x}" cy="${p.y}" r="12" class="${n.id===seed?"chosen":""}"/><text x="${p.x}" y="${p.y+26}" text-anchor="middle">${e(n.label.length>32?n.label.slice(0,29)+"…":n.label)}</text>`;}).join("")}</svg>`;
  const options=W.graph.nodes.map(n=>`<option value="${e(n.id)}">${e(n.label)}</option>`).join("");
  return `<h2>People & relationships</h2><p>${e(W.graph.definition)}</p><p>${e(W.graph.coverage)}</p><p class="qualification">Addresses stay separate from people. Employment intervals, account access and material identity require their own source-backed records; they are not inferred from communication.</p>
    <div class="toolbar"><label>Preview / one-hop neighborhood<select id="graph-seed"><option value="">All available relationships</option>${options}</select></label><label>Target for documented paths<select id="graph-target"><option value="">Any target</option>${options}</select></label>${btn("Show neighborhood","graph-selection")}${btn("Show documented paths","paths")}${btn(state.explicit?"Show proposed connections":"Explicit records only","toggle-explicit")}${btn("Expand displayed edges","expand")}${seed?btn("Apply address to investigation","apply-address",seed):""}</div>
    <p>${edges.length} of ${matching.length} authorized matching edges shown. Display cap ${state.limit}; preview does not change investigation filters.</p>${svg}
    ${table(["Node / type","Identity and source","Inspect"],nodes.map(n=>[`${e(n.label)}<br>${e(n.kind)}`,e(n.identity_status),n.evidence_id?btn("Open source unit","evidence",n.evidence_id):btn("Preview neighborhood","node",n.id)]))}
    ${table(["Directed relationship","Time basis / qualification","Supporting records"],edges.map(r=>[`${e(nodeById.get(r.source)?.label)} → ${e(nodeById.get(r.target)?.label)}<br>${e(r.relation)} · ${e(r.kind)}`,`${e(r.display_time)}<p>${e(r.qualification)}</p>`,evidenceButtons(r.evidence_refs.map(p=>p.evidence_id))]))}<div id="paths-result"></div>`;
}
function showPaths() {
  const result=W.graph.path_index[state.graphSeed];
  const panel=document.getElementById("paths-result");
  if(!result){panel.innerHTML=empty(`Path analysis not included for this seed. This snapshot prepares up to ${W.graph.path_seed_limit} address seeds. Use the co-worker's temporal path tool for another authorized seed.`);return;}
  const visible=new Set(visibleSources().map(s=>s.source_id));
  const rows=key=>result[key].filter(p=>(!state.graphTarget || p.target===state.graphTarget) && p.edge_ids.every(id=>edgeById.get(id).evidence_refs.every(r=>visible.has(r.source_id)))).map(p=>`<article class="path"><p>${p.edge_ids.map(id=>{const r=edgeById.get(id);return `${e(r.source)} → ${e(r.target)} (${e(r.relation)}, ${e(r.display_time)})`;}).join(" → ")}</p><div>${evidenceButtons([...new Set(p.edge_ids.flatMap(id=>edgeById.get(id).evidence_refs.map(r=>r.evidence_id)))])}</div><p>${e(JSON.stringify(p.temporal_checks))}</p></article>`).join("") || empty("No matching witness in this bounded prepared scope.");
  panel.innerHTML=`<section class="card"><h3>Documented paths</h3><p>${e(result.status)} · ${e(result.qualification)}</p><p>Search limits: 4 hops, 128 nodes, 49 edges, 256 paths; ${e(result.unresolved.join(", ") || "no reported frontier limit")}. Complete here describes the authorized header graph, not all matter relationships.</p><h3>Established strict order</h3>${rows("paths")}<h3>Unknown or uncertain ordering</h3>${rows("partial_paths")}<details><summary>Rejected ordering / conflicting source basis</summary>${rows("rejected_paths")}</details></section>`;
}
function chronology() {
  if(W.case_map&&W.package_mode!=="approved_excerpt_briefing")return readingChronology();
  if(W.package_mode==="approved_excerpt_briefing")return `<h2>Chronology</h2>${empty("Event chronology is not included in this excerpt-only briefing. Return to the authorized investigation snapshot.")}`;
  const ids=new Set(visibleSources().map(s=>s.source_id));
  const events=W.temporal.events.filter(x=>eventIncluded(x)&&x.source_ids.some(id=>ids.has(id))).sort((a,b)=>(a.time.earliest||"9999").localeCompare(b.time.earliest||"9999"));
  return `<h2>Chronology</h2><p>Source-represented event time, shown in the original offset. Capture: ${e(W.captured_at)}. The date first known is an investigation date, not an event date.</p><p class="qualification">Communications lane only in this version. Undated or unzoned records remain unresolved; roles, access, development and testimony dates are not manufactured.</p>
    <div class="timeline">${events.map(x=>`<article><strong>${e(x.display)}</strong><p>${e(x.title)}</p>${evidenceButtons(x.evidence_refs.map(p=>p.evidence_id))}<small>${e(x.basis)} · ${e(x.qualification)}</small></article>`).join("") || empty("No dated email event in the selected scope.")}</div>
    ${transactionReview()}${table(["Event time / precision","Event / lane / first retained","Source and qualification"],events.map(x=>[`${e(x.display)}<br>${e(x.precision)}`,`${e(x.title)}<br>${e(x.lane)}<p>First retained in workspace: ${e(x.first_known_at||"Not retained")} · knowledge revision ${e(x.known_from_revision||"unavailable")}</p>`,`${evidenceButtons(x.evidence_refs.map(p=>p.evidence_id))}<p>${e(x.qualification)}</p>`]))}`;
}
function issues() {
  if(W.package_mode==="approved_excerpt_briefing")return `<h2>Questions</h2>${empty("Unreviewed questions are not included in this briefing.")}`;
  return `<h2>Questions</h2><p class="muted">Counsel questions and proposed next steps.</p>
    ${(W.counsel_issues||[]).map(q=>`<article class="card"><h3>${e(q.question)}</h3><small>Needs review</small><div class="actions">${evidenceButtons(q.supporting_evidence)}</div>${q.counter_evidence.length?`<h4>Counterevidence</h4>${evidenceButtons(q.counter_evidence)}`:""}<details><summary>Context and missing information</summary><p>${e(q.status)}</p><p>${e(q.legal_framework||"No legal framework supplied")}</p><small>${e(q.framework_basis)}</small>${q.unknowns.map(value=>`<p>${e(value)}</p>`).join("")}</details></article>`).join("")||empty("No counsel questions were supplied.")}
    <section class="card"><h3>Next steps</h3>${nextSteps()||empty("No structured next steps were supplied.")}<small>Proposed review work; no collection or contact was performed.</small></section>
    <h3>Missing information</h3>${W.gaps.length?table(["Question","Record and closure test","Inspect"],W.gaps.map(g=>[e(g.question),`${e(g.requested_record||"Record to be specified")}<details><summary>Why it matters</summary><p>${e(g.why_it_matters||g.priority_basis)}</p><p>${e(g.closure_condition)}</p><p>${e(g.owner)} · ${e(g.internal_target||"No target assigned")}</p></details>`,btn("View action draft","gap",g.id)])):empty("No evidence gaps were recorded.")}
    <details><summary>Investigation questions (${W.issues.length})</summary>${table(["Question / draft assessment","Supporting sources","Counterevidence and alternatives","Missing information"],W.issues.map(h=>[`${e(h.question)}<p>${e(h.assessment)}</p>${pills(h.status)}`,evidenceButtons(h.supporting_evidence),`${evidenceButtons(h.contradictory_evidence)}${h.alternatives.map(a=>`<p>${e(a)}</p>`).join("")}`,h.gap_ids.map(id=>btn(W.gaps.find(g=>g.id===id)?.question,"gap",id)).join(" ")]))}</details>`;
}
function comparisons() {
  const options=W.evidence.map(p=>`<option value="${e(p.evidence_id)}">${e(sourceById.get(p.source_id)?.relative_path)} · ${p.start_offset}:${p.end_offset}</option>`).join("");
  return `<h2>Compare sources</h2><p>${btn("Back to documents","view","Evidence Explorer")}</p><div class="toolbar"><label>First source<select id="compare-a">${options}</select></label><label>Second source<select id="compare-b">${options}</select></label>${btn("Compare sources","compare-selected")}</div><div id="comparison-result">${state.comparison.length===2?comparisonPanels(...state.comparison):empty("Choose two source passages to compare.")}</div>`;
}
function comparisonPanels(a,b) {
  const panels=[a,b].map(id=>{const p=evidenceById.get(id);return p?`<article class="card"><h3>${e(sourceById.get(p.source_id)?.relative_path)}</h3><blockquote>${e(p.text)}</blockquote><p>${btn("View source context","evidence",id)}</p><details><summary>Source details</summary><small>Generated normalized span ${p.start_offset}:${p.end_offset} · ${e(p.content_sha256)}</small></details></article>`:empty("Citation unavailable—verification required.");}).join("");
  return `<div class="compare-grid">${panels}</div><section class="card"><h3>Comparison requires review</h3><p>Check the same identity, material/version, relevant time, meaning of terms, surrounding context and innocent alternatives. No automated dishonesty or contradiction finding is asserted.</p><p>Exact byte identity: ${evidenceById.get(a)?.content_sha256===evidenceById.get(b)?.content_sha256?"Same normalized source bytes; originals still have separate integrity records":"Not established by these versions"}. Similar wording does not establish copying or transfer direction.</p></section>`;
}
function explorer() {
  const sources=visibleSources(), events=W.temporal.events.filter(x=>x.source_ids.some(id=>sources.some(s=>s.source_id===id)));
  const periods=new Map();for(const x of events){const day=x.time.earliest?.slice(0,10)||"Date unresolved";const items=periods.get(day)||[];items.push(x);periods.set(day,items);}
  const distinct=items=>new Set(items.map(x=>x.metric_occurrence_id).filter(Boolean)).size;
  const pairs=new Map();for(const x of events){for(const sender of x.fields.headers.From){for(const field of ["To","Cc","Bcc"]){for(const recipient of x.fields.headers[field]){const key=JSON.stringify([sender,recipient,field]);const items=pairs.get(key)||[];items.push(x);pairs.set(key,items);}}}}
  return `<div class="page-intro"><div><h2>Evidence</h2><p class="muted">${sources.length} of ${W.sources.length} documents</p></div>${W.evidence.length?btn("Compare sources","view","Comparisons"):""}</div><form id="document-search" class="document-search" role="search"><label>Search documents<input id="document-query" value="${e(state.query)}" placeholder="Search text or file name"></label><button type="submit">Search</button>${state.query||state.address||state.from||state.to||state.sourceIds?btn("Reset filters","reset"):""}</form>${documentList(sources)}
    ${W.package_mode==="approved_excerpt_briefing"?'<p>Communication analytics are not included in this excerpt-only briefing.</p>':`<details><summary>Communication measure and exact record sets</summary><p>${e(W.temporal.count_definition)}</p><p>Full authorized snapshot: ${W.temporal.message_count.count} distinct identified messages; ${W.temporal.source_record_count} source email records; ${W.temporal.message_count.unresolved_multiplicity.length} records with unresolved multiplicity. Pair-cell sums would double-count multi-recipient messages.</p>
    ${table(["Equal-length UTC day / event basis","Distinct identified messages / source records","Exact rows"],[...periods].sort().map(([day,items])=>[e(day),`${distinct(items)} messages / ${items.length} source records / ${items.filter(x=>!x.metric_occurrence_id).length} unresolved<span class="bar" style="width:${Math.max(2,distinct(items)/Math.max(1,distinct(events))*100)}%"></span>`,btn("Open counted records","period",day)]))}
    <h3>Directed sender–recipient table</h3><p>Each cell counts distinct Message-ID occurrences under the displayed recipient field. Multi-recipient messages contribute to multiple pairs; pair counts are not additive. Missing Bcc records do not establish absence.</p>${table(["Sender → recipient / field","Distinct messages / source records","Drill through"],[...pairs].map(([key,items])=>{const [sender,recipient,field]=JSON.parse(key);return [`${e(sender)} → ${e(recipient)}<br>${e(field)}`,`${distinct(items)} / ${items.length}`,btn("Open pair records","pair",key)];}))}</details>`}
    `;
}
function workProduct() {
  const reviewed=eligibleBriefing();
  return `<h2>Reports</h2>${reportTabs()}${briefingReadiness()}
    ${reviewed.map(f=>`<article class="card"><h3>${e(f.title)}</h3>${pills(f.review_state)}<p>${e(f.reviewed_text)}</p>${evidenceButtons(f.supporting_evidence)}${f.counter_evidence.length?`<h4>Counterevidence</h4>${evidenceButtons(f.counter_evidence)}`:""}<p class="qualification">${e(f.limitations)}</p></article>`).join("")||empty("No reviewed wording is available for a briefing yet.")}`;
}
function changes() {
  return `<h2>Review history</h2>${historyTabs()}<p>${e(W.changes.mode)}</p>${W.changes.previous_snapshot?table(["Change","Before / after","Inspect"],W.changes.items.map(c=>[e(c.kind),`${e(c.before||"")}<p>${e(c.after||c.event_time||"")}</p>`,c.finding_id?btn("View finding","finding",c.finding_id):btn("View source","source",c.source_id)])):empty("No earlier snapshot is available to compare.")}`;
}
function audit() {
  const history=W.findings.flatMap(f=>f.review_history).concat(decisions);
  return `<h2>Review history</h2>${historyTabs()}${history.length?table(["Reviewer / time","Decision","Rationale and wording"],history.map(d=>[`${e(d.actor)}<br><small>${e(d.at)}</small>`,`${e(d.action)}<p>${btn(W.findings.find(f=>f.id===d.finding_id)?.title||"View finding","finding",d.finding_id)}</p>`,`${e(d.rationale)}<details><summary>Reviewed wording and source basis</summary><p>${e(d.text)}</p><small>${e(d.material_digest)}</small></details>`])):empty("No review decisions have been recorded.")}
    <details><summary>Processing and source integrity</summary><p>Capture ${e(W.captured_at)} · Stop reason ${e(W.analysis.stop_reason)}</p><p>Hashes describe the held copies; source authenticity remains unverified.</p>${table(["Document","Original SHA-256","Normalized SHA-256"],W.sources.map(source=>[e(source.relative_path),e(source.original_sha256),e(source.content_sha256)]))}</details>`;
}
function settings() {return `<h2>Matter settings</h2><section class="card"><h3>Saved views</h3>${btn("Save current view","save-view")}${savedViews.map((v,i)=>`<p>${btn(v.name,"open-view",String(i))} · Snapshot ${e(v.snapshot_id.slice(0,12))}</p>`).join("")||'<p>No saved view. Save a view, then save an investigation copy to retain it.</p>'}</section><section class="card"><h3>Execution, privacy and access</h3>${Object.values(W.privacy).map(s=>`<p>${e(s)}</p>`).join("")}<p>Scope: ${e(W.access_scope)}. Restrictions are applied before this webpage is generated. Browser filters do not change access rights.</p><p>Membrane: ${e(W.memory?.status || "Not attested")}. ${e(W.memory?.qualification || "")}</p></section><section class="card"><h3>Available scope and current limitations</h3>${Object.values(W.capabilities).map(s=>`<p>${e(s)}</p>`).join("")}</section>${W.sample?'<p class="warning">Synthetic EMC-2 sample; this is not a real matter.</p>':""}`;}
let renderedState = "";
function render() {
  const focusedGraphNode=document.activeElement?.matches?.(".map-node")?document.activeElement.dataset.id:null;
  state.limit=Math.max(1,Math.min(49,Number(state.limit)||16));
  if(!views.includes(state.view))state.view="Overview";
  if(!reportUI)initializeReport();
  const {source,sourceIsEvidence,...pageState}=state;
  const pageKey=JSON.stringify([pageState,decisions,savedViews,unsavedReviews,unsavedViews,copyRequested]);
  if(pageKey===renderedState) {
    if(state.source)openSource(state.source,state.sourceIsEvidence);
    else reportUI.setInspectorOpen(false);
    return;
  }
  renderedState=pageKey;
  reportUI.setView(navigationGroup(state.view)?.routes[0]||"Matter settings");
  document.getElementById("app").innerHTML=`<section class="scope" aria-label="Investigation scope"><details><summary>Filter investigation ${state.query||state.address||state.from||state.to||state.sourceIds?'· Active filters':""}</summary><div class="toolbar"><label>Search text<input id="query" value="${e(state.query)}" placeholder="Search documents"></label><label>Email address<input id="address" value="${e(state.address)}" placeholder="Sender or recipient"></label><label>From date (UTC)<input id="from" type="date" value="${e(state.from)}"></label><label>Through date (UTC)<input id="to" type="date" value="${e(state.to)}"></label>${btn("Apply filters","apply")}${btn("Reset filters","reset")}${btn(state.supportingOnly?"Restore counterevidence":"Supporting evidence only","toggle-support")}</div><small>Filters combine using AND. Address matches sender OR recipient. Unknown email dates are excluded by date filters. ${state.sourceIds?`${state.sourceIds.length} selected documents. `:""}Reports cover the full authorized snapshot.</small></details>${state.supportingOnly?'<p class="warning">Counterevidence is hidden. Restore it before creating a briefing.</p>':""}</section>
<main id="content" tabindex="-1">${({"Overview":overview,"Reports":reportsView,"Findings":findings,"People & relationships":graphView,"Chronology":chronology,"Issues & evidence":issues,"Comparisons":comparisons,"Evidence Explorer":explorer,"Work product":workProduct,"Since last review":changes,"Activity & audit":audit,"Matter settings":settings}[state.view])()}</main>${unsavedReminder()}`;
  reportUI.enhance(document.getElementById("app"));
  if(focusedGraphNode)[...document.querySelectorAll(".map-node")].find(node=>node.dataset.id===focusedGraphNode)?.focus({preventScroll:true});
  for(const [id,value] of [["graph-seed",state.graphSeed],["graph-target",state.graphTarget],["compare-a",state.comparison[0]],["compare-b",state.comparison[1]]]){const el=document.getElementById(id);if(el&&value)el.value=value;}
  if(state.view==="People & relationships" && state.graphMode==="sources" && state.graphPaths)showPaths();
  if(state.source)openSource(state.source,state.sourceIsEvidence);
  else reportUI.setInspectorOpen(false);
}
function openSource(id, isEvidence=false) {
  const p=isEvidence?evidenceById.get(id):null, source=sourceById.get(p?p.source_id:id);
  if(!source){notice("Citation unavailable—verification required.");return;}
  const text=source.text;
  const chars=text===null?[]:Array.from(text);
  const valid=p&&text!==null&&chars.slice(p.start_offset,p.end_offset).join("")===p.text;
  const cited=p?`Generated normalized character span ${p.start_offset}:${p.end_offset}`:"Full normalized source";
  const original=source.original_included?`originals/${source.original_sha256}${source.media_type==="application/pdf"?".pdf":".bin"}`:null;
  let page=null;if(source.media_type==="application/pdf"&&valid){const pages=[...chars.slice(0,p.start_offset+1).join("").matchAll(/(?:^|\n)Page (\d+):\n/g)];page=pages.at(-1)?.[1]||null;}
  const content=`<details><summary>Source details</summary><p>File name: ${e(source.relative_path)}</p><p>${e(source.source_id)} · ${e(cited)}</p><p>${e(source.extraction_status)} · ${e(source.review_state)}</p><p>Normalized SHA-256: ${e(source.content_sha256)}</p><p>Original hash verifies held bytes, not authenticity. ${e(source.locator_basis)}</p></details>
    <div class="actions">${original?`<a href="${e(original)}" ${source.media_type==="application/pdf"?'target="_blank" rel="noopener noreferrer"':`download="${e(source.relative_path.split("/").at(-1))}"`}>Open original</a>`:'<span>Original file not included in this package</span>'}${btn("Copy citation","copy-citation",p?p.evidence_id:source.source_id)}${p?btn("Compare sources","add-evidence-comparison",p.evidence_id):""}${btn("Flag extraction problem","flag-extraction",source.source_id)}</div>
    ${original&&source.media_type==="application/pdf"?`<h3>Original PDF ${page?`· physical page ${page}`:""}</h3><iframe title="Original PDF" src="${e(original)}${page?`#page=${page}`:""}"></iframe><p>Extracted span highlighted below. Original page-region alignment is unavailable; verify the original page.</p>`:""}
    <h3>${text===null?"Cited excerpt":"Source text"}</h3><div class="source-text">${text===null?(p?e(p.text):"Normalized text unavailable; inspect the original."):valid?`${e(chars.slice(0,p.start_offset).join(""))}<mark id="cited-span">${e(p.text)}</mark>${e(chars.slice(p.end_offset).join(""))}`:p?'Citation unavailable—verification required.':e(text)}</div>`;
  reportUI.openInspector(source.relative_path,content);document.getElementById("source-dialog").querySelector("mark")?.scrollIntoView({block:"center"});
}
function reviewFinding(id) {
  const f=W.findings.find(f=>f.id===id);if(!f)return;
  const dialog=document.getElementById("review-dialog");
  dialog.innerHTML=`<h2>Review ${e(f.title)}</h2><p>Record an attributable decision about this exact source basis. Independent model checking is not human approval.</p><label>Your name<input id="review-actor" maxlength="200" autocomplete="off"></label><label>Decision<select id="review-action"><option>Reviewed with qualification</option><option>Revised</option><option>Request evidence</option><option>Dismissed</option></select></label><label>Preserved / revised wording<textarea id="review-text" maxlength="4000">${e(currentReview(f).reviewed_text||f.assessment)}</textarea></label><label>Qualification and rationale<textarea id="review-rationale" maxlength="4000" placeholder="State what the evidence establishes and what remains unresolved"></textarea></label><div class="actions">${btn("Record review","commit-review",f.id,"class=\"primary\"")}${btn("Cancel","close-review")}</div>`;dialog.showModal();reportUI.enhance(dialog);
}
function download(name,body,type) {const url=URL.createObjectURL(new Blob([body],{type}));const a=document.createElement("a");a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function pageFor(data) {const clone=document.documentElement.cloneNode(true);clone.querySelector("#workspace-data").textContent=JSON.stringify(data).replace(/</g,"\\u003c").replace(/&/g,"\\u0026");clone.querySelector("#app").innerHTML="";for(const id of ["report-actions","report-navigation","report-inspector-ui"])clone.querySelector("#"+id).innerHTML="";clone.querySelectorAll("[data-radix-popper-content-wrapper],[data-slot=sheet-content],[data-slot=tooltip-content],[data-radix-focus-guard]").forEach(n=>n.remove());clone.querySelector("#notice").textContent="";clone.querySelectorAll("dialog").forEach(d=>{d.innerHTML="";d.removeAttribute("open");});return "<!doctype html>\n"+clone.outerHTML;}
function savedCopy() {const data={...W,decisions,saved_views:savedViews,saved_state:state,sources:W.sources.map(s=>({...s,original_included:false}))};download("investigation-snapshot.html",pageFor(data),"text/html");copyRequested=true;render();notice("Saved a local copy with authorized derivatives and review decisions. Original files are not included; keep the original run package for verification.");}
function exportPreview() {
  const approved=visibleFindings().map(currentReview).filter(f=>["Reviewed with qualification","Revised"].includes(f.review_state));
  const ids=new Set(approved.flatMap(f=>f.supporting_evidence.concat(f.counter_evidence)).map(id=>evidenceById.get(id)?.source_id));
  const dialog=document.getElementById("export-dialog");
  dialog.innerHTML=`<h2>Create briefing</h2><p>Frozen reviewed wording, exact supporting and contrary excerpts, qualifications and current review attribution/rationale. ${approved.length} reviewed findings / ${ids.size} source versions. Original model wording, unreviewed questions/gaps, full sources and original files are excluded.</p><label>Recipient / audience<input id="export-audience" maxlength="200"></label><p class="warning">This is a local copy without authenticated access control. Later revocation cannot revoke exported copies. Confirm the recipient is authorized for every included excerpt and review record.</p>${table(["Included source","Version"],[...ids].map(id=>[e(sourceById.get(id)?.relative_path),e(sourceById.get(id)?.content_sha256)]))}<div class="actions">${btn("Confirm authorized recipient and create copy","commit-export","",approved.length&&!state.supportingOnly?'class="primary"':'disabled')}${btn("Cancel","close-export")}</div>${state.supportingOnly?'<p>Restore the balanced view before exporting.</p>':""}`;dialog.showModal();reportUI.enhance(dialog);
}
function briefing() {
  const audience=document.getElementById("export-audience").value.trim();if(!audience){notice("Enter the authorized audience.");return;}
  const findings=visibleFindings().map(currentReview).filter(f=>["Reviewed with qualification","Revised"].includes(f.review_state));
  const evidenceIds=new Set(findings.flatMap(f=>f.supporting_evidence.concat(f.counter_evidence))), evidence=W.evidence.filter(p=>evidenceIds.has(p.evidence_id));
  const sourceIds=new Set(evidence.map(p=>p.source_id));
  const edges=W.graph.edges.filter(r=>!["model_proposal","hypothesis"].includes(r.kind)&&r.evidence_refs.every(p=>evidenceIds.has(p.evidence_id))), nodeIds=new Set(edges.flatMap(r=>[r.source,r.target]));
  const reviewFields=["id","finding_id","material_digest","actor","at","action","text","rationale","snapshot_id"];
  const data={...W,title:"Reviewed investigation briefing",goal:"Frozen reviewed wording with supporting and contrary excerpts.",audience,package_mode:"approved_excerpt_briefing",
    analysis:{status:"Reviewed excerpt briefing",stop_reason:W.analysis.stop_reason,scope:"Selected reviewed excerpts; full investigation is not included"},
    findings:findings.map((f,i)=>({...f,title:`Reviewed finding ${i+1}`,assessment:f.reviewed_text,issue_ids:[],gap_ids:[],
      review_history:[...new Map(f.review_history.concat(decisions.filter(d=>d.finding_id===f.id)).filter(d=>d.material_digest===f.material_digest).map(d=>[d.actor,d])).values()].filter(d=>d.text===f.reviewed_text&&["Reviewed with qualification","Revised"].includes(d.action)).map(d=>Object.fromEntries(reviewFields.filter(k=>k in d).map(k=>[k,d[k]])))})),
    sources:W.sources.filter(s=>sourceIds.has(s.source_id)).map(s=>({...s,text:null,original_included:false,extraction_status:"Approved excerpts only; original source not included"})),evidence,
    graph:{...W.graph,edges,nodes:W.graph.nodes.filter(n=>nodeIds.has(n.id)),path_index:{}},
    temporal:{...W.temporal,events:[],nodes:[],edges:[],message_count:{count:0,unresolved_multiplicity:[]},source_record_count:0,count_definition:"Communication analytics unavailable in this excerpt-only briefing"},
    issues:[],gaps:[],counsel_issues:[],matter_scope:{intended_decision:"",parties:[],transaction_refs:[]},
    financial_review:{events:[],transactions:[],evidence:[],status:"Not included in reviewed excerpt briefing"},
    capabilities:{...W.capabilities,financial_scenarios:"Unreviewed arithmetic not included",legal_elements:"Counsel intake not included"},
    coverage:{source_ids:[...sourceIds],readable_ids:[],unreadable_ids:[],definition:"Authorized approved excerpts only; this package does not include originals or full search coverage"},
    reading_reports:[],reading_tasks:[],reading_copy:null,case_map:null,reading_review:{checks:[],withheld_finding_ids:[]},
    consistency:{status:"Not included in reviewed briefing",checks:[],withheld_finding_ids:[]},
    changes:{mode:"Frozen briefing; previous snapshots excluded",previous_snapshot:null,items:[]},decisions:[],saved_views:[],saved_state:{...defaults}};
  download("reviewed-briefing.html",pageFor(data),"text/html");document.getElementById("export-dialog").close();notice("Created a frozen briefing with reviewed findings and their supporting and contrary excerpts. Originals are excluded.");
}
async function performAction(action,id="",trigger) {
  if(action==="view")goto({view:id,finding:null,source:null});
  else if(action==="finding")goto({view:"Findings",finding:id||null});
  else if(action==="evidence")goto({source:id,sourceIsEvidence:true});
  else if(action==="source")goto({source:id,sourceIsEvidence:false});
  else if(action==="sources")goto({view:"Evidence Explorer"});
  else if(action==="readable"||action==="unreadable")goto({view:"Evidence Explorer",sourceIds:visibleSources().filter(s=>(s.text!==null)===(action==="readable")).map(s=>s.source_id)});
  else if(action==="apply")goto({query:document.getElementById("query").value,address:document.getElementById("address").value.trim().toLowerCase(),from:document.getElementById("from").value,to:document.getElementById("to").value});
  else if(action==="reset")goto({...defaults,view:state.view});
  else if(action==="toggle-support")goto({supportingOnly:!state.supportingOnly});
  else if(action==="graph-selection")goto({graphSeed:document.getElementById("graph-seed").value,graphTarget:document.getElementById("graph-target").value,graphPaths:false});
  else if(action==="node")goto({graphSeed:id});
  else if(action==="apply-address")goto({address:id});
  else if(action==="toggle-explicit")goto({explicit:!state.explicit});
  else if(action==="expand")goto({limit:Math.min(49,state.limit+16)});
  else if(action==="paths")goto({graphSeed:document.getElementById("graph-seed").value,graphTarget:document.getElementById("graph-target").value,graphPaths:true});
  else if(action==="compare-finding"){const f=W.findings.find(x=>x.id===id);const conflict=W.reading_review?.checks.find(check=>check.finding_id===id)?.evidence_ids[0];goto({view:"Comparisons",source:null,comparison:[f.supporting_evidence[0],conflict||f.counter_evidence[0]||f.supporting_evidence[1]].filter(Boolean)});}
  else if(action==="compare-selected")goto({comparison:[document.getElementById("compare-a").value,document.getElementById("compare-b").value]});
  else if(action==="add-comparison"||action==="add-evidence-comparison"){const evidenceId=action==="add-comparison"?W.evidence.find(p=>p.source_id===id)?.evidence_id:id;if(!evidenceId){notice("No exact retained passage for this source.");return;}goto({view:"Comparisons",source:null,comparison:state.comparison.concat(evidenceId).slice(-2)});reportUI.closeInspector();}
  else if(action==="close-source"){if(state.source)goto({source:null});else reportUI.closeInspector();}
  else if(action==="close-review")document.getElementById("review-dialog").close();
  else if(action==="close-export")document.getElementById("export-dialog").close();
  else if(action==="review")reviewFinding(id);
  else if(action==="commit-review"){
    const f=W.findings.find(x=>x.id===id),actor=document.getElementById("review-actor").value.trim(),text=document.getElementById("review-text").value.trim(),rationale=document.getElementById("review-rationale").value.trim();
    if(!actor||!text||!rationale){notice("Enter your name, wording, and qualification/rationale.");return;}
    decisions.push({id:crypto.randomUUID(),finding_id:id,material_digest:f.material_digest,actor,at:new Date().toISOString(),action:document.getElementById("review-action").value,text,rationale,before:f.assessment,snapshot_id:W.snapshot_id});
    markUnsaved("review");document.getElementById("review-dialog").close();render();notice("Review recorded in this open page. Save an investigation copy or export review decisions to retain it.");
  } else if(action==="save-copy")savedCopy();
  else if(action==="save-reviews")download("review-decisions.json",JSON.stringify({version:"mn.litigation.review.v1",matter_id:W.matter_id,snapshot_id:W.snapshot_id,decisions:W.findings.flatMap(f=>f.review_history).concat(decisions)},null,2),"application/json");
  else if(action==="save-view"){const name=prompt("Name this view");if(name){savedViews.push({name,snapshot_id:W.snapshot_id,state:{...state}});markUnsaved("view");render();notice("View saved in the open page. Save an investigation copy to retain it.");}}
  else if(action==="open-view"){const saved=savedViews[Number(id)];if(saved&&saved.snapshot_id===W.snapshot_id)goto(saved.state);else notice("Saved view belongs to a different snapshot.");}
  else if(action==="export-preview")exportPreview();
  else if(action==="commit-export")briefing();
  else if(action==="period"){const ids=W.temporal.events.filter(x=>(x.time.earliest?.slice(0,10)||"Date unresolved")===id).flatMap(x=>x.source_ids);goto({view:"Evidence Explorer",sourceIds:ids});}
  else if(action==="pair"){const [sender,recipient,field]=JSON.parse(id);const ids=W.temporal.events.filter(x=>x.fields.headers.From.includes(sender)&&x.fields.headers[field].includes(recipient)).flatMap(x=>x.source_ids);goto({view:"Evidence Explorer",sourceIds:ids});}
  else if(action==="finding-gaps")goto({view:"Issues & evidence"});
  else if(action==="gap"){const g=W.gaps.find(x=>x.id===id);const content=`<h3>${e(g.question)}</h3><p>${e(g.priority_basis)}</p><p>Requested record or interview: ${e(g.requested_record||"Specify record")}</p><p>Decision it informs: ${e(g.why_it_matters||"Requires attorney review")}</p><p>Proposed priority: ${e(g.priority||"Needs review")}</p><p>Closure condition: ${e(g.closure_condition)}</p><p>Owner: ${e(g.owner)} · Internal target: ${e(g.internal_target||"Not assigned")}</p><p>This draft does not send a request, contact anyone or change a collection.</p>${evidenceButtons(g.source_evidence_ids)}${btn("Copy action draft","copy-gap",id)}`;reportUI.openInspector("Investigation action draft",content,trigger);}
  else if(action==="copy-gap"){const g=W.gaps.find(x=>x.id===id);await copy(`Investigation draft: ${g.question}\nRationale: ${g.priority_basis}\nClosure: ${g.closure_condition}\nSnapshot: ${W.snapshot_id}\nEvidence: ${g.source_evidence_ids.join(", ")}\nRecord/interview: ${g.requested_record||"Specify record"}\nDecision: ${g.why_it_matters||"Requires review"}\nOwner: ${g.owner}\nInternal target: ${g.internal_target||"Not assigned"}`);}
  else if(action==="copy-citation"){const p=evidenceById.get(id),s=sourceById.get(p?p.source_id:id);await copy(`${s.source_id} · normalized SHA-256 ${s.content_sha256}${p?` · generated character span ${p.start_offset}:${p.end_offset}\n${p.text}`:""}`);}
  else if(action==="flag-extraction"){notice("Extraction problem draft prepared. Export this note for the co-worker; originals remain unchanged.");download("extraction-problem.json",JSON.stringify({snapshot_id:W.snapshot_id,source_id:id,action:"Verify extraction against original",status:"Draft for review"},null,2),"application/json");}
}
document.addEventListener("click", event => {
  const button=event.target.closest("[data-action]");if(button)performAction(button.dataset.action,button.dataset.id,button);
});
async function copy(text){try{await navigator.clipboard.writeText(text);notice("Copied with source/snapshot reference.");}catch{download("citation.txt",text,"text/plain");notice("Clipboard unavailable. Citation saved to a text file.");}}
if(location.hash){try{state={...defaults,...JSON.parse(decodeURIComponent(location.hash.slice(1)))};}catch{state={...defaults};}}
render();
