import { build } from "esbuild";
import { readFile, writeFile } from "node:fs/promises";

// Keep dependency licenses with the executable even when the JS file is copied alone.
const options = {
    entryPoints: ["index.js"], bundle: true, platform: "browser", format: "esm",
    target: "chrome116", charset: "utf8", legalComments: "inline",
    write: false, metafile: true, logLevel: "warning"
};
const result = await build(options);
const packages = new Set();
for (const input of Object.keys(result.metafile.inputs)) {
    if (!input.startsWith("node_modules/")) continue;
    const [scope, name] = input.slice("node_modules/".length).split("/");
    packages.add(scope.startsWith("@") ? scope + "/" + name : scope);
}
const notices = new Map();
for (const name of [...packages].sort()) {
    const base = "node_modules/" + name;
    const metadata = JSON.parse(await readFile(base + "/package.json", "utf8"));
    const license = (await readFile(base + "/LICENSE", "utf8")).trim();
    if (metadata.license !== "MIT" || license.includes("*/"))
        throw new Error("Check the runtime license of " + name + " before bundling.");
    notices.set(license, [...(notices.get(license) || []), name + " " + metadata.version]);
}
const header = ["/*! Generated from website/browser-transport with npm run build.",
    ...[...notices].flatMap(([license, names]) => [names.join(", "), license]), "*/\n"].join("\n\n");
await writeFile("../assets/adb-transport.js", header + result.outputFiles[0].text);
