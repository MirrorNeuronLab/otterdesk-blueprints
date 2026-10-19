// Domain-specific graph controls. The shared skill owns report chrome and primitives.
const shared = (window as any).MNWebReport;
const { React, flushSync, mount, convert, Tip } = shared;
const { memo, useSyncExternalStore } = React;
const {
  Button,
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  Popover,
  PopoverTrigger,
  PopoverContent,
  NativeSelect,
} = shared.components;
const {
  ChevronDown,
  ArrowLeft,
  ArrowRight,
  Play,
  Pause,
  Plus,
  Minus,
  Maximize,
  Focus,
  ScanSearch,
} = shared.icons;
const $ = (id: string) => document.getElementById(id)!;
const notify = (type: string, detail: any) =>
  document.dispatchEvent(new CustomEvent("report:" + type, { detail }));
let state = {
  view: "overview",
  more: false,
  popup: null as string | null,
  inspector: false,
  title: "Selection evidence",
  playing: false,
  ready: false,
  graph: true,
  network: true,
  evolution: false,
  changeEnabled: false,
  changeNote: "",
};
const listeners = new Set<() => void>();
function update(patch: Partial<typeof state>) {
  if (
    Object.entries(patch).every(
      ([k, v]) => state[k as keyof typeof state] === v,
    )
  )
    return;
  state = { ...state, ...patch };
  flushSync(() => listeners.forEach((fn) => fn()));
}
const subscribe = (fn: () => void) => {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
};
const useState = () => useSyncExternalStore(subscribe, () => state);
const tabRows = [
  ["overview", "Overview", "overview"],
  ["map", "Dependency graph", "explore"],
  ["timeline", "Graph evolution", "explore"],
  ["review", "Recommended prompts", "review"],
  ["matrix", "Dependency matrix", "explore"],
  ["paths", "Call paths", "explore"],
  ["impact", "Change impact", "explore"],
  ["coupling", "Changes together", "explore"],
  ["treemap", "Size and churn", "explore"],
  ["score", "Architecture score", "score-panel"],
  ["evidence", "Evidence coverage", "evidence"],
];
const fieldNodes = [...document.querySelector(".toolbar")!.children]
  .filter((n) => n.tagName === "LABEL")
  .map((n, i) => convert(n, i));
