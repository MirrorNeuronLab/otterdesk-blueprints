import { build } from "esbuild";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
const root = import.meta.dirname,
  output = path.resolve(root, "../payloads/domain/workspace_assets");
await build({
  entryPoints: ["src/main.tsx"],
  outfile: path.join(output, "report-shell.js"),
  bundle: true,
  minify: true,
  format: "iife",
  platform: "browser",
  target: "es2022",
  jsx: "transform",
  jsxFactory: "React.createElement",
  jsxFragment: "React.Fragment",
  define: { "process.env.NODE_ENV": '"production"' },
  legalComments: "inline",
});
const { createHash } = await import("node:crypto");
const sha = p => createHash("sha256").update(readFileSync(p)).digest("hex");
writeFileSync(path.join(output,"vendor/report-adapter-provenance.txt"),JSON.stringify({
 sources:Object.fromEntries(["src/main.tsx","build.mjs","package.json","package-lock.json"].map(name=>[name,sha(path.join(root,name))])),
 outputs:{"report-shell.js":sha(path.join(output,"report-shell.js"))},
},null,2)+"\n");
