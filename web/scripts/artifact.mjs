// Turns dist-demo/index.html into page content for an Artifact (the host adds its own
// doctype/html/head/body skeleton): keeps <title>, the theme bootstrap, styles and scripts.
import { readFileSync, writeFileSync } from "node:fs";
const html = readFileSync(new URL("../dist-demo/index.html", import.meta.url), "utf8");
const head = html.slice(html.indexOf("<head>") + 6, html.indexOf("</head>"));
const body = html.slice(html.indexOf("<body>") + 6, html.lastIndexOf("</body>"));
const keep = head.replace(/<meta[^>]*>/g, "").replace(/<link rel="icon"[^>]*>/g, "");
const title = keep.match(/<title>.*?<\/title>/)[0];
const out = `${title}\n${keep.replace(title, "")}\n${body}`;
writeFileSync(new URL("../dist-demo/gridsetu-control-room.html", import.meta.url), out);
console.log(`artifact page: ${(out.length / 1e6).toFixed(2)} MB`);
