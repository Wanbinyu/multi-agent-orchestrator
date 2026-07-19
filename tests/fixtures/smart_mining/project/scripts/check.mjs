import { access, readFile } from "node:fs/promises";

const routes = [
  "overview", "monitor", "alerts", "devices",
  "architecture", "events", "timeline",
];

for (const route of routes) {
  await access(new URL(`../src/pages/${route}.js`, import.meta.url));
}
const entry = await readFile(new URL("../src/main.js", import.meta.url), "utf8");
for (const route of routes) {
  if (!entry.includes(`./pages/${route}.js`)) {
    throw new Error(`missing route import: ${route}`);
  }
}
const html = await readFile(new URL("../index.html", import.meta.url), "utf8");
for (const marker of ["#login", "canvas", "Mock data ready"]) {
  if (!html.includes(marker)) throw new Error(`missing runtime marker: ${marker}`);
}
console.log(`${process.argv[2] || "check"} passed: ${routes.length} routes`);
