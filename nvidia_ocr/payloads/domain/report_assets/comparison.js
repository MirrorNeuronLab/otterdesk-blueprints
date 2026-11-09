/* Read-only projection of committed OCR; source text always enters through textContent. */
(() => {
  "use strict";
  const data = JSON.parse(document.getElementById("report-data").textContent);
  const record = data.document;
  const byId = (id) => document.getElementById(id);
  const svgNS = "http://www.w3.org/2000/svg";
  let pageIndex = 0;

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function showView(view) {
    byId("comparison-view").hidden = view !== "compare";
    byId("files-view").hidden = view !== "files";
  }
  function showDetails(trigger) {
    const details = element("dl");
    const values = [
      ["Source file", record.source],
      ["Status", record.status],
      ["Source SHA-256", record.source_sha256],
      ["OCR input SHA-256", record.input_sha256],
      ["Model revision", record.model_revision],
      [
        "Page preparation",
        record.converted
          ? "Rendered from the Office document for OCR."
          : "Original document.",
      ],
      [
        "Model warnings",
        (record.warnings || []).join("\n") || "None reported.",
      ],
    ];
    for (const [label, value] of values)
      if (value) details.append(element("dt", label), element("dd", value));
    const note = element(
      "p",
      "Confidence is a model score, not a guarantee that text is correct.",
    );
    shell.openInspector(
      "Document details",
      details.outerHTML + note.outerHTML,
      trigger,
    );
  }
  const actions = [
    {
      id: "original",
      label: "Download original",
      icon: "download",
    },
  ];
  if (record.text_url)
    actions.push({
      id: "text",
      label: "Download text",
      icon: "download",
    });
  if (record.json_url)
    actions.push({
      id: "json",
      label: "Download page data",
      icon: "download",
    });
  actions.push({ id: "details", label: "Document details", icon: "info" });
  const shell = MNWebReport.createReport({
    tabs: [
      ["compare", "Compare", "comparison-view"],
      ["files", "Files", "files-view"],
    ],
    view: "compare",
    actions,
    onView: showView,
    onAction: (id, trigger) => {
      if (id === "details") showDetails(trigger);
      else {
        const downloads = {
          original: [record.original, record.source.split("/").pop()],
          text: [record.text_url, "text.txt"],
          json: [record.json_url, "ocr_result.json"],
        };
        const [href, name] = downloads[id];
        const link = element("a");
        link.href = href;
        link.download = name;
        document.body.append(link);
        link.click();
        link.remove();
      }
    },
  });

  for (const file of data.files.filter((file) => file.page)) {
    const option = element("option", file.source);
    option.value = file.page;
    option.selected = file.source === record.source;
    byId("document-select").append(option);
  }
  byId("original-link").href = record.original;
  byId("original-link").download = record.source.split("/").pop();
  byId("document-note").textContent =
    record.preview_note ||
    (record.converted
      ? "Office pages are rendered as they were sent to OCR. Download the original to review its full content."
      : "Select a text region to compare it with the extracted text.");
  if (record.error) {
    byId("document-error").textContent =
      "Couldn't read this document. " + record.error;
    byId("document-error").hidden = false;
  }
  for (const [index, page] of record.pages.entries()) {
    const option = element(
      "option",
      `${page.page_number} of ${record.pages.length}`,
    );
    option.value = index;
    byId("page-select").append(option);
  }
  const counts = data.summary;
  byId("batch-counts").textContent =
    `${counts.completed_count} completed · ${counts.failed_count} failed · ${counts.skipped_count} skipped`;
  function showFiles() {
    const query = byId("file-search").value.toLocaleLowerCase();
    const fragment = document.createDocumentFragment();
    for (const file of data.files.filter((file) =>
      file.source.toLocaleLowerCase().includes(query),
    )) {
      const row = element(file.page ? "a" : "div", undefined, "file-row");
      if (file.page) row.href = file.page;
      row.append(
        element("span", file.source, "file-name"),
        element(
          "span",
          {
            completed: "Completed",
            failed: "Failed",
            skipped: "Unsupported format",
          }[file.status],
          "file-status",
        ),
      );
      fragment.append(row);
    }
    byId("file-empty").hidden = fragment.childElementCount > 0;
    byId("file-list").replaceChildren(fragment);
  }
  function setResultView() {
    const regions = byId("result-view").value === "regions";
    byId("page-text").hidden = regions;
    byId("region-list").hidden = !regions;
  }
  function selectRegion(index, fromPreview) {
    document.querySelectorAll("[data-region]").forEach((node) => {
      node.dataset.selected = String(node.dataset.region === String(index));
      node.setAttribute("aria-pressed", node.dataset.selected);
    });
    byId("show-regions").checked = true;
    byId("page-preview").classList.add("show-regions");
    if (fromPreview) {
      byId("result-view").value = "regions";
      setResultView();
      byId("region-list").children[index]?.scrollIntoView({ block: "nearest" });
    } else {
      byId("page-preview")
        .querySelector(`[data-region="${index}"]`)
        ?.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  }
  function showPage(index) {
    pageIndex = Math.max(0, Math.min(index, record.pages.length - 1));
    const page = record.pages[pageIndex];
    const svg = byId("page-preview");
    svg.replaceChildren();
    svg.toggleAttribute("hidden", !page?.preview);
    byId("preview-empty").hidden = !!page?.preview;
    byId("copy-text").disabled = !page?.text;
    byId("page-select").disabled = !page;
    byId("previous-page").disabled = pageIndex === 0;
    byId("next-page").disabled = pageIndex >= record.pages.length - 1;
    byId("page-select").value = String(pageIndex);
    byId("copy-status").textContent = "";
    byId("page-text").textContent = page?.text || "";
    byId("text-empty").hidden = !!page?.text || record.status === "failed";
    byId("page-stats").textContent = page
      ? `${page.regions.length} text regions`
      : "No OCR result";
    byId("region-list").replaceChildren();
    if (page) {
      svg.setAttribute("viewBox", `0 0 ${page.width} ${page.height}`);
      svg.setAttribute("aria-label", `Original page ${page.page_number}`);
      if (page.preview) {
        const image = document.createElementNS(svgNS, "image");
        image.setAttribute("width", page.width);
        image.setAttribute("height", page.height);
        image.setAttribute("href", page.preview);
        image.addEventListener("error", () => {
          svg.setAttribute("hidden", "");
          byId("preview-empty").hidden = false;
        });
        svg.append(image);
      }
      const rows = document.createDocumentFragment();
      for (const [index, region] of page.regions.entries()) {
        const rect = document.createElementNS(svgNS, "rect");
        const [left, top, right, bottom] = region.bbox;
        for (const [key, value] of Object.entries({
          x: left * page.width,
          y: top * page.height,
          width: (right - left) * page.width,
          height: (bottom - top) * page.height,
          class: "region-box",
          tabindex: "0",
          role: "button",
          "aria-pressed": "false",
          "aria-label": `Region ${index + 1}: ${region.text.slice(0, 160)}`,
        }))
          rect.setAttribute(key, value);
        rect.dataset.region = index;
        svg.append(rect);
        const row = element("button", region.text);
        row.type = "button";
        row.setAttribute("aria-pressed", "false");
        row.dataset.region = index;
        row.setAttribute(
          "aria-label",
          `Region ${index + 1}: ${region.text.slice(0, 160)}`,
        );
        row.append(
          element(
            "small",
            `Region ${index + 1} · Confidence ${(region.confidence * 100).toFixed(1)}%`,
          ),
        );
        rows.append(row);
      }
      byId("region-list").append(rows);
    }
    byId("preview-scroll").scrollTop = byId("result-scroll").scrollTop = 0;
    setResultView();
  }
  async function copyText() {
    try {
      await navigator.clipboard.writeText(record.pages[pageIndex].text);
      byId("copy-status").textContent = "Page text copied.";
    } catch {
      byId("result-view").value = "text";
      setResultView();
      const range = document.createRange();
      range.selectNodeContents(byId("page-text"));
      const selection = getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      byId("copy-status").textContent =
        "Couldn't copy automatically. The text is selected; use your browser's Copy command.";
    }
  }
  document.addEventListener("click", (event) => {
    const region = event.target.closest("[data-region]");
    if (region)
      selectRegion(Number(region.dataset.region), !!region.closest("svg"));
    const button = event.target.closest("button");
    if (button?.id === "previous-page") showPage(pageIndex - 1);
    if (button?.id === "next-page") showPage(pageIndex + 1);
    if (button?.id === "copy-text") void copyText();
  });
  document.addEventListener("keydown", (event) => {
    if (
      event.target.matches("rect[data-region]") &&
      ["Enter", " "].includes(event.key)
    ) {
      event.preventDefault();
      selectRegion(Number(event.target.dataset.region), true);
    }
  });
  document.addEventListener("change", (event) => {
    const target = event.target;
    if (target.id === "document-select") location.href = target.value;
    if (target.id === "page-select") showPage(Number(target.value));
    if (target.id === "result-view") setResultView();
    if (target.id === "zoom") byId("page-preview").dataset.zoom = target.value;
    if (target.id === "show-regions")
      byId("page-preview").classList.toggle("show-regions", target.checked);
  });
  document.addEventListener("input", (event) => {
    if (event.target.id === "file-search") showFiles();
  });
  // Upgrade static controls before inserting the potentially large region list.
  shell.enhance(byId("report-main"));
  showFiles();
  showPage(0);
  shell.ready(true);
})();
