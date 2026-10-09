// A UI audit to paste into the browser pane's console (or run through the preview tool) while the Studio is open (`npm run dev`, http://localhost:1420/?mock).
// It reports, for the current window size: horizontal scrolling of the page, controls with no accessible name, images with no alt, controls covered by another element
// (the kind of bug where one button sits on top of another), and controls smaller than 18 px. Controls scrolled out of view inside their own scroll area are not counted.
// Use `copy(JSON.stringify(window.__audit()))` or read the returned object. The app's smallest window is 1100 x 700: audit at that size and a large one.
window.__audit = () => {
  const out = { w: innerWidth, h: innerHeight, hscroll: document.documentElement.scrollWidth > innerWidth + 1, noName: [], noAlt: 0, obscured: [], tiny: 0 };
  const clipped = (e) => {
    const r = e.getBoundingClientRect(), cx = r.x + r.width / 2, cy = r.y + r.height / 2;
    for (let p = e.parentElement; p && p !== document.body; p = p.parentElement) {
      const cs = getComputedStyle(p);
      if (/(auto|scroll|hidden|clip)/.test(cs.overflowY + cs.overflowX)) { const b = p.getBoundingClientRect(); if (cx < b.left || cx > b.right || cy < b.top || cy > b.bottom) return true; }
    }
    return false;
  };
  for (const e of document.querySelectorAll("button,a[href],input,select,textarea,[role=button],[role=tab],[role=menuitem]")) {
    const r = e.getBoundingClientRect(), cs = getComputedStyle(e);
    if (r.width <= 0 || r.height <= 0 || cs.visibility === "hidden" || cs.display === "none" || clipped(e)) continue;
    const cx = Math.min(innerWidth - 1, Math.max(0, r.x + r.width / 2)), cy = Math.min(innerHeight - 1, Math.max(0, r.y + r.height / 2));
    if (r.bottom < 0 || r.top >= innerHeight || r.right < 0 || r.left >= innerWidth) continue;
    const name = (e.getAttribute("aria-label") || e.innerText || e.title || e.getAttribute("placeholder") || (e.labels && e.labels[0] && e.labels[0].innerText) || "").trim();
    if (!name && !["range", "color", "hidden"].includes(e.type)) out.noName.push(e.outerHTML.slice(0, 90));
    if (Math.min(r.width, r.height) < 18 && !["checkbox", "radio"].includes(e.type)) out.tiny++;
    const top = document.elementFromPoint(cx, cy);
    if (top && top !== e && !e.contains(top) && !top.contains(e)) out.obscured.push(((e.innerText || e.getAttribute("aria-label") || e.className || "") + "").slice(0, 30) + " <- " + ((top.className || top.tagName) + "").slice(0, 40));
  }
  out.noAlt = document.querySelectorAll("img:not([alt])").length;
  out.noName = out.noName.slice(0, 10);
  out.obscured = out.obscured.slice(0, 12);
  return out;
};
