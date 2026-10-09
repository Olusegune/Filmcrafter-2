// More UI checks to paste into the browser pane's console next to ui-audit.js (same use: open the Studio in the preview, set a window size, run, read the result).
//   window.__contrast()  text whose colour against its real background is below WCAG AA (4.5, or 3 for large text), grouped by CSS class, worst first
//   window.__focus()     controls that show nothing when they get keyboard focus
//   window.__misc()      page language and title, duplicate ids, labels with no control, truncated text with no tooltip, images with no alt
(() => {
  const lum = (r, g, b) => { const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const parse = (s) => { const m = s.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const over = (top, under) => ({ r: top.r * top.a + under.r * (1 - top.a), g: top.g * top.a + under.g * (1 - top.a), b: top.b * top.a + under.b * (1 - top.a), a: 1 });
  const backdrop = (el) => {
    const chain = [];
    for (let e = el; e; e = e.parentElement) { const cs = getComputedStyle(e); if (/gradient|url\(/.test(cs.backgroundImage)) return null; const c = parse(cs.backgroundColor); if (c && c.a > 0) { chain.push(c); if (c.a >= 1) break; } }
    let base = { r: 5, g: 7, b: 10, a: 1 };                       // the app's own background, behind everything
    for (let i = chain.length - 1; i >= 0; i--) base = over(chain[i], base);
    return base;
  };
  const visible = (e) => { const r = e.getBoundingClientRect(), cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none" && +cs.opacity > 0.05 && r.bottom > 0 && r.top < innerHeight; };
  const hasText = (e) => [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim().length > 1);
  const label = (e) => (e.className && typeof e.className === "string" ? "." + e.className.trim().split(/\s+/).slice(0, 2).join(".") : e.tagName.toLowerCase());

  window.__contrast = () => {
    const groups = {};
    let checked = 0;
    for (const e of document.querySelectorAll("body *")) {
      if (!hasText(e) || !visible(e)) continue;
      const cs = getComputedStyle(e);
      let fg = parse(cs.color); if (!fg) continue;
      const bg = backdrop(e);
      if (!bg) continue;                                              // on a gradient or a picture: a colour pair cannot say
      fg = over({ ...fg, a: fg.a * (+cs.opacity || 1) }, bg);
      const L1 = lum(fg.r, fg.g, fg.b), L2 = lum(bg.r, bg.g, bg.b);
      const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
      const px = parseFloat(cs.fontSize), bold = +cs.fontWeight >= 700;
      const need = px >= 24 || (px >= 18.66 && bold) ? 3 : 4.5;
      checked++;
      if (e.disabled || e.closest("[disabled], [aria-disabled=true]")) continue;          // a disabled control is allowed to look disabled
      if (ratio < need) { const k = label(e); (groups[k] ??= { n: 0, worst: 99, need, sample: e.textContent.trim().slice(0, 40), colour: cs.color }).n++; groups[k].worst = Math.min(groups[k].worst, +ratio.toFixed(2)); }
    }
    return { checked, failing: Object.entries(groups).sort((a, b) => a[1].worst - b[1].worst).slice(0, 25).map(([k, v]) => `${k} x${v.n} ${v.worst}:1 (needs ${v.need}) "${v.sample}" ${v.colour}`) };
  };

  // Which controls would show something when focused from the keyboard? A script cannot press Tab, so this reads the style sheets instead: it looks for a :focus-visible / :focus rule
  // that matches the control and gives it an outline, a shadow or a border colour. (Checked by hand with real Tab presses on the Home screen: the rings appear.)
  window.__focus = () => {
    const rules = [];
    for (const sheet of document.styleSheets) {
      let list; try { list = sheet.cssRules; } catch { continue; }
      const walk = (rs) => { for (const r of rs) { if (r.cssRules && !r.selectorText) walk(r.cssRules); if (!r.selectorText || !/:focus(-visible)?/.test(r.selectorText)) continue;
        const st = r.style, shows = (st.outlineStyle && st.outlineStyle !== "none") || (st.outline && !/none|0px/.test(st.outline)) || st.boxShadow || st.borderColor || st.border || st.background || st.backgroundColor;
        if (!shows) continue;
        for (const sel of r.selectorText.split(",")) { if (!/:focus(-visible)?/.test(sel)) continue; const base = sel.replace(/:focus-visible|:focus-within|:focus/g, "").replace(/::[\w-]+/g, "").trim() || "*"; rules.push(base); } } };
      walk(list);
    }
    const none = [];
    const list = [...document.querySelectorAll("button, a[href], input, select, textarea, summary, [tabindex='0']")].filter((e) => visible(e) && !e.disabled && e.tabIndex >= 0).slice(0, 200);
    for (const e of list) {
      let ok = false;
      for (const sel of rules) { try { if (e.matches(sel)) { ok = true; break; } } catch { /* a selector the browser cannot match here */ } }
      if (!ok && !(e.type === "range" || e.type === "color")) none.push(label(e) + " " + (e.innerText || e.getAttribute("aria-label") || e.title || "").trim().slice(0, 28));
    }
    return { checked: list.length, noFocusRule: [...new Set(none)].slice(0, 25) };
  };

  window.__misc = () => {
    const out = { lang: document.documentElement.lang || "(none)", title: document.title, dupIds: [], orphanLabels: 0, truncatedNoTip: [], noAlt: document.querySelectorAll("img:not([alt])").length };
    const ids = {}; document.querySelectorAll("[id]").forEach((e) => { ids[e.id] = (ids[e.id] || 0) + 1; });
    out.dupIds = Object.entries(ids).filter(([, n]) => n > 1).map(([k]) => k).slice(0, 10);
    document.querySelectorAll("label[for]").forEach((l) => { if (!document.getElementById(l.htmlFor)) out.orphanLabels++; });
    for (const e of document.querySelectorAll("body *")) {
      if (!visible(e) || e.children.length > 0) continue;
      const cs = getComputedStyle(e);
      if ((cs.textOverflow === "ellipsis" || cs.overflow === "hidden") && e.scrollWidth > e.clientWidth + 2 && !e.title && !e.closest("[title]") && hasText(e)) out.truncatedNoTip.push(label(e) + " " + e.textContent.trim().slice(0, 30));
    }
    out.truncatedNoTip = [...new Set(out.truncatedNoTip)].slice(0, 15);
    return out;
  };
})();
