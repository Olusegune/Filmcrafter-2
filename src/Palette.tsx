import { useEffect, useMemo, useRef, useState } from "react";
import * as I from "./icons";
import "./palette.css";

export type Command = { id: string; label: string; hint?: string; keys?: string; run: () => void };
export type ShotRef = { id: string; start: number };

const MAX_SHOTS = 8;

/** The commands whose words contain every word typed, then the shots whose id contains it ("01-04", "s01", "shot 12"). Pure, so it can be tested. */
export function filterPalette(query: string, commands: Command[], shots: ShotRef[]): { commands: Command[]; shots: ShotRef[] } {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return { commands, shots: [] };
  const hay = (c: Command) => `${c.label} ${c.hint ?? ""} ${c.keys ?? ""}`.toLowerCase();
  // best first: a word that starts the label, then a word inside the label, then a word only in the hint or the key (the list keeps its own order among equals)
  const score = (c: Command) => words.reduce((n, w) => { const l = c.label.toLowerCase(); return n + (l.startsWith(w) || l.includes(` ${w}`) ? 0 : l.includes(w) ? 1 : 2); }, 0);
  const cmds = commands.map((c, i) => ({ c, i, s: score(c) })).filter(({ c }) => words.every((w) => hay(c).includes(w)))
    .sort((a, b) => a.s - b.s || a.i - b.i).map(({ c }) => c);
  const id = words.filter((w) => w !== "shot" && w !== "go" && w !== "to").join("");
  const found = id ? shots.filter((s) => s.id.toLowerCase().replace(/^s/, "").includes(id.replace(/^s/, ""))).slice(0, MAX_SHOTS) : [];
  return { commands: cmds, shots: found };
}

/** One search box for every action in the Studio and every shot (Ctrl+Shift+P). Up and down choose, Enter does it, Esc closes. */
export function Palette({ commands, shots, onShot, onClose }: { commands: Command[]; shots: ShotRef[]; onShot: (id: string) => void; onClose: () => void }) {
  const [q, setQ] = useState("");
  const [at, setAt] = useState(0);
  const box = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const hit = useMemo(() => filterPalette(q, commands, shots), [q, commands, shots]);
  const rows = useMemo(() => [
    ...hit.commands.map((c) => ({ key: c.id, label: c.label, hint: c.hint, keys: c.keys, run: c.run })),
    ...hit.shots.map((s) => ({ key: `shot-${s.id}`, label: `Go to shot ${s.id}`, hint: undefined, keys: undefined, run: () => onShot(s.id) })),
  ], [hit, onShot]);
  useEffect(() => { box.current?.focus(); }, []);
  useEffect(() => { setAt(0); }, [q]);
  useEffect(() => { list.current?.children[at]?.scrollIntoView({ block: "nearest" }); }, [at]);
  const go = (i: number) => { const r = rows[i]; if (!r) return; onClose(); window.setTimeout(r.run, 0); };
  const key = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") { e.preventDefault(); onClose(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); setAt((a) => Math.min(rows.length - 1, a + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setAt((a) => Math.max(0, a - 1)); }
    else if (e.key === "Enter") { e.preventDefault(); go(at); }
  };
  return (
    <div className="overlay palette-wrap" onClick={onClose}>
      <div className="palette glass" role="dialog" aria-label="Command palette" onClick={(e) => e.stopPropagation()} onKeyDown={key}>
        <div className="pl-search"><I.Search size={16} />
          <input ref={box} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Type what you want to do, or a shot number" aria-label="Search commands and shots"
                 role="combobox" aria-expanded="true" aria-controls="pl-list" aria-activedescendant={rows[at] ? `pl-${rows[at].key}` : undefined} /></div>
        <ul id="pl-list" className="pl-list" role="listbox" ref={list}>
          {rows.map((r, i) => (
            <li key={r.key} id={`pl-${r.key}`} role="option" aria-selected={i === at} className={i === at ? "on" : ""} onMouseMove={() => setAt(i)} onClick={() => go(i)}>
              <span className="pl-label">{r.label}</span>
              {r.hint && <span className="pl-hint">{r.hint}</span>}
              {r.keys && <kbd>{r.keys}</kbd>}
            </li>))}
          {!rows.length && <li className="pl-none" role="option" aria-selected="false">Nothing matches “{q}”.</li>}
        </ul>
        <div className="pl-foot"><kbd>↑</kbd><kbd>↓</kbd> choose <kbd>Enter</kbd> do it <kbd>Esc</kbd> close</div>
      </div>
    </div>
  );
}
