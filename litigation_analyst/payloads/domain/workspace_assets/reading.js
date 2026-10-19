/* Reading and graph presentation over the authorized frozen workspace. */
function money(value, currency) {
  if(value===null||value===undefined)return "Not established";
  const amount=/^(-?)(\d+)(?:\.(\d+))?$/.exec(String(value));
  if(!amount)return `${e(currency)} ${e(value)}`;
  return `${e(currency)} ${amount[1]}${amount[2].replace(/\B(?=(\d{3})+(?!\d))/g,",")}.${(amount[3]||"").padEnd(2,"0")}`;
}

function readingFlags() {
  const count=(W.reading_review?.withheld_finding_ids||[]).length;
  if(!count)return "";
  return `<div class="review-notice"><span><strong>${count} finding${count===1?" needs":"s need"} review.</strong> Available records conflict with draft claims.</span>${btn("Review findings","view","Findings")}</div>`;
}
function flaggedFinding(id) {
  const finding=W.findings.find(f=>f.id===id), checks=(W.reading_review?.checks||[]).filter(check=>check.finding_id===id);
  const evidenceIds=[...new Set(checks.flatMap(check=>check.evidence_ids))];
  return `<article class="card flagged-finding ${state.finding===id?"selected":""}"><div class="section-title"><h3>${e(finding?.title||"Finding withheld during consistency review")}</h3>${pills("Needs correction")}</div><p>Available records conflict with this draft. It remains excluded from briefing exports.</p><div class="actions">${evidenceButtons(evidenceIds)}</div>${finding?`<details ${state.finding===id?'open':""}><summary>Original draft and review reason</summary><p>${e(finding.assessment)}</p><p class="qualification">${e(finding.limitations)}</p>${checks.map(check=>`<p>${e(check.reason)}</p>`).join("")}</details><div class="actions">${btn("Compare sources","compare-finding",id)}${btn("Missing information","finding-gaps",id)}</div>`:""}</article>`;
}
function findingsView() {
  const flags=W.reading_review?.withheld_finding_ids||[], visible=visibleFindings();
  const selected=visible.find(f=>f.id===state.finding);
  const pending=visible.filter(needsReview), completed=visible.filter(f=>!needsReview(f));
  if(selected)return `<h2>Findings</h2>${findingCard(selected,true)}`;
  return `<h2>Findings</h2>${flags.length||pending.length?`<h3>Needs attention</h3>${flags.map(flaggedFinding).join("")}${pending.map(f=>findingCard(f)).join("")}`:
    empty(visible.length?"No findings need review in this view.":"No findings match this view.")}
    ${completed.length?`<details ${!pending.length&&!flags.length?'open':""}><summary>Reviewed findings (${completed.length})</summary>${completed.map(f=>findingCard(f)).join("")}</details>`:""}`;
}
function readingOverview() {
  const financial=W.financial_review, first=financial.transactions[0];
  const records=financial.events.filter(r=>!first||(r.transaction_ref===first.transaction_ref&&r.currency===first.currency&&r.ledger_id===first.ledger_id));
  const synthetic=W.sample||W.sources.some(s=>s.text?.includes("SYNTHETIC TEST MATTER"));
  const retained=visibleFindings();
  return `<div class="page-intro"><div><h2>What the records support</h2><p>${e(W.matter_scope?.intended_decision||W.goal)}</p></div>${primaryAction()}</div>
    ${synthetic?'<p class="sample-label">Synthetic test matter</p>':""}
    <div class="reading-grid overview-main"><section class="card record-summary"><div class="section-title"><div><span class="eyebrow">Recorded facts</span><h3>${e(first?.transaction_ref||"Current findings")}</h3></div>${btn("View timeline","view","Chronology")}</div>
      ${records.length?`<div class="record-amounts">${records.filter(r=>["requested","approved","net_balance"].includes(r.event_type)).slice(0,6).map(r=>`<div><span>${e(({requested:"Requested",approved:"Stated approval",net_balance:"Recorded net"})[r.event_type])}</span><strong>${money(r.amount,r.currency)}</strong>${evidenceButtons(r.evidence_ids)}</div>`).join("")}</div>`:
        retained.length?retained.slice(0,2).map(f=>`<h4>${e(f.title)}</h4><p>${e(currentReview(f).reviewed_text||f.assessment)}</p>${btn("View finding","finding",f.id)}`).join(""):empty("Review the available documents and flagged claims to establish what the records support.")}
      ${first?`<p class="summary-result">Request less stated approval <strong>${money(first.request_minus_approval,first.currency)}</strong></p><p class="summary-result">Posting / reversal net <strong>${money(first.posting_reversal_net,first.currency)}</strong></p><p class="qualification">${e(first.qualification)}</p><details><summary>Record classifications and scope</summary><p>Event types and ledger grouping are counsel annotations. Exact quotations and recorded amounts are verified.</p>${financial.transactions.length>1?`<p>${financial.transactions.length} transaction groups are available. This summary shows ${e(first.transaction_ref)}.</p>${btn("View all transaction records","view","Chronology")}`:""}</details>`:""}</section>
      <section class="card"><span class="eyebrow">Next useful work</span><h3>What remains unresolved</h3>${nextSteps(3)||W.gaps.slice(0,3).map(g=>`<p>${btn(g.question,"gap",g.id)}</p>`).join("")||empty("No structured next steps were supplied.")}${btn("View questions","view","Issues & evidence")}</section></div>
    ${readingFlags()}
    <div class="overview-counts" aria-label="Investigation counts">${btn(`${W.sources.length} documents`,"sources")}${btn(`${W.temporal.nodes.length} correspondents`,"view","People & relationships")}${btn(`${W.gaps.length} evidence gaps`,"view","Issues & evidence")}</div>
    <div class="reading-grid"><section class="card"><h3>People & events</h3><div class="person-chips">${W.temporal.nodes.slice(0,5).map(n=>btn(n.names.join(" / ")||n.label,"open-map",n.id)).join("")}</div>${btn("Open graph","open-map")}</section><section class="card"><h3>Review scope</h3><p>${e(W.analysis.scope)}.</p><details><summary>Coverage and provenance</summary><p>${W.coverage.readable_ids.length} readable documents. ${retained.length} narrative draft findings remain available after record checks.</p>${reviewAllowance()}<p>Snapshot ${e(W.snapshot_id)}</p>${W.reading_copy?`<p>${e(W.reading_copy.definition)}</p>`:""}</details></section></div>`;
}
function markdownInline(value) {
  return e(value).replace(/\[([^\]\n]+)\]\((?:evidence:|exact-source-passages\.md#)([a-zA-Z0-9-]+)\)/g,(_,label,id)=>
    evidenceById.has(id)?`<button class="citation-link" data-action="evidence" data-id="${id}">${label} ↗</button>`:label)
    .replace(/`([^`]+)`/g,"<code>$1</code>").replace(/\*\*([^*]+)\*\*/g,"<strong>$1</strong>")
    .replace(/\\([|_\[\]()*`])/g,"$1");
}
function markdownRows(line) {
  return line.trim().replace(/^\||\|$/g,"").split(/(?<!\\)\|/).map(s=>s.trim());
}
function renderMarkdown(text) {
  const lines=String(text).replace(/\r\n/g,"\n").split("\n"), blocks=[];
  let i=0, heading=0;
  while(i<lines.length) {
    const line=lines[i];
    if(!line.trim()){i++;continue;}
    if(line.startsWith("```")) {
      const code=[];i++;while(i<lines.length&&!lines[i].startsWith("```"))code.push(lines[i++]);i++;
      blocks.push(`<pre><code>${e(code.join("\n"))}</code></pre>`);continue;
    }
    const title=/^(#{1,6})\s+(.+)$/.exec(line);
    if(title){const level=Math.min(6,title[1].length+1);blocks.push(`<h${level} id="report-heading-${heading++}">${markdownInline(title[2])}</h${level}>`);i++;continue;}
    if(line.startsWith("|")&&lines[i+1]&&/^\|[\s:|\-]+\|$/.test(lines[i+1])) {
      const headers=markdownRows(line), rows=[];i+=2;
      while(i<lines.length&&lines[i].startsWith("|"))rows.push(markdownRows(lines[i++]).map(markdownInline));
      blocks.push(table(headers,rows));continue;
    }
    if(/^>\s?/.test(line)){const quote=[];while(i<lines.length&&/^>\s?/.test(lines[i]))quote.push(lines[i++].replace(/^>\s?/,""));blocks.push(`<blockquote>${quote.map(markdownInline).join("\n")}</blockquote>`);continue;}
    if(/^(?:[-*]|\d+\.)\s/.test(line)){const ordered=/^\d+\./.test(line),items=[];while(i<lines.length&&(ordered?/^\d+\.\s/:/^[-*]\s/).test(lines[i]))items.push(`<li>${markdownInline(lines[i++].replace(/^(?:[-*]|\d+\.)\s/,""))}</li>`);blocks.push(`<${ordered?"ol":"ul"}>${items.join("")}</${ordered?"ol":"ul"}>`);continue;}
    blocks.push(`<p>${markdownInline(line)}</p>`);i++;
  }
  return blocks.join("\n");
}
function reportsView() {
  const reports=W.reading_reports||[], selected=reports.find(r=>r.id===state.reportId)||reports[0];

  if(!selected)return `<h2>Reports</h2>${reportTabs()}${briefingReadiness()}${empty("Reading reports are not included in this package.")}`;
  const headings=[...selected.markdown.matchAll(/^#{1,6}\s+(.+)$/gm)];
  return `<h2>Reports</h2>${reportTabs()}${briefingReadiness()}<p class="muted">Reports cover the full authorized snapshot. Use Actions to download Markdown or save a copy.</p>
    <div class="report-tabs">${reports.map(r=>btn(r.title,"select-report",r.id,r.id===selected.id?'aria-pressed="true"':"" )).join("")}</div>
    <div class="report-layout"><aside class="report-toc"><strong>In this report</strong>${headings.map((h,i)=>btn(h[1],"report-heading",String(i))).join("")}</aside><article class="report-paper markdown">${renderMarkdown(selected.markdown)}</article></div>`;
}

function graphView() {
  const switcher=`<div class="report-tabs">${btn("People & events","graph-mode","case",state.graphMode!=="sources"?'aria-pressed="true"':"")}${btn("Advanced source relationships","graph-mode","sources",state.graphMode==="sources"?'aria-pressed="true"':"")}</div>`;
  return switcher+(state.graphMode==="sources"||!W.case_map?sourceGraphView():caseMapView());
}
function caseMapView() {
  const map=W.case_map, sources=new Set(visibleSources().map(s=>s.source_id));
  const candidates=map.nodes.filter(n=>n.source_ids.some(id=>sources.has(id)));
  const candidateIds=new Set(candidates.map(n=>n.id));
  let matching=map.edges.filter(r=>candidateIds.has(r.source)&&candidateIds.has(r.target)&&r.evidence_ids.every(id=>sources.has(evidenceById.get(id)?.source_id)));
  const selected=candidates.find(n=>n.id===state.mapSelection);
  const connected=new Set(selected?[selected.id,...matching.filter(r=>r.source===selected.id||r.target===selected.id).flatMap(r=>[r.source,r.target])]:[]);
  const prioritized=selected?[...matching.filter(r=>r.source===selected.id||r.target===selected.id),...matching.filter(r=>r.source!==selected.id&&r.target!==selected.id)]:matching;
  const limited=prioritized.slice(0,49), kept=new Set(limited.flatMap(r=>[r.source,r.target]));
  const nodes=candidates.filter(n=>kept.has(n.id)).slice(0,60), nodeIds=new Set(nodes.map(n=>n.id));
  const edges=limited.filter(r=>nodeIds.has(r.source)&&nodeIds.has(r.target));
  const columns=["correspondent","communication","financial_record","transaction"], positions=new Map();
  const groups=columns.map(kind=>nodes.filter(n=>n.kind===kind));
  const height=Math.max(360,Math.max(...groups.map(g=>g.length))*86+100);
  groups.forEach((group,col)=>group.forEach((n,row)=>positions.set(n.id,{x:25+col*255,y:65+row*86})));
  const labels=["Named correspondents","Communications","Financial records","References"];
  const svg=`<svg class="case-map" viewBox="0 0 1030 ${height}" aria-label="People and events graph with selectable source-backed nodes" role="group"><defs><marker id="map-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="#92aaa7"/></marker></defs>${labels.map((label,col)=>`<text class="column-label" x="${25+col*255}" y="26">${label}</text>`).join("")}${edges.filter(r=>nodeIds.has(r.source)&&nodeIds.has(r.target)).map(r=>{const a=positions.get(r.source),b=positions.get(r.target),right=b.x>=a.x;const x1=a.x+(right?215:0),x2=b.x+(right?0:215);return `<path class="map-edge ${selected?(r.source===selected.id||r.target===selected.id?"highlighted":"muted-edge"):""}" d="M${x1} ${a.y+26} C${(x1+x2)/2} ${a.y+26},${(x1+x2)/2} ${b.y+26},${x2} ${b.y+26}" marker-end="url(#map-arrow)"><title>${e(r.label)}</title></path>`;}).join("")}${nodes.map(n=>{const p=positions.get(n.id),label=n.label.length>27?n.label.slice(0,24)+"…":n.label;return `<g class="map-node ${n.kind} ${n.id===selected?.id?"active":""} ${selected&&!connected.has(n.id)?"muted-node":""}" data-action="map-node" data-id="${e(n.id)}" tabindex="0" role="button" aria-label="Inspect ${e(n.label)}"><title>${e(n.label)}${n.detail?' · '+e(n.detail):""}</title><rect x="${p.x}" y="${p.y}" width="215" height="56" rx="8"/><text x="${p.x+12}" y="${p.y+23}">${e(label)}</text><text class="node-detail" x="${p.x+12}" y="${p.y+42}">${e((n.detail||n.date?.slice(0,10)||n.kind.replaceAll("_"," ")).slice(0,32))}</text></g>`;}).join("")}</svg>`;
  return `<div class="page-intro"><div><span class="eyebrow">Evidence map</span><h2>People & events</h2><p>${e(map.definition)}</p></div>${selected?btn("Clear selection","map-node",""):""}</div><p class="graph-caption"><span class="legend-dot correspondent"></span> Named address <span class="legend-dot communication"></span> Email record <span class="legend-dot financial_record"></span> Financial record <span class="legend-dot transaction"></span> Reference</p>
    <div class="graph-workspace"><div class="map-scroll">${nodes.length?svg:empty("No source-backed connections match this scope. Reset filters to inspect the full authorized map.")}</div>

    <aside class="card node-inspector" aria-label="Selected graph item">${selected?`<span class="eyebrow">${e(selected.kind.replaceAll("_"," "))}</span><h3>${e(selected.label)}</h3><p>${e(selected.detail||selected.date||"Date unresolved")}</p><p>${e(selected.qualification)}</p><h4>Sources</h4><div class="actions">${evidenceButtons(selected.evidence_ids)}</div>`:'<h3>Inspect a person or event</h3><p>Select a node to see its sources and connections.</p>'}</aside></div>
    <details><summary>Graph coverage</summary><p>${nodes.length} nodes · ${edges.length} of ${matching.length} matching links shown (49-link display cap). ${map.omitted_communications} communications and ${map.omitted_financial_records} financial records omitted by projection limits. Dates describe records; ordering does not establish causation.</p></details>
    <details><summary>Inspect connections as a table</summary>${table(["From","Connection","To","Evidence"],edges.map(r=>[e(map.nodes.find(n=>n.id===r.source)?.label),e(r.label),e(map.nodes.find(n=>n.id===r.target)?.label),evidenceButtons(r.evidence_ids)]))}</details>`;
}
function readingChronology() {
  const sources=new Set(visibleSources().map(s=>s.source_id));
  const events=W.case_map.nodes.filter(n=>["communication","financial_record"].includes(n.kind)&&n.source_ids.some(id=>sources.has(id))).filter(n=>{const day=n.date?.slice(0,10);return (!state.from&&!state.to)||day&&(!state.from||day>=state.from)&&(!state.to||day<=state.to);}).sort((a,b)=>(a.date||"9999").localeCompare(b.date||"9999"));
  return `<div class="page-intro"><div><h2>Timeline</h2><p>Email dates and counsel-labelled financial events. Undated records stay unresolved; financial dates retain their annotation basis.</p></div>${btn("Open event graph","open-map")}</div><div class="timeline reading-timeline">${events.map(n=>`<article><span class="eyebrow">${e(n.date?.slice(0,10)||"Date unresolved")} · ${n.kind==="communication"?"Communication":"Financial record"}</span><h3>${e(n.label)}</h3><small>${e(n.date_label)}</small><p>${e(n.qualification)}</p>${evidenceButtons(n.evidence_ids)}</article>`).join("")||empty("No event records match this scope.")}</div><details><summary>Inspect transaction arithmetic</summary>${transactionReview()}</details>`;
}
document.addEventListener("click",event=>{
  const button=event.target.closest("[data-action]");if(!button)return;
  const {action,id}=button.dataset;
  if(action==="select-report")goto({reportId:id});
  else if(action==="download-report"){const report=W.reading_reports?.find(r=>r.id===id);if(report)download(report.filename,report.markdown,"text/markdown");}
  else if(action==="report-heading"){const heading=document.getElementById(`report-heading-${id}`);heading?.scrollIntoView({block:"start",behavior:"smooth"});}
  else if(action==="graph-mode")goto({graphMode:id,graphPaths:false});
  else if(action==="map-node")goto({mapSelection:state.mapSelection===id?"":id});
  else if(action==="open-map")goto({view:"People & relationships",graphMode:"case",mapSelection:id||""});
  else if(action==="reading-task"){
    const task=W.reading_tasks.find(t=>t.id===id);if(!task)return;
    const content=`${pills(task.status)}<p><strong>Record:</strong> ${e(task.record)}</p><p><strong>Decision it informs:</strong> ${e(task.purpose)}</p><p><strong>Closure test:</strong> ${e(task.closure)}</p><p>Owner: ${e(task.owner)}</p><p class="muted">${e(task.origin)}</p><div class="actions">${evidenceButtons(task.evidence_ids)}</div>`;
    reportUI.openInspector(task.title,content,button);
  }
});
document.addEventListener("keydown",event=>{
  if(["Enter"," "].includes(event.key)&&event.target.matches('.map-node')){event.preventDefault();event.target.dispatchEvent(new MouseEvent("click",{bubbles:true}));}
});
