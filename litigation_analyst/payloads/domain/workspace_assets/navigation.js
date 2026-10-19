/* Presentation groups retain the original routes used by bookmarks and saved views. */
const primaryNavigation = [
  {label:"Overview", routes:["Overview"]},
  {label:"Findings", routes:["Findings"]},
  {label:"Questions", routes:["Issues & evidence"]},
  {label:"Evidence", routes:["Evidence Explorer", "Comparisons"]},
  {label:"People & events", routes:["People & relationships"]},
  {label:"Timeline", routes:["Chronology"]},
  {label:"Reports", routes:["Reports", "Work product"]},
  {label:"Review history", routes:["Activity & audit", "Since last review"]}
];
let unsavedReviews = false;
let unsavedViews = false;
let copyRequested = false;
let reportUI;

function initializeReport() {
  reportUI = MNWebReport.createReport({
    tabs: [...primaryNavigation.map(group=>[group.routes[0],group.label,"content"]),["Matter settings","Matter settings","content"]],
    view: navigationGroup(state.view)?.routes[0]||"Matter settings",
    navigationLabel: "Investigation views",
    actions: [
      {id:"save-copy",label:"Save copy",icon:"download"},
      {id:"download-report",label:"Download report Markdown",icon:"download"},
      {id:"source-appendix",label:"Download source appendix",icon:"download"},
      {id:"save-reviews",label:"Export review decisions",icon:"download"},
      {id:"details",label:"Report details",icon:"info"},
    ],
    inspector: {contentId:"source-dialog",description:"Authorized source passages, context and qualifications for this matter."},
    onView: view=>goto({view,finding:null,source:null}),
    onAction(action,trigger) {
      if(action==="details") {
        reportUI.openInspector("Report details",`<p>${e(W.analysis.status)}</p><p>${e(W.analysis.scope)}</p><details><summary>Source identity</summary><p>Snapshot: ${e(W.snapshot_id)}</p><p>${e(W.coverage.definition||"Frozen authorized scope")}</p></details>`,trigger);
      } else if(action==="source-appendix"||action==="download-report") {
        const report=W.reading_reports?.find(r=>r.id===(action==="source-appendix"?"source-passages":state.reportId))||
          (action==="download-report"?W.reading_reports?.[0]:null);
        if(report)download(report.filename,report.markdown,"text/markdown");
        else notice("This report is not included in the saved scope.");
      }
      else performAction(action,"",trigger);
    },
    onDismiss() {if(state.source)goto({source:null});},
  });
  reportUI.ready();
}

