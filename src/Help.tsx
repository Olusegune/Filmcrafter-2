import { Fragment, useMemo, useRef, useState, type ReactNode } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import guide from "../docs/GETTING_STARTED.md?raw";
import * as I from "./icons";

// Screenshots live in docs/img and are written in the guide as ![what it shows](img/name.png), which GitHub shows too. The app bundles them (so they work offline).
const IMAGES = import.meta.glob("../docs/img/*.png", { eager: true, query: "?url", import: "default" }) as Record<string, string>;
export const docImage = (path: string): string | undefined => IMAGES[`../docs/${path}`];

/** Inline markdown: **bold**, *italic*, `code`. */
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g).filter(Boolean).map((t, i) =>
    t.startsWith("**") ? <b key={i}>{t.slice(2, -2)}</b>
      : t.startsWith("`") ? <code key={i}>{t.slice(1, -1)}</code>
        : t.startsWith("*") && t.length > 2 ? <em key={i}>{t.slice(1, -1)}</em> : <Fragment key={i}>{t}</Fragment>);
}

/** Small renderer for the guide's markdown (headings, paragraphs, lists, tables, rules). */
export function renderGuide(md: string): ReactNode[] {
  const out: ReactNode[] = [];
  let n = 0;                       // a running number for React's keys: line numbers could repeat (a table's end and the next block's start)
  const lines = md.split(/\r?\n/);
  let i = 0;
  while (i < lines.length) {
    const l = lines[i];
    if (!l.trim()) { i++; continue; }
    if (l.startsWith("---")) { out.push(<hr key={n++} />); i++; continue; }
    const img = l.match(/^!\[(.*)\]\((.+)\)\s*$/);
    if (img) {
      const src = docImage(img[2]);
      out.push(src ? <figure key={n++} className="guide-shot"><img src={src} alt={img[1]} loading="lazy" /><figcaption>{inline(img[1])}</figcaption></figure>
                   : <p key={n++}><em>{inline(img[1])}</em></p>);   // a picture that is missing never leaves a hole in the guide
      i++; continue;
    }
    const h = l.match(/^(#{1,3}) (.*)/);
    if (h) { const T = (["h1", "h2", "h3"] as const)[h[1].length - 1]; out.push(<T key={n++} id={h[1].length === 2 ? slug(h[2]) : undefined}>{inline(h[2])}</T>); i++; continue; }
    if (l.startsWith("|")) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].startsWith("|")) {
        if (!/^\|[\s|:-]+\|$/.test(lines[i])) rows.push(lines[i].slice(1, -1).split("|").map((c) => c.trim()));
        i++;
      }
      out.push(<table key={n++}><thead><tr>{rows[0].map((c, k) => <th key={k}>{inline(c)}</th>)}</tr></thead>
        <tbody>{rows.slice(1).map((r, k) => <tr key={k}>{r.map((c, n) => <td key={n}>{inline(c)}</td>)}</tr>)}</tbody></table>);
      continue;
    }
    if (/^(\d+\.|-) /.test(l)) {
      const ordered = /^\d+\./.test(l);
      const items: string[] = [];
      while (i < lines.length && /^(\d+\.|-) /.test(lines[i])) { items.push(lines[i].replace(/^(\d+\.|-) /, "")); i++; }
      const L = ordered ? "ol" : "ul";
      out.push(<L key={n++}>{items.map((t, k) => <li key={k}>{inline(t)}</li>)}</L>);
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(#|\||---|!\[|\d+\. |- )/.test(lines[i])) { para.push(lines[i]); i++; }
    out.push(<p key={n++}>{inline(para.join(" "))}</p>);
  }
  return out;
}

const slug = (t: string) => "doc-" + t.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const ONLINE = "https://github.com/Olusegune/Pulseframe-Music-Video-Maker/blob/main/docs/GETTING_STARTED.md";

/** The user guide, bundled with the app (works offline): contents, search, and a link to the online copy. */
export function HelpSheet({ onClose }: { onClose: () => void }) {
  const [q, setQ] = useState("");
  const body = useRef<HTMLElement>(null);
  const [intro, ...parts] = guide.split(/\r?\n(?=## )/);
  const sections = parts.map((p) => ({ title: p.split(/\r?\n/)[0].slice(3).trim(), md: p }));
  const shown = useMemo(() => {
    const t = q.trim().toLowerCase();
    return t ? sections.filter((s) => s.md.toLowerCase().includes(t)) : sections;
  }, [q]);   // eslint-disable-line react-hooks/exhaustive-deps
  const go = (title: string) => body.current?.querySelector("#" + slug(title))?.scrollIntoView({ behavior: "smooth", block: "start" });
  return (
    <div className="overlay" onClick={onClose} onKeyDown={(e) => e.key === "Escape" && onClose()}>
      <div className="sheet glass help-sheet docs-sheet" role="dialog" aria-label="Documentation" onClick={(e) => e.stopPropagation()}>
        <div className="docs-head">
          <h2>Documentation</h2>
          <input className="docs-search" type="search" placeholder="Search the guide" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search the guide" autoFocus />
          <button className="btn ghost sm" onClick={() => openUrl(ONLINE)} title="The same guide on GitHub">View online</button>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close /></button>
        </div>
        <div className="docs-body">
          <nav className="docs-toc" aria-label="Contents">
            {shown.map((s) => <button key={s.title} className="link" onClick={() => go(s.title)}>{s.title.replace(/^\d+\.\s*/, "")}</button>)}
          </nav>
          <article className="guide" ref={body}>
            {!q && renderGuide(intro)}
            {shown.length ? shown.map((s) => <Fragment key={s.title}>{renderGuide(s.md)}</Fragment>) : <p>Nothing in the guide matches "{q}".</p>}
          </article>
        </div>
      </div>
    </div>
  );
}
