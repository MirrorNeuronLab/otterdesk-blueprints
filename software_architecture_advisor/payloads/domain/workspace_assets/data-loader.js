"use strict";
// Same-origin HTTP loading and an explicit offline file selection mode.
// Repository JSON is data only: never evaluated or inserted as HTML.
window.loadArchitectureData = function (names, render, options = {}) {
  const optional = new Set(options.optional || []);
  const allNames = [...names, ...optional];
  const root = document.querySelector('meta[name="data-root"]').content;
  const panel = document.getElementById("load-data");
  const status = document.getElementById("load-status");
  const picker = document.getElementById("data-files");
  const maxBytes = 100 * 1024 * 1024;
  const accept = (values) => {
    render(values);
    panel.hidden = true;
    document.getElementById("content").hidden = false;
  };
  picker.addEventListener("change", async () => {
    try {
      const files = [...picker.files];
      if (files.reduce((n, f) => n + f.size, 0) > maxBytes)
        throw new Error("Selected data exceeds 100 MB.");
      const data = {};
      for (const name of allNames) {
        const matches = files.filter((f) => f.name === name);
        if (!matches.length && optional.has(name)) continue;
        if (matches.length !== 1)
          throw new Error(
            "Select exactly one " +
              name +
              " along with the other listed files.",
          );
        data[name] = JSON.parse(await matches[0].text());
      }
      accept(data);
    } catch (error) {
      status.textContent = "Couldn’t open the report data. " + error.message;
      panel.hidden = false;
    }
  });
  status.textContent =
    "Open " +
    names.join(", ") +
    " from the data folder. The files stay in this browser.";
  if (location.protocol === "file:") return;
  Promise.all(
    allNames.map(async (name) => {
      const response = await fetch(root + "/" + name, {
        credentials: "same-origin",
      });
      if (response.status === 404 && optional.has(name)) return null;
      if (!response.ok) throw new Error(name + " could not be read.");
      const body = await response.text();
      if (body.length > maxBytes)
        throw new Error("Report data exceeds 100 MB.");
      return [name, JSON.parse(body)];
    }),
  )
    .then((rows) => accept(Object.fromEntries(rows.filter(Boolean))))
    .catch((error) => {
      status.textContent =
        "Couldn’t load report data. " +
        error.message +
        " You can select the listed data files below.";
      panel.hidden = false;
    });
};