function navigationGroup(route) {
  return primaryNavigation.find(group=>group.routes.includes(route));
}
function navigationView() {
  const active=navigationGroup(state.view);
  return `<nav aria-label="Investigation views"><p class="nav-label">Matter workspace</p><div class="primary-navigation">${primaryNavigation.map(group=>btn(group.label,"view",group.routes[0],`data-primary-view="true" ${group===active?'aria-current="page"':""}`)).join("")}</div><div class="nav-footer">${btn("Matter settings","view","Matter settings",state.view==="Matter settings"?'aria-current="page"':"")}<small>Local investigation</small></div></nav>`;
}
function routeTabs(items) {
  return `<div class="route-tabs">${items.map(([label,route])=>btn(label,"view",route,state.view===route?'aria-pressed="true"':"")).join("")}</div>`;
}
function reportTabs() {
  return routeTabs([["Read reports","Reports"],["Reviewed briefing","Work product"]]);
}
function historyTabs() {
  return routeTabs([["Review decisions","Activity & audit"],["Changes","Since last review"]]);
}
function needsReview(finding) {
  return !["Reviewed with qualification","Revised","Dismissed"].includes(currentReview(finding).review_state);
}
function reviewAttentionCount() {
  return new Set([...(W.reading_review?.withheld_finding_ids||[]),
    ...visibleFindings().filter(needsReview).map(f=>f.id)]).size;
}
function eligibleBriefing() {
  return visibleFindings().map(currentReview).filter(f=>["Reviewed with qualification","Revised"].includes(f.review_state));
}
function primaryAction() {
  const pending=reviewAttentionCount(), route=pending?"Findings":"Reports";
  if(state.view===route)return "";
  return btn(pending?"Review findings":"Read report","view",route,'class="primary"');
}
function exportMenu() {
  const reports=W.reading_reports||[], current=reports.find(r=>r.id===state.reportId)||reports[0];
  return `<details class="export-menu"><summary>Export</summary><div class="export-options" role="group" aria-label="Export options">${btn("Save copy","save-copy")}${current?btn("Download report Markdown","download-report",current.id):""}${reports.some(r=>r.id==="source-passages")?btn("Download source appendix","download-report","source-passages"):""}${btn("Export review decisions","save-reviews")}</div></details>`;
}
function markUnsaved(kind) {
  if(kind==="review")unsavedReviews=true;
  if(kind==="view")unsavedViews=true;
  copyRequested=false;
}
function unsavedReminder() {
  if(!unsavedReviews&&!unsavedViews)return "";
  const message=copyRequested?"Copy download requested. Check the saved file before closing.":
    unsavedReviews?"Unsaved review changes. Save a copy to keep them.":"Unsaved view changes. Save a copy to keep them.";
  return `<div class="unsaved-reminder" role="status"><span>${e(message)}</span>${btn("Save copy","save-copy")}</div>`;
}
function briefingReadiness() {
  const count=eligibleBriefing().length, canExport=count>0&&!state.supportingOnly;
  return `<section class="briefing-readiness"><div><strong>${count} reviewed finding${count===1?"":"s"} eligible for briefing</strong><p>${state.supportingOnly?"Restore counterevidence before creating a briefing.":count?"Includes reviewed wording, supporting sources and counterevidence.":"Review findings before creating a briefing. Flagged claims remain excluded."}</p></div>${canExport?btn("Create briefing","export-preview","",'class="primary"'):btn("Review findings","view","Findings")}</section>`;
}
function documentTitle(source) {
  return W.temporal.events.find(event=>event.source_ids.includes(source.source_id))?.title||source.relative_path;
}
function documentDate(source) {
  const event=W.temporal.events.find(event=>event.source_ids.includes(source.source_id));
  return event?.time.earliest?`<span title="${e(event.display)}">${e(event.time.earliest.slice(0,10))}<small>UTC · Email date</small></span>`:
    '<span class="muted">Not indexed</span>';
}
function documentType(source) {
  return ({"message/rfc822":"Email","text/csv":"CSV","text/plain":"Text","application/pdf":"PDF",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document":"Word document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":"Spreadsheet"})[source.media_type]||source.media_type;
}
function documentList(sources) {
  if(!sources.length)return empty(W.sources.length?"No documents match these filters. Reset filters to see all available documents.":"No documents are included in this investigation.");
  return `<div class="document-table">${table(["Document","Date","Type","Inspect"],sources.map(source=>[
    `<span class="document-title" title="${e(documentTitle(source))}">${e(documentTitle(source))}</span><details class="document-details"><summary>Document details</summary><dl><dt>File name</dt><dd>${e(source.relative_path)}</dd><dt>Source</dt><dd>${e(source.source_id)}</dd><dt>Normalized SHA-256</dt><dd>${e(source.content_sha256)}</dd><dt>Processing</dt><dd>${e(source.extraction_status)}</dd></dl></details>`,
    documentDate(source),e(documentType(source)),
    `${btn("View source","source",source.source_id)}${btn("Compare sources","add-comparison",source.source_id)}`]))}</div>`;
}
function nextSteps(limit) {
  const tasks=W.reading_tasks||[];
  return tasks.slice(0,limit??tasks.length).map((task,index)=>`<div class="next-item"><span class="step-number">${index+1}</span><div>${btn(task.title,"reading-task",task.id)}<small>${e(task.status)} · ${e(task.owner)}</small></div></div>`).join("");
}
document.addEventListener("submit",event=>{
  if(event.target.id!=="document-search")return;
  event.preventDefault();
  goto({query:document.getElementById("document-query").value});
});
