import { useMemo } from "react";
import type { Manifest, ManifestInput } from "./api";
import { ASPECTS, QUALITY, sentShape, shapeDiffers } from "./frame";
import { Pill } from "./Dock";
import * as I from "./icons";

/**
 * The few choices that decide how a picture or clip comes out (shape, resolution, detail, length), right beside the button that makes
 * it, so nothing has to be scrolled to. Shape and resolution are the project's; the rest belong to the chosen model and start on Auto.
 */
export function FormatRow({ manifest, auto, pins, setPins, frame, quality, onFrame, kind }: {
  manifest: Manifest | null; auto: Record<string, unknown>; pins: Record<string, unknown>; setPins: (p: Record<string, unknown>) => void;
  frame: string; quality: string; onFrame: (key: "aspect_ratio" | "quality", value: string) => void; kind: "image" | "video";
}) {
  const roleOf = useMemo(() => Object.fromEntries(Object.entries(manifest?.roles ?? {}).map(([r, f]) => [f, r])), [manifest]);
  const own = (manifest?.inputs ?? []).filter((f: ManifestInput) => {
    const r = roleOf[f.name];
    if (kind === "image" && r === "duration") return false;
    return (r === "duration" || r === "resolution" || f.name === "quality") && (f.enum?.length || f.type === "integer" || f.type === "number");
  });
  const set = (name: string, raw: string, f: ManifestInput) => {
    const next = { ...pins };
    if (raw === "") delete next[name];
    else next[name] = f.enum?.length ? f.enum.find((x) => String(x) === raw) : Number(raw);
    setPins(next);
  };
  const shape = sentShape(manifest, { ...auto, ...pins });
  const differs = shapeDiffers(shape, frame);
  const label = (name: string, r?: string) => (r === "duration" ? "Length" : r === "resolution" ? "Resolution" : name === "quality" ? "Detail" : name);
  return (
    <div className="fmt-row">
      <label className="fmt-f"><span><I.FrameSize size={13} /> Shape</span>
        <select value={frame} onChange={(e) => onFrame("aspect_ratio", e.target.value)} aria-label="Shape of the frame">
          {ASPECTS.map(([v, l]) => <option key={v} value={v}>{v} · {l.split(" · ")[0]}</option>)}
        </select></label>
      <label className="fmt-f"><span><I.Sliders size={13} /> Quality</span>
        <select value={quality} onChange={(e) => onFrame("quality", e.target.value)} aria-label="Quality for the whole project">
          {QUALITY.map(([v, l]) => <option key={v} value={v}>{l.split(" · ")[0]}{l.includes("·") ? ` · ${l.split(" · ")[1].replace("best the model offers", "best")}` : ""}</option>)}
        </select></label>
      {own.map((f) => {
        const pinned = f.name in pins;
        const shown = pinned ? pins[f.name] : auto[f.name] ?? f.default;
        return (
          <label key={f.name} className={`fmt-f ${pinned ? "pinned" : ""}`}><span>{label(f.name, roleOf[f.name])}</span>
            {f.enum?.length
              ? <select value={pinned ? String(pins[f.name]) : ""} onChange={(e) => set(f.name, e.target.value, f)} aria-label={label(f.name, roleOf[f.name])}>
                  <option value="">Auto{shown !== undefined && shown !== null ? ` · ${String(shown)}` : ""}</option>
                  {f.enum.map((o) => <option key={String(o)} value={String(o)}>{String(o)}</option>)}
                </select>
              : <input type="number" min={f.minimum ?? undefined} max={f.maximum ?? undefined} placeholder={`Auto${shown ? ` · ${String(shown)}` : ""}`}
                       value={pinned ? String(pins[f.name]) : ""} onChange={(e) => set(f.name, e.target.value, f)} aria-label={label(f.name, roleOf[f.name])} />}
          </label>);
      })}
      {shape && (differs
        ? <Pill tone="warn" icon={<I.Alert size={12} />} title="This model can't make your frame shape exactly, so the picture is trimmed to your shape afterwards.">
            Model makes {shape.label}: trimmed to {frame}</Pill>
        : <Pill tone="ok" icon={<I.Check size={12} />} title="What will be asked of the model">Sends {shape.label}</Pill>)}
    </div>
  );
}
