import { Fragment, memo, type ReactNode } from "react";

/** Small, safe Markdown renderer for copilot answers: paragraphs, bullet and numbered
 *  lists, tables, headings, **bold**, *italic* and `code`. Builds React elements, never
 *  injects HTML, so model output cannot run script in the page. */
function inline(text: string, key: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g;
  let last = 0, m: RegExpExecArray | null, i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const t = m[0];
    if (t.startsWith("**")) out.push(<strong key={`${key}-${i++}`} className="font-semibold">{t.slice(2, -2)}</strong>);
    else if (t.startsWith("`")) out.push(<code key={`${key}-${i++}`} className="num rounded bg-raised px-1 py-px text-[12px]">{t.slice(1, -1)}</code>);
    else out.push(<em key={`${key}-${i++}`}>{t.slice(1, -1)}</em>);
    last = m.index + t.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const cells = (row: string) => row.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

export const Markdown = memo(function Markdown({ text }: { text: string }) {
  const lines = text.replace(/\r/g, "").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0, k = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    if (line.trim().startsWith("|") && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      const head = cells(line);
      const align = cells(lines[i + 1]).map((c) => (c.endsWith(":") ? "right" : "left"));
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].trim().startsWith("|")) rows.push(cells(lines[i++]));
      blocks.push(
        <div key={k++} className="-mx-1 overflow-x-auto" data-lenis-prevent>
          <table className="w-full min-w-max text-[12.5px]">
            <thead><tr className="border-b text-left text-muted-foreground">
              {head.map((h, j) => <th key={j} className={`px-1 py-1 font-medium ${align[j] === "right" ? "text-right" : ""}`}>{inline(h, `h${j}`)}</th>)}
            </tr></thead>
            <tbody>{rows.map((r, ri) => (
              <tr key={ri} className="border-b border-border/50">
                {r.map((c, j) => <td key={j} className={`px-1 py-1 ${align[j] === "right" ? "num text-right" : ""}`}>{inline(c, `c${ri}-${j}`)}</td>)}
              </tr>))}
            </tbody>
          </table>
        </div>);
      continue;
    }
    if (/^\s*([-*•]|\d+\.)\s+/.test(line)) {
      const ordered = /^\s*\d+\./.test(line);
      const items: string[] = [];
      while (i < lines.length && /^\s*([-*•]|\d+\.)\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*([-*•]|\d+\.)\s+/, ""));
      const L = ordered ? "ol" : "ul";
      blocks.push(<L key={k++} className={`space-y-1 pl-4 ${ordered ? "list-decimal" : "list-disc"} marker:text-faint`}>
        {items.map((it, j) => <li key={j}>{inline(it, `l${k}-${j}`)}</li>)}</L>);
      continue;
    }
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) { blocks.push(<p key={k++} className="font-semibold">{inline(h[2], `hd${k}`)}</p>); i++; continue; }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^\s*([-*•]|\d+\.)\s+/.test(lines[i]) && !lines[i].trim().startsWith("|")) para.push(lines[i++]);
    blocks.push(<p key={k++}>{para.map((p, j) => <Fragment key={j}>{j > 0 && <br />}{inline(p, `p${k}-${j}`)}</Fragment>)}</p>);
  }
  return <div className="space-y-2.5 text-[13.5px] leading-relaxed">{blocks}</div>;
});
