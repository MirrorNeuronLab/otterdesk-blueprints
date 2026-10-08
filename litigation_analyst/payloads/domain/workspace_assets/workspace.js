"use strict";
const W = JSON.parse(document.getElementById("workspace-data").textContent);
const e = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const sourceById = new Map(W.sources.map(s => [s.source_id, s]));
const evidenceById = new Map(W.evidence.map(p => [p.evidence_id, p]));
const nodeById = new Map(W.graph.nodes.map(n => [n.id, n]));
const edgeById = new Map(W.graph.edges.map(r => [r.id, r]));
const views = ["Overview", "Findings", "People & relationships", "Chronology", "Issues & evidence", "Comparisons", "Evidence Explorer", "Work product", "Since last review", "Activity & audit", "Matter settings"];
const defaults = {view:"Overview", query:"", address:"", from:"", to:"", sourceIds:null, finding:null, source:null, sourceIsEvidence:false, graphSeed:"", graphTarget:"", graphPaths:false, explicit:true, limit:16, comparison:[], supportingOnly:false};
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
function visibleFindings() {const ids=new Set(visibleSources().map(s=>s.source_id)); return W.findings.filter(f=>f.supporting_evidence.concat(f.counter_evidence).some(id=>ids.has(evidenceById.get(id)?.source_id)));}
function evidenceButtons(ids) {return ids.map(id=>{const p=evidenceById.get(id);return p?btn(sourceById.get(p.source_id)?.relative_path || p.source_id,"evidence",id):'<span>Citation unavailable—verification required</span>';}).join(" ") || '<p class="muted">No matching retained passage. Search coverage is limited.</p>';}
function currentReview(f) {const items=f.review_history.concat(decisions.filter(d=>d.finding_id===f.id));const current=items.filter(d=>d.material_digest===f.material_digest);const byActor=new Map(current.map(d=>[d.actor,d]));const disagree=new Set([...byActor.values()].map(d=>JSON.stringify([d.action,d.text]))).size>1;const latest=items.at(-1);return latest?{...f,review_state:disagree?"Reviewers disagree":latest.material_digest===f.material_digest?latest.action:"Needs reassessment",reviewed_text:latest.text}:f;}
function findingCard(original, full=false) {
  const f=currentReview(original), scoped=new Set(visibleSources().map(s=>s.source_id));
  const outside=f.counter_evidence.filter(id=>!scoped.has(evidenceById.get(id)?.source_id));
  const hasReviewedWording=f.reviewed_text&&["Reviewed with qualification","Revised"].includes(f.review_state);
  return `<article class="card ${state.finding===f.id?"selected":""}"><div class="row">${pills(f.review_state, f.evidentiary_assessment, `Revision ${f.revision}`)}</div><h3>${e(f.title)}</h3><p>${e(hasReviewedWording?f.reviewed_text:f.assessment)}</p>${hasReviewedWording?`<details><summary>Original model draft</summary><p>${e(f.assessment)}</p></details>`:""}<small>${e(f.source_basis)} · ${e(f.model_review)}</small>
    <div class="section"><strong>Supporting records</strong><div class="actions">${evidenceButtons(f.supporting_evidence)}</div></div>
    ${state.supportingOnly?'<p class="warning">One-sided analytical subset. Restore counterevidence before preparing work product.</p>':`<div class="section"><strong>Counterevidence and alternatives</strong><div class="actions">${evidenceButtons(f.counter_evidence)}</div>${f.alternatives.map(a=>`<p>${e(a)}</p>`).join("")}</div>`}
    ${outside.length?`<p class="warning">${outside.length} linked counterevidence passage(s) fall outside the analytical filter. They remain inspectable above.</p>`:""}
    <p class="qualification"><strong>Limitations:</strong> ${e(f.limitations)}</p>
    <div class="actions">${btn(full?"Close finding":"Open finding","finding",full?"":f.id)} ${btn("Compare passages","compare-finding",f.id)} ${btn("Review wording","review",f.id)} ${btn("Inspect evidence gaps","finding-gaps",f.id)}</div>
    ${full?`<details><summary>Revision, source basis and review history</summary><p>Stable finding: ${e(f.id)} · ${e(f.origin)}</p><p>Source basis digest: ${e(f.material_digest)}</p>${table(["Actor / time","Action","Rationale / preserved wording"],f.review_history.concat(decisions.filter(d=>d.finding_id===f.id)).map(d=>[`${e(d.actor)}<br>${e(d.at)}`,e(d.action),`${e(d.rationale)}<p>${e(d.text)}</p>`]))}</details>`:""}</article>`;
}
function overview() {
  const sources=visibleSources(), findings=visibleFindings();
  return `<h2>What needs review</h2><p>${e(W.goal)}</p><div class="metrics">${btn(`${findings.length} findings · exact matching ledger`,"view","Findings")}${btn(`${sources.length} authorized source records`,"sources")}${W.package_mode==="approved_excerpt_briefing"?"":btn(`${W.gaps.length} open evidence gaps`,"view","Issues & evidence")}</div>
    ${findings.map(f=>findingCard(f)).join("") || empty("No evidence-grounded finding was retained. Inspect the sources and incomplete enquiries.")}
    <div class="grid"><section class="card"><h3>Decision-critical gaps</h3>${W.gaps.slice(0,4).map(g=>`<p>${btn(g.question,"gap",g.id)}</p>`).join("") || (W.package_mode==="approved_excerpt_briefing"?'<p>Unreviewed gap register is not included. Finding qualifications retain material limitations.</p>':'<p>No structured gap recorded. This does not certify completeness.</p>')}</section><section class="card"><h3>Since the previous snapshot</h3><p>${e(W.changes.mode)}</p><p>${W.changes.previous_snapshot?`${W.changes.items.length} change records; categories can overlap.`:"No comparable earlier authorized snapshot is available."}</p>${btn("Inspect changes","view","Since last review")}</section></div>
    <details><summary>Scope, coverage and counting basis</summary><p>${e(W.coverage.definition)}</p>${W.package_mode==="approved_excerpt_briefing"?'<p>Full sources and processing coverage are not included in this briefing.</p>':`${btn(`${sources.filter(s=>s.text!==null).length} readable records`,"readable")}${btn(`${sources.filter(s=>s.text===null).length} unreadable records`,"unreadable")}<p>Readable does not mean fully extracted or reviewed. Every count opens its exact records.</p>`}</details>`;
}
function findings() {const selected=W.findings.find(f=>f.id===state.finding);return `<h2>Findings</h2>${selected?findingCard(selected,true):visibleFindings().map(f=>findingCard(f)).join("") || empty("No retained finding in the selected scope.")}`;}
function graphView() {
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
  if(W.package_mode==="approved_excerpt_briefing")return `<h2>Chronology</h2>${empty("Event chronology is not included in this excerpt-only briefing. Return to the authorized investigation snapshot.")}`;
  const ids=new Set(visibleSources().map(s=>s.source_id));
  const events=W.temporal.events.filter(x=>eventIncluded(x)&&x.source_ids.some(id=>ids.has(id))).sort((a,b)=>(a.time.earliest||"9999").localeCompare(b.time.earliest||"9999"));
  return `<h2>Chronology</h2><p>Source-represented event time, shown in the original offset. Capture: ${e(W.captured_at)}. The date first known is an investigation date, not an event date.</p><p class="qualification">Communications lane only in this version. Undated or unzoned records remain unresolved; roles, access, development and testimony dates are not manufactured.</p>
    <div class="timeline">${events.map(x=>`<article><strong>${e(x.display)}</strong><p>${e(x.title)}</p>${evidenceButtons(x.evidence_refs.map(p=>p.evidence_id))}<small>${e(x.basis)} · ${e(x.qualification)}</small></article>`).join("") || empty("No dated email event in the selected scope.")}</div>
    ${table(["Event time / precision","Event / lane / first retained","Source and qualification"],events.map(x=>[`${e(x.display)}<br>${e(x.precision)}`,`${e(x.title)}<br>${e(x.lane)}<p>First retained in workspace: ${e(x.first_known_at||"Not retained")} · knowledge revision ${e(x.known_from_revision||"unavailable")}</p>`,`${evidenceButtons(x.evidence_refs.map(p=>p.evidence_id))}<p>${e(x.qualification)}</p>`]))}`;
}
function issues() {
  if(W.package_mode==="approved_excerpt_briefing")return `<h2>Issues & evidence</h2>${empty("Unreviewed question and gap objects are not included in this briefing. Inspect the finding's preserved qualifications.")}`;
  return `<h2>Issues & evidence</h2><p>Investigation questions. Counsel-defined elements or claim limitations have not been supplied.</p>${table(["Question / assessment","Supporting records","Counterevidence / alternatives","Missing proof"],W.issues.map(h=>[`${e(h.question)}<p>${e(h.assessment)}</p>${pills(h.status)}`,evidenceButtons(h.supporting_evidence),`${evidenceButtons(h.contradictory_evidence)}${h.alternatives.map(a=>`<p>${e(a)}</p>`).join("")}`,h.gap_ids.map(id=>btn(W.gaps.find(g=>g.id===id)?.question,"gap",id)).join(" ")]))}
    <h3>Evidence gaps</h3>${table(["Missing information","Affected findings / purpose","Closure condition","Next action"],W.gaps.map(g=>[e(g.question),`${g.finding_ids.map(id=>btn(W.findings.find(f=>f.id===id)?.title,"finding",id)).join(" ")}<p>${e(g.priority_basis)}</p>`,e(g.closure_condition),btn("Create action draft","gap",g.id)]))}`;
}
function comparisons() {
  const options=W.evidence.map(p=>`<option value="${e(p.evidence_id)}">${e(sourceById.get(p.source_id)?.relative_path)} · ${p.start_offset}:${p.end_offset}</option>`).join("");
  return `<h2>Comparisons</h2><div class="toolbar"><label>Earlier / first record<select id="compare-a">${options}</select></label><label>Later / second record<select id="compare-b">${options}</select></label>${btn("Compare source passages","compare-selected")}</div><div id="comparison-result">${state.comparison.length===2?comparisonPanels(...state.comparison):empty("Choose two exact passages. A semantic difference alone does not establish contradiction.")}</div>`;
}
function comparisonPanels(a,b) {
  const panels=[a,b].map(id=>{const p=evidenceById.get(id);return p?`<article class="card"><h3>${e(sourceById.get(p.source_id)?.relative_path)}</h3><blockquote>${e(p.text)}</blockquote><small>Generated normalized span ${p.start_offset}:${p.end_offset} · ${e(p.content_sha256)}</small><p>${btn("Expand source context","evidence",id)}</p></article>`:empty("Citation unavailable—verification required.");}).join("");
  return `<div class="compare-grid">${panels}</div><section class="card"><h3>Comparison requires review</h3><p>Check the same identity, material/version, relevant time, meaning of terms, surrounding context and innocent alternatives. No automated dishonesty or contradiction finding is asserted.</p><p>Exact byte identity: ${evidenceById.get(a)?.content_sha256===evidenceById.get(b)?.content_sha256?"Same normalized source bytes; originals still have separate integrity records":"Not established by these versions"}. Similar wording does not establish copying or transfer direction.</p></section>`;
}
function explorer() {
  const sources=visibleSources(), events=W.temporal.events.filter(x=>x.source_ids.some(id=>sources.some(s=>s.source_id===id)));
  const periods=new Map();for(const x of events){const day=x.time.earliest?.slice(0,10)||"Date unresolved";const items=periods.get(day)||[];items.push(x);periods.set(day,items);}
  const distinct=items=>new Set(items.map(x=>x.metric_occurrence_id).filter(Boolean)).size;
  const pairs=new Map();for(const x of events){for(const sender of x.fields.headers.From){for(const field of ["To","Cc","Bcc"]){for(const recipient of x.fields.headers[field]){const key=JSON.stringify([sender,recipient,field]);const items=pairs.get(key)||[];items.push(x);pairs.set(key,items);}}}}
  return `<h2>Evidence Explorer</h2><p>Literal record filter in this offline snapshot. Questions requiring analysis belong in the co-worker chat, which uses Membrane memory and original-source intelligence.</p>
    ${W.package_mode==="approved_excerpt_briefing"?'<p>Communication analytics are not included in this excerpt-only briefing.</p>':`<details><summary>Communication measure and exact record sets</summary><p>${e(W.temporal.count_definition)}</p><p>Full authorized snapshot: ${W.temporal.message_count.count} distinct identified messages; ${W.temporal.source_record_count} source email records; ${W.temporal.message_count.unresolved_multiplicity.length} records with unresolved multiplicity. Pair-cell sums would double-count multi-recipient messages.</p>
    ${table(["Equal-length UTC day / event basis","Distinct identified messages / source records","Exact rows"],[...periods].sort().map(([day,items])=>[e(day),`${distinct(items)} messages / ${items.length} source records / ${items.filter(x=>!x.metric_occurrence_id).length} unresolved<span class="bar" style="width:${Math.max(2,distinct(items)/Math.max(1,distinct(events))*100)}%"></span>`,btn("Open counted records","period",day)]))}
    <h3>Directed sender–recipient table</h3><p>Each cell counts distinct Message-ID occurrences under the displayed recipient field. Multi-recipient messages contribute to multiple pairs; pair counts are not additive. Missing Bcc records do not establish absence.</p>${table(["Sender → recipient / field","Distinct messages / source records","Drill through"],[...pairs].map(([key,items])=>{const [sender,recipient,field]=JSON.parse(key);return [`${e(sender)} → ${e(recipient)}<br>${e(field)}`,`${distinct(items)} / ${items.length}`,btn("Open pair records","pair",key)];}))}</details>`}
    ${table(["Source / version","Document type / extraction","Review / inspection"],sources.map(s=>[`${e(s.relative_path)}<br><small>${e(s.source_id)} · ${e(s.content_sha256)}</small>`,`${e(s.media_type)}<p>${e(s.extraction_status)}</p>`,`${e(s.review_state)}<p>${btn("Open source","source",s.source_id)} ${btn("Add to comparison","add-comparison",s.source_id)}</p>`]))}`;
}
function workProduct() {
  const reviewed=W.findings.map(currentReview).filter(f=>["Reviewed with qualification","Revised"].includes(f.review_state));
  return `<h2>Work product</h2><p>Reviewed wording is separate from model assessment. Save a local investigation copy to retain decisions and views; nothing is saved automatically in browser storage.</p>
    <div class="actions">${btn("Save investigation copy","save-copy")}${btn("Export review decisions","save-reviews")}${btn("Create briefing","export-preview","","class=\"primary\"")}</div>
    ${reviewed.map(f=>`<article class="card"><h3>${e(f.title)}</h3>${pills(f.review_state)}<p>${e(f.reviewed_text)}</p>${evidenceButtons(f.supporting_evidence)}<h3>Counterevidence</h3>${evidenceButtons(f.counter_evidence)}<p class="qualification">${e(f.limitations)}</p></article>`).join("") || empty("No human-reviewed wording is available yet. Review a finding before creating an approved briefing.")}
    <section class="card"><h3>Witness preparation / action drafts</h3>${W.gaps.map(g=>`<p>${btn(`Clarify: ${g.question}`,"gap",g.id)}</p>`).join("") || '<p>No structured gap supplied.</p>'}<p>These are neutral investigation drafts; no witness has been contacted and no discovery request has been sent.</p></section>`;
}
function changes() {return `<h2>Since last review</h2><p>${e(W.changes.mode)}</p><p>${W.changes.previous_snapshot?`${e(W.changes.previous_snapshot.slice(0,12))} → ${e(W.snapshot_id.slice(0,12))}`:"No comparable earlier authorized snapshot. Current records do not establish when an event first happened."}</p><p>${e(W.changes.definition)}</p>${table(["Change","Before / after","Inspect"],W.changes.items.map(c=>[e(c.kind),`${e(c.before||"")}<p>${e(c.after||c.event_time||"")}</p>`,c.finding_id?btn("Open finding","finding",c.finding_id):btn("Open source","source",c.source_id)]))}`;}
function audit() {return `<h2>Activity & audit</h2><p>Capture ${e(W.captured_at)} · ${e(W.analysis.status)} · Stop reason ${e(W.analysis.stop_reason)}</p><p>Import and integrity records describe the held copies. They do not establish pre-import custody, truth or admissibility.</p>${table(["Actor / time","Object / action","Rationale / source revision"],W.findings.flatMap(f=>f.review_history).concat(decisions).map(d=>[`${e(d.actor)}<br>${e(d.at)}`,`${e(d.finding_id)}<br>${e(d.action)}`,`${e(d.rationale)}<br>${e(d.material_digest)}`]))}<details><summary>Snapshot integrity / processing</summary>${table(["Source","Original bytes SHA-256","Normalized version"],W.sources.map(s=>[e(s.source_id),e(s.original_sha256),e(s.content_sha256)]))}</details>`;}
function settings() {return `<h2>Matter settings</h2><section class="card"><h3>Saved views</h3>${savedViews.map((v,i)=>`<p>${btn(v.name,"open-view",String(i))} · Snapshot ${e(v.snapshot_id.slice(0,12))}</p>`).join("")||'<p>No saved view. Save a view, then save an investigation copy to retain it.</p>'}</section><section class="card"><h3>Execution, privacy and access</h3>${Object.values(W.privacy).map(s=>`<p>${e(s)}</p>`).join("")}<p>Scope: ${e(W.access_scope)}. Restrictions are applied before this webpage is generated. Browser filters do not change access rights.</p><p>Membrane: ${e(W.memory?.status || "Not attested")}. ${e(W.memory?.qualification || "")}</p></section><section class="card"><h3>Available scope and current limitations</h3>${Object.values(W.capabilities).map(s=>`<p>${e(s)}</p>`).join("")}</section>${W.sample?'<p class="warning">Synthetic EMC-2 sample; this is not a real matter.</p>':""}`;}
function render() {
  state.limit=Math.max(1,Math.min(49,Number(state.limit)||16));
  if(!views.includes(state.view))state.view="Overview";
  document.getElementById("app").innerHTML=`<header><div class="header-row"><div><span class="eyebrow">OtterDesk · Investigation workspace</span><h1>${e(W.title)}</h1><p>${e(W.analysis.status)} · Snapshot ${e(W.snapshot_id.slice(0,12))} · ${e(W.audience)}</p></div><div class="actions">${btn("Save view","save-view")}${btn("Save investigation copy","save-copy")}${btn("Create briefing","export-preview","","class=\"primary\"")}</div></div></header>
    <section class="scope" aria-label="Investigation scope"><div class="toolbar"><label>Record text / filename<input id="query" value="${e(state.query)}" placeholder="Search authorized records"></label><label>Address<input id="address" value="${e(state.address)}" placeholder="Exact address, either sender or recipient"></label><label>Event time from (UTC)<input id="from" type="date" value="${e(state.from)}"></label><label>Event time through (UTC)<input id="to" type="date" value="${e(state.to)}"></label>${btn("Apply to investigation","apply")}${btn("Reset filters","reset")}${btn(state.supportingOnly?"Restore balanced view":"Supporting evidence only","toggle-support")}</div><small>Dimensions combine using AND. Address matches sender OR recipient. Date filters exclude unknown event dates. ${state.sourceIds?`${state.sourceIds.length} selected source records. `:""}Preview selection does not alter this scope.</small>${state.supportingOnly?'<p class="warning">One-sided analytical subset; briefing creation is blocked until balance is restored.</p>':""}</section>
    <div class="workspace"><nav aria-label="Investigation views">${views.map(v=>btn(v,"view",v,v===state.view?'aria-current="page"':"")).join("")}</nav><main id="content" tabindex="-1">${({"Overview":overview,"Findings":findings,"People & relationships":graphView,"Chronology":chronology,"Issues & evidence":issues,"Comparisons":comparisons,"Evidence Explorer":explorer,"Work product":workProduct,"Since last review":changes,"Activity & audit":audit,"Matter settings":settings}[state.view])()}</main></div>`;
  for(const [id,value] of [["graph-seed",state.graphSeed],["graph-target",state.graphTarget],["compare-a",state.comparison[0]],["compare-b",state.comparison[1]]]){const el=document.getElementById(id);if(el&&value)el.value=value;}
  if(state.view==="People & relationships" && state.graphPaths)showPaths();
  if(state.source)openSource(state.source,state.sourceIsEvidence);
  else if(document.getElementById("source-dialog").open)document.getElementById("source-dialog").close();
}
function openSource(id, isEvidence=false) {
  const p=isEvidence?evidenceById.get(id):null, source=sourceById.get(p?p.source_id:id);
  if(!source){notice("Citation unavailable—verification required.");return;}
  const dialog=document.getElementById("source-dialog"), text=source.text;
  const valid=p&&text!==null&&text.slice(p.start_offset,p.end_offset)===p.text;
  const cited=p?`Generated normalized character span ${p.start_offset}:${p.end_offset}`:"Full normalized source";
  const original=source.original_included?`originals/${source.original_sha256}${source.media_type==="application/pdf"?".pdf":".bin"}`:null;
  let page=null;if(source.media_type==="application/pdf"&&valid){const pages=[...text.slice(0,p.start_offset+1).matchAll(/(?:^|\n)Page (\d+):\n/g)];page=pages.at(-1)?.[1]||null;}
  dialog.innerHTML=`<div class="dialog-head"><div><h2>${e(source.relative_path)}</h2><small>${e(source.source_id)} · ${e(cited)}</small></div>${btn("Back to investigation","close-source")}</div><p>${e(source.extraction_status)} · ${e(source.review_state)}</p><p class="qualification">Original hash verifies held bytes, not truth or admissibility. ${e(source.locator_basis)}</p>
    <div class="actions">${original?`<a href="${e(original)}" ${source.media_type==="application/pdf"?'target="_blank" rel="noopener noreferrer"':`download="${e(source.relative_path.split("/").at(-1))}"`}>Open original</a>`:'<span>Source not included in this package</span>'}${btn("Copy citation","copy-citation",p?p.evidence_id:source.source_id)}${p?btn("Add to comparison","add-evidence-comparison",p.evidence_id):""}${btn("Flag extraction problem","flag-extraction",source.source_id)}</div>
    ${original&&source.media_type==="application/pdf"?`<h3>Original PDF ${page?`· physical page ${page}`:""}</h3><iframe title="Original PDF" src="${e(original)}${page?`#page=${page}`:""}"></iframe><p>Extracted span highlighted below. Original page-region alignment is unavailable; verify the original page.</p>`:""}
    <h3>${text===null?"Retained cited excerpt":"Normalized text and surrounding context"}</h3><div class="source-text">${text===null?(p?e(p.text):"Normalized text unavailable; inspect the original."):valid?`${e(text.slice(0,p.start_offset))}<mark id="cited-span">${e(p.text)}</mark>${e(text.slice(p.end_offset))}`:p?'Citation unavailable—verification required.':e(text)}</div>`;
  if(!dialog.open)dialog.showModal();dialog.querySelector("mark")?.scrollIntoView({block:"center"});
}
function reviewFinding(id) {
  const f=W.findings.find(f=>f.id===id);if(!f)return;
  const dialog=document.getElementById("review-dialog");
  dialog.innerHTML=`<h2>Review ${e(f.title)}</h2><p>Record an attributable decision about this exact source basis. Independent model checking is not human approval.</p><label>Your name<input id="review-actor" maxlength="200" autocomplete="off"></label><label>Decision<select id="review-action"><option>Reviewed with qualification</option><option>Revised</option><option>Request evidence</option><option>Dismissed</option></select></label><label>Preserved / revised wording<textarea id="review-text" maxlength="4000">${e(currentReview(f).reviewed_text||f.assessment)}</textarea></label><label>Qualification and rationale<textarea id="review-rationale" maxlength="4000" placeholder="State what the evidence establishes and what remains unresolved"></textarea></label><div class="actions">${btn("Record review","commit-review",f.id,"class=\"primary\"")}${btn("Cancel","close-review")}</div>`;dialog.showModal();
}
function download(name,body,type) {const url=URL.createObjectURL(new Blob([body],{type}));const a=document.createElement("a");a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function pageFor(data) {const clone=document.documentElement.cloneNode(true);clone.querySelector("#workspace-data").textContent=JSON.stringify(data).replace(/</g,"\\u003c").replace(/&/g,"\\u0026");clone.querySelector("#app").innerHTML="";clone.querySelector("#notice").textContent="";clone.querySelectorAll("dialog").forEach(d=>{d.innerHTML="";d.removeAttribute("open");});return "<!doctype html>\n"+clone.outerHTML;}
function savedCopy() {const data={...W,decisions,saved_views:savedViews,saved_state:state,sources:W.sources.map(s=>({...s,original_included:false}))};download("investigation-snapshot.html",pageFor(data),"text/html");notice("Saved a local copy with authorized derivatives and review decisions. Original files are not included; keep the original run package for verification.");}
function exportPreview() {
  const approved=visibleFindings().map(currentReview).filter(f=>["Reviewed with qualification","Revised"].includes(f.review_state));
  const ids=new Set(approved.flatMap(f=>f.supporting_evidence.concat(f.counter_evidence)).map(id=>evidenceById.get(id)?.source_id));
  const dialog=document.getElementById("export-dialog");
  dialog.innerHTML=`<h2>Create briefing</h2><p>Frozen reviewed wording, exact supporting and contrary excerpts, qualifications and current review attribution/rationale. ${approved.length} reviewed findings / ${ids.size} source versions. Original model wording, unreviewed questions/gaps, full sources and original files are excluded.</p><label>Recipient / audience<input id="export-audience" maxlength="200"></label><p class="warning">This is a local copy without authenticated access control. Later revocation cannot revoke exported copies. Confirm the recipient is authorized for every included excerpt and review record.</p>${table(["Included source","Version"],[...ids].map(id=>[e(sourceById.get(id)?.relative_path),e(sourceById.get(id)?.content_sha256)]))}<div class="actions">${btn("Confirm authorized recipient and create copy","commit-export","",approved.length&&!state.supportingOnly?'class="primary"':'disabled')}${btn("Cancel","close-export")}</div>${state.supportingOnly?'<p>Restore the balanced view before exporting.</p>':""}`;dialog.showModal();
}
function briefing() {
  const audience=document.getElementById("export-audience").value.trim();if(!audience){notice("Enter the authorized audience.");return;}
  const findings=visibleFindings().map(currentReview).filter(f=>["Reviewed with qualification","Revised"].includes(f.review_state));
  const evidenceIds=new Set(findings.flatMap(f=>f.supporting_evidence.concat(f.counter_evidence))), evidence=W.evidence.filter(p=>evidenceIds.has(p.evidence_id));
  const sourceIds=new Set(evidence.map(p=>p.source_id));
  const edges=W.graph.edges.filter(r=>!["model_proposal","hypothesis"].includes(r.kind)&&r.evidence_refs.every(p=>evidenceIds.has(p.evidence_id))), nodeIds=new Set(edges.flatMap(r=>[r.source,r.target]));
  const reviewFields=["id","finding_id","material_digest","actor","at","action","text","rationale","snapshot_id"];
  const data={...W,title:"Reviewed investigation briefing",goal:"Frozen reviewed wording with supporting and contrary excerpts.",audience,package_mode:"approved_excerpt_briefing",
    analysis:{...W.analysis,status:"Reviewed excerpt briefing",scope:"Selected reviewed excerpts; full investigation is not included"},
    findings:findings.map((f,i)=>({...f,title:`Reviewed finding ${i+1}`,assessment:f.reviewed_text,issue_ids:[],gap_ids:[],
      review_history:[...new Map(f.review_history.concat(decisions.filter(d=>d.finding_id===f.id)).filter(d=>d.material_digest===f.material_digest).map(d=>[d.actor,d])).values()].filter(d=>d.text===f.reviewed_text&&["Reviewed with qualification","Revised"].includes(d.action)).map(d=>Object.fromEntries(reviewFields.filter(k=>k in d).map(k=>[k,d[k]])))})),
    sources:W.sources.filter(s=>sourceIds.has(s.source_id)).map(s=>({...s,text:null,original_included:false,extraction_status:"Approved excerpts only; original source not included"})),evidence,
    graph:{...W.graph,edges,nodes:W.graph.nodes.filter(n=>nodeIds.has(n.id)),path_index:{}},
    temporal:{...W.temporal,events:[],nodes:[],edges:[],message_count:{count:0,unresolved_multiplicity:[]},source_record_count:0,count_definition:"Communication analytics unavailable in this excerpt-only briefing"},
    issues:[],gaps:[],
    coverage:{source_ids:[...sourceIds],readable_ids:[],unreadable_ids:[],definition:"Authorized approved excerpts only; this package does not include originals or full search coverage"},
    changes:{mode:"Frozen briefing; previous snapshots excluded",previous_snapshot:null,items:[]},decisions:[],saved_views:[],saved_state:{...defaults}};
  download("reviewed-briefing.html",pageFor(data),"text/html");document.getElementById("export-dialog").close();notice("Created a frozen briefing with reviewed findings and their supporting and contrary excerpts. Originals are excluded.");
}
document.addEventListener("click", async event => {
  const button=event.target.closest("[data-action]");if(!button)return;
  const {action,id}=button.dataset;
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
  else if(action==="compare-finding"){const f=W.findings.find(x=>x.id===id);goto({view:"Comparisons",comparison:[f.supporting_evidence[0],f.counter_evidence[0]||f.supporting_evidence[1]].filter(Boolean)});}
  else if(action==="compare-selected")goto({comparison:[document.getElementById("compare-a").value,document.getElementById("compare-b").value]});
  else if(action==="add-comparison"||action==="add-evidence-comparison"){const evidenceId=action==="add-comparison"?W.evidence.find(p=>p.source_id===id)?.evidence_id:id;if(!evidenceId){notice("No exact retained passage for this source.");return;}goto({view:"Comparisons",comparison:state.comparison.concat(evidenceId).slice(-2)});document.getElementById("source-dialog").close();}
  else if(action==="close-source"){if(state.source)goto({source:null});else document.getElementById("source-dialog").close();}
  else if(action==="close-review")document.getElementById("review-dialog").close();
  else if(action==="close-export")document.getElementById("export-dialog").close();
  else if(action==="review")reviewFinding(id);
  else if(action==="commit-review"){
    const f=W.findings.find(x=>x.id===id),actor=document.getElementById("review-actor").value.trim(),text=document.getElementById("review-text").value.trim(),rationale=document.getElementById("review-rationale").value.trim();
    if(!actor||!text||!rationale){notice("Enter your name, wording, and qualification/rationale.");return;}
    decisions.push({id:crypto.randomUUID(),finding_id:id,material_digest:f.material_digest,actor,at:new Date().toISOString(),action:document.getElementById("review-action").value,text,rationale,before:f.assessment,snapshot_id:W.snapshot_id});
    document.getElementById("review-dialog").close();render();notice("Review recorded in this open page. Save an investigation copy or export review decisions to retain it.");
  } else if(action==="save-copy")savedCopy();
  else if(action==="save-reviews")download("review-decisions.json",JSON.stringify({version:"mn.litigation.review.v1",matter_id:W.matter_id,snapshot_id:W.snapshot_id,decisions:W.findings.flatMap(f=>f.review_history).concat(decisions)},null,2),"application/json");
  else if(action==="save-view"){const name=prompt("Name this view");if(name){savedViews.push({name,snapshot_id:W.snapshot_id,state:{...state}});notice("View saved in the open page. Save an investigation copy to retain it.");}}
  else if(action==="open-view"){const saved=savedViews[Number(id)];if(saved&&saved.snapshot_id===W.snapshot_id)goto(saved.state);else notice("Saved view belongs to a different snapshot.");}
  else if(action==="export-preview")exportPreview();
  else if(action==="commit-export")briefing();
  else if(action==="period"){const ids=W.temporal.events.filter(x=>(x.time.earliest?.slice(0,10)||"Date unresolved")===id).flatMap(x=>x.source_ids);goto({view:"Evidence Explorer",sourceIds:ids});}
  else if(action==="pair"){const [sender,recipient,field]=JSON.parse(id);const ids=W.temporal.events.filter(x=>x.fields.headers.From.includes(sender)&&x.fields.headers[field].includes(recipient)).flatMap(x=>x.source_ids);goto({view:"Evidence Explorer",sourceIds:ids});}
  else if(action==="finding-gaps")goto({view:"Issues & evidence"});
  else if(action==="gap"){const g=W.gaps.find(x=>x.id===id);const dialog=document.getElementById("source-dialog");dialog.innerHTML=`<div class="dialog-head"><h2>Investigation action draft</h2>${btn("Back to investigation","close-source")}</div><h3>${e(g.question)}</h3><p>${e(g.priority_basis)}</p><p>Closure condition: ${e(g.closure_condition)}</p><p>Owner: ${e(g.owner)} · Internal target: not set</p><p>This draft does not send a request, contact anyone or change a collection.</p>${evidenceButtons(g.source_evidence_ids)}${btn("Copy action draft","copy-gap",id)}`;if(!dialog.open)dialog.showModal();}
  else if(action==="copy-gap"){const g=W.gaps.find(x=>x.id===id);await copy(`Investigation draft: ${g.question}\nRationale: ${g.priority_basis}\nClosure: ${g.closure_condition}\nSnapshot: ${W.snapshot_id}\nEvidence: ${g.source_evidence_ids.join(", ")}\nOwner: Unassigned\nInternal target: Not set`);}
  else if(action==="copy-citation"){const p=evidenceById.get(id),s=sourceById.get(p?p.source_id:id);await copy(`${s.source_id} · normalized SHA-256 ${s.content_sha256}${p?` · generated character span ${p.start_offset}:${p.end_offset}\n${p.text}`:""}`);}
  else if(action==="flag-extraction"){notice("Extraction problem draft prepared. Export this note for the co-worker; originals remain unchanged.");download("extraction-problem.json",JSON.stringify({snapshot_id:W.snapshot_id,source_id:id,action:"Verify extraction against original",status:"Draft for review"},null,2),"application/json");}
});
async function copy(text){try{await navigator.clipboard.writeText(text);notice("Copied with source/snapshot reference.");}catch{download("citation.txt",text,"text/plain");notice("Clipboard unavailable. Citation saved to a text file.");}}
if(location.hash){try{state={...defaults,...JSON.parse(decodeURIComponent(location.hash.slice(1)))};}catch{state={...defaults};}}
render();
