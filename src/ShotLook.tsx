import { useEffect, useState } from "react";
import { api, errorText, type StyleBibleRead } from "./api";
import { PanelHead } from "./Dock";
import * as I from "./icons";

/** Save one shot's own look; an empty pick goes back to its scene's or the film's. It only writes a setting: nothing is rendered or charged. */
export const saveShotLook = (dir: string, shotId: string, style: string) => api.stylebible(dir, "set_shot", { shot: shotId, style: style || null });

/** The first option of the picker: what the shot is played in when it has no look of its own. */
export const sameAsLabel = (own: StyleBibleRead, filmLook: string, sceneLook: string): string =>
  `Same as its ${sceneLook !== filmLook ? "scene" : "film"} (${own.styles.find((x) => x.id === sceneLook)?.name ?? sceneLook})`;

/** Play this one shot in another look than its scene and the film (a dream, a memory). It only changes what the next picture or take is made from: nothing is re-rendered, and a new take shows its price first. */
export function ShotLook({ dir, shotId, own, filmLook, sceneLook, onChanged }: {
  dir: string; shotId: string; own: StyleBibleRead | null; filmLook: string; sceneLook: string; onChanged: (r: StyleBibleRead) => void;
}) {
  const [err, setErr] = useState("");
  const mine = own?.shots[shotId] ?? "";
  const [open, setOpen] = useState(!!mine);                                       // folded until the shot has a look of its own; once open it stays open, also after the look is cleared
  useEffect(() => { if (mine) setOpen(true); }, [mine]);
  if (!own) return null;
  const set = (style: string) => { setErr(""); saveShotLook(dir, shotId, style).then(onChanged).catch((e) => setErr(errorText(e))); };
  return (
    <details className="panel shot-look" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary><PanelHead icon={<I.Eye size={18} />} title="Look for this shot" tag={mine ? "Own" : ""} tone="ok" right={<I.Chevron size={16} />} /></summary>
      <label className="sl-field"><span className="cam-lbl">Look</span>
        <select aria-label="Look for this shot" value={mine} onChange={(e) => set(e.target.value)}>
          <option value="">{sameAsLabel(own, filmLook, sceneLook)}</option>
          {own.styles.filter((x) => x.id !== sceneLook).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
        </select></label>
      <p className="dim">{mine ? "This shot is made in its own look. Pictures and takes already made are left as they are." : "Pictures and takes already made are never re-rendered when a look changes."}</p>
      {err && <div className="error-text" role="alert">{err}</div>}
    </details>
  );
}