const optionNodes = [
  ...document.querySelector(".filters [data-menu-items]")!.children,
].map((n, i) => convert(n, i));
const Fields = memo(() => <>{fieldNodes}</>);
const OptionsFields = memo(() => <>{optionNodes}</>);
function Toolbar() {
  const s = useState();
  return (
    <>
      <Fields />
      <div className="filters">
        <Popover
          open={s.popup === "options"}
          onOpenChange={(open) => {
            if (open || state.popup === "options")
              update({ popup: open ? "options" : null });
            if (open) {
              document
                .querySelector<HTMLSelectElement>(
                  ".report-options label:not([hidden]) select",
                )
                ?.focus();
            }
          }}
        >
          <PopoverTrigger asChild>
            <Button id="options-trigger" variant="outline" size="sm">
              Options
              <ChevronDown aria-hidden="true" />
            </Button>
          </PopoverTrigger>
          <PopoverContent
            forceMount
            hidden={s.popup !== "options"}
            align="end"
            className="report-options"
            onOpenAutoFocus={(e) => e.preventDefault()}
            onEscapeKeyDown={(e) => {
              e.stopPropagation();
              $("options-trigger").focus();
            }}
          >
            <OptionsFields />
          </PopoverContent>
        </Popover>
      </div>
    </>
  );
}
const commands = [
  ["zoom-in", "Zoom in", Plus],
  ["zoom-out", "Zoom out", Minus],
  ["zoom-reset", "Fit visible graph", Maximize],
  ["zoom-focus", "Focus selected", Focus],
  ["zoom-changes", "Zoom to changes", ScanSearch],
] as const;
let graphCommands: Record<string, () => void> = {};
function GraphActions() {
  const s = useState();
  return (
    <div className="graph-actions" hidden={!s.graph}>
      <DropdownMenu
        modal={false}
        open={s.popup === "graph"}
        onOpenChange={(open) => {
          if (open || state.popup === "graph")
            update({ popup: open ? "graph" : null });
        }}
      >
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm">
            Graph actions
            <ChevronDown aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          align="end"
          className="report-component-menu"
          onEscapeKeyDown={(e) => e.stopPropagation()}
        >
          {commands
            .filter(([id]) =>
              id === "zoom-changes"
                ? s.evolution
                : id === "zoom-focus"
                  ? s.network
                  : true,
            )
            .map(([id, label, Icon]) => (
              <DropdownMenuItem
                key={id}
                id={id}
                disabled={id === "zoom-changes" && !s.changeEnabled}
                onSelect={() => graphCommands[id]?.()}
              >
                <Icon aria-hidden="true" />
                {label}
              </DropdownMenuItem>
            ))}
          {s.evolution && s.changeNote && (
            <p id="change-zoom-note" className="qualification px-2 py-1">
              {s.changeNote}
            </p>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
function Playback() {
  const s = useState();
  return (
    <div className="report-playback">
      <Tip label="Previous commit">
        <Button
          id="previous"
          aria-label="Previous commit"
          variant="outline"
          size="icon-sm"
        >
          <ArrowLeft aria-hidden="true" />
        </Button>
      </Tip>
      <Button id="play" variant="outline" size="sm">
        {s.playing ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
        {s.playing ? "Pause" : "Play"}
      </Button>
      <Tip label="Next commit">
        <Button
          id="next"
          aria-label="Next commit"
          variant="outline"
          size="icon-sm"
        >
          <ArrowRight aria-hidden="true" />
        </Button>
      </Tip>
    </div>
  );
}
const shell = shared.createReport({
  tabs: tabRows,
  view: "overview",
  navigationLabel: "Architecture results",
  actions: [
    {
      id: "export",
      label: "Export report",
      href: $("report-actions").getAttribute("data-report-href"),
      icon: "download",
    },
    {
      id: "details",
      label: "Report details",
      icon: "info",
      requiresReady: true,
    },
  ],
  inspector: {
    panelId: "graph-inspector",
    titleId: "inspector-title",
    contentId: "inspector-content",
    description:
      "Saved evidence and source references for the selected observation, file or function.",
  },
  onView: (view) => notify("view", { view }),
  onAction: (_id, trigger) => notify("panel", { kind: "report", trigger }),
  onDismiss: () => notify("dismiss", {}),
});
const toolbar = document.querySelector(".toolbar")!;
mount(toolbar, <Toolbar />);
const baseline = $("baseline"),
  baselineHost = document.createElement("span");
baselineHost.className = "report-button-mount";
baseline.replaceWith(baselineHost);
mount(baselineHost, <NativeSelect id="baseline" />);
const graphActions = document.querySelector(".graph-actions")!,
  graphHost = document.createElement("span");
graphHost.className = "report-button-mount";
graphActions.replaceWith(graphHost);
mount(graphHost, <GraphActions />);
const transport = $("previous"),
  playHost = document.createElement("span");
playHost.className = "report-button-mount";
transport.before(playHost);
for (const id of ["previous", "play", "next"]) $(id).remove();
mount(playHost, <Playback />);
const api = {
  ...shell,
  setView(view: string) {
    shell.setView(view);
  },
  closeDisclosures() {
    update({ popup: null });
    shell.closeDisclosures();
  },
  setInspectorOpen(inspector: boolean) {
    shell.setInspectorOpen(inspector);
  },
  setInspectorTitle(title: string) {
    shell.setInspectorTitle(title);
  },
  setPlaying(playing: boolean) {
    update({ playing });
  },
  setGraphVisible(graph: boolean) {
    update({ graph });
  },
  setGraphMode(network: boolean, evolution: boolean) {
    update(
      network !== state.network || evolution !== state.evolution
        ? { network, evolution, changeNote: "" }
        : { network, evolution },
    );
  },
  setGraphChanges(changeEnabled: boolean, changeNote: string) {
    update({ changeEnabled, changeNote });
  },
  bindGraphCommands(commands: Record<string, () => void>) {
    graphCommands = commands;
  },
  ready() {
    shell.ready();
  },
};
Object.assign(window, { ReportUI: api });
