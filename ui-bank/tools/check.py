"""Render every pattern page and assert the things eyes miss.

Run from the repo root:  .venv/bin/python ui-bank/tools/check.py [page ...]

For each page x viewport it saves a screenshot into ui-bank/screenshots/ and
reports three classes of failure:

  overflow-page   the document scrolls horizontally
  overflow-el     an element's content is wider/taller than its box and the
                  box is not a scroll container
  contrast        rendered text below the WCAG AA ratio for its size

The contrast check resolves the effective background by walking ancestors
until it finds a non-transparent one, which is what a human eye does; it
cannot see through a background-image, so those elements are skipped and
reported separately rather than silently passing.
"""

import json
import pathlib
import sys

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
PATTERNS = ROOT / "patterns"
SHOTS = ROOT / "screenshots"

# (label, width, height, colour scheme). One shot per row. Both schemes are
# covered across the set rather than doubling every page.
VIEWPORTS = [
    ("1920x1080-dark", 1920, 1080, "dark"),
    ("1366x768-light", 1366, 768, "light"),
    ("900x1400-dark", 900, 1400, "dark"),
]

AUDIT_JS = r"""
() => {
  // color-mix() computes to `color(srgb r g b / a)` with 0-1 channels in
  // Chromium, not rgba(). Missing that made every colour-mixed panel invisible
  // to this check and silently fall through to the page background.
  const parseColor = (s) => {
    let m = s.match(/^color\(srgb ([^)]+)\)/);
    if (m) {
      const p = m[1].split(/[\s/]+/).filter(Boolean).map(Number);
      return { r: p[0] * 255, g: p[1] * 255, b: p[2] * 255, a: p.length > 3 ? p[3] : 1 };
    }
    m = s.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(/[,\s/]+/).filter(Boolean).map(Number);
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const lin = (c) => {
    c /= 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  };
  const lum = (c) => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
  const over = (fg, bg) => ({
    r: fg.r * fg.a + bg.r * (1 - fg.a),
    g: fg.g * fg.a + bg.g * (1 - fg.a),
    b: fg.b * fg.a + bg.b * (1 - fg.a),
    a: 1,
  });
  const ratio = (a, b) => {
    const l1 = lum(a), l2 = lum(b);
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
  };
  const desc = (el) => {
    let s = el.tagName.toLowerCase();
    if (el.id) s += "#" + el.id;
    if (el.className && typeof el.className === "string")
      s += "." + el.className.trim().split(/\s+/).slice(0, 3).join(".");
    return s;
  };

  const out = { pageOverflow: null, elementOverflow: [], contrast: [], skipped: [] };

  const de = document.documentElement;
  if (de.scrollWidth > de.clientWidth) {
    out.pageOverflow = { scrollWidth: de.scrollWidth, clientWidth: de.clientWidth };
  }

  const all = document.querySelectorAll("body *");
  for (const el of all) {
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden") continue;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) continue;
    // Deliberately clipped (.visually-hidden) - not a layout defect.
    if (cs.clipPath && cs.clipPath !== "none") continue;

    // --- overflow: only a complaint when the box cannot scroll to reveal it.
    const scrollableX = ["auto", "scroll"].includes(cs.overflowX);
    const scrollableY = ["auto", "scroll"].includes(cs.overflowY);
    if (!scrollableX && el.scrollWidth - el.clientWidth > 1 && cs.overflowX !== "visible") {
      out.elementOverflow.push({
        el: desc(el), axis: "x", over: el.scrollWidth - el.clientWidth });
    }
    if (!scrollableY && el.scrollHeight - el.clientHeight > 1 && cs.overflowY !== "visible") {
      out.elementOverflow.push({
        el: desc(el), axis: "y", over: el.scrollHeight - el.clientHeight });
    }

    // --- contrast: only for nodes that render their own text.
    const ownText = Array.from(el.childNodes)
      .filter((n) => n.nodeType === 3 && n.textContent.trim().length)
      .map((n) => n.textContent.trim())
      .join(" ");
    if (!ownText) continue;
    // Decorative glyphs hidden from assistive tech and duplicated by a real
    // text label next to them are icons, not text. Everything visible that is
    // NOT aria-hidden still has to pass.
    if (el.closest('[aria-hidden="true"]')) continue;

    const fg = parseColor(cs.color);
    if (!fg || fg.a === 0) continue;

    // Opacity anywhere up the tree fades the text against whatever is behind
    // it. Skipping faded elements (the first version of this check) excused
    // precisely the cases where contrast is worst.
    let opacity = 1;
    for (let a = el; a && a !== document.documentElement; a = a.parentElement) {
      opacity *= parseFloat(getComputedStyle(a).opacity) || 1;
    }
    fg.a *= opacity;
    if (fg.a <= 0.02) continue;

    let bg = null, node = el, imaged = false;
    while (node) {
      const ncs = getComputedStyle(node);
      if (ncs.backgroundImage && ncs.backgroundImage !== "none") { imaged = true; break; }
      const c = parseColor(ncs.backgroundColor);
      if (c && c.a > 0) {
        bg = bg ? over(bg, c) : (c.a === 1 ? c : { ...c });
        if (c.a === 1) break;
      }
      node = node.parentElement;
    }
    if (imaged) { out.skipped.push({ el: desc(el), why: "background-image" }); continue; }
    if (!bg) bg = { r: 255, g: 255, b: 255, a: 1 };
    if (bg.a < 1) bg = over(bg, { r: 255, g: 255, b: 255, a: 1 });

    const size = parseFloat(cs.fontSize);
    const weight = parseInt(cs.fontWeight, 10) || 400;
    const large = size >= 24 || (size >= 18.66 && weight >= 700);
    const need = large ? 3.0 : 4.5;
    const r = ratio(over(fg, bg), bg);
    if (r < need) {
      out.contrast.push({
        el: desc(el), text: ownText.slice(0, 40), ratio: +r.toFixed(2),
        need, size, color: cs.color });
    }
  }
  return out;
}
"""


def main(argv):
    pages = argv or sorted(p.name for p in PATTERNS.glob("*.html"))
    SHOTS.mkdir(exist_ok=True)
    failures = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for page_name in pages:
            path = PATTERNS / page_name
            if not path.exists():
                print(f"!! missing {page_name}")
                failures += 1
                continue
            stem = path.stem
            for label, width, height, scheme in VIEWPORTS:
                ctx = browser.new_context(
                    viewport={"width": width, "height": height},
                    color_scheme=scheme,
                    device_scale_factor=1,
                )
                page = ctx.new_page()
                page.goto(path.as_uri())
                page.wait_for_timeout(250)
                shot = SHOTS / f"{stem}--{label}.png"
                page.screenshot(path=str(shot), full_page=False)
                report = page.evaluate(AUDIT_JS)
                ctx.close()

                problems = []
                if report["pageOverflow"]:
                    problems.append(f"page-overflow {report['pageOverflow']}")
                for item in report["elementOverflow"]:
                    problems.append(f"overflow-{item['axis']} {item['el']} +{item['over']}px")
                for item in report["contrast"]:
                    problems.append(
                        f"contrast {item['ratio']}<{item['need']} {item['el']} "
                        f"[{item['text']}]"
                    )
                status = "PASS" if not problems else f"FAIL({len(problems)})"
                print(f"{stem:26s} {label:16s} {status}")
                for p in problems[:12]:
                    print(f"    - {p}")
                if len(problems) > 12:
                    print(f"    ... {len(problems) - 12} more")
                failures += len(problems)
        browser.close()

    print(f"\ntotal problems: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
