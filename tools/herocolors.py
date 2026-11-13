#!/usr/bin/env python3
"""Each hero's card colours, picked from their portrait, into data/hero_colors.json.

The hero page's header card paints soft blobs of these colours behind the name. The picker favours vivid colours
over large areas (Grey Talon's robe over his grey hair, Infernus's flame over his dark coat) and lifts them a little.
OVERRIDES sets a hero's colours by hand where the art has a look the picker can't know about.

Run:  python3 tools/herocolors.py      (needs Pillow; one image download per hero)
A hero whose portrait can't be read keeps yesterday's colours.
"""
import colorsys, io, json, os, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

# hand-picked colours, a line per hero (2 or 3 hex colours, strongest first)
OVERRIDES = {
    "hero_baba": ["#a3203f", "#c77dab", "#6f2a52"],  # her scarf's burgundy and the lilac behind her on the wiki
    "hero_nano": ["#8a5cc7", "#c0b67c", "#5d3d99"],  # Calico: the purple of her cat and coat, with the gold of her glasses
}


def portrait(h):
    im = h.get("images") or {}
    for k in ("icon_hero_card", "icon_image_small", "selection_image"):
        if im.get(k): return im[k]


def pick(data):
    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("RGBA").resize((64, 86))
    W, H = im.size
    px = []
    for y in range(H):
        for x in range(W):
            p = im.getpixel((x, y))
            if p[3] > 200: px.append((p[:3], y / H))
    if not px: return None
    q = Image.new("RGB", (len(px), 1)); q.putdata([p[0] for p in px])
    q = q.quantize(colors=14, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[:42]
    stats = {}
    for (rgb, y), i in zip(px, [q.getpixel((k, 0)) for k in range(len(px))]):
        s = stats.setdefault(i, [0, 0]); s[0] += 1; s[1] += y
    def gather(min_s):
        cols = []
        for i, (n, sy) in stats.items():
            r, g, b = pal[i * 3:i * 3 + 3]
            hue, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
            if l < .1 or l > .9 or s < min_s: continue  # near black, near white, greys
            score = (n ** .5) * (s ** 2 + .02) * (1 - abs(l - .5))  # vivid beats big
            R, G, B = colorsys.hls_to_rgb(hue, min(.62, max(.45, l)), min(1, max(s * 1.25, .35)))  # lifted a little
            cols.append((score, "#%02x%02x%02x" % (int(R * 255), int(G * 255), int(B * 255)), hue * 360, sy / n))
        return cols
    cols = gather(.25) or gather(.08) or gather(0)  # muted portraits (Graves, Warden...) still get their strongest tint
    cols.sort(reverse=True)
    chosen = []
    for c in cols:  # distinct hues only
        if all(min(abs(c[2] - p[2]), 360 - abs(c[2] - p[2])) > 30 for p in chosen): chosen.append(c)
    if not chosen: return None
    return {"colors": [c[1] for c in chosen[:3]], "y": round(chosen[0][3], 2)}


def main():
    heroes = json.load(open(os.path.join(DATA, "heroes.json"), encoding="utf-8"))
    path = os.path.join(DATA, "hero_colors.json")
    try: old = json.load(open(path, encoding="utf-8")).get("heroes", {})
    except Exception: old = {}
    out, fails = {}, []
    for h in heroes:
        cn, u = h.get("class_name"), portrait(h)
        if not cn or not u: continue
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (personal-deadlock-wiki data update)"})
            got = pick(urllib.request.urlopen(req, timeout=30).read())
        except Exception as e:
            got = None; fails.append("%s (%s)" % (h.get("name"), str(e)[:60]))
        if got is None and cn in old: got = old[cn]
        if cn in OVERRIDES: got = dict(got or {"y": .5}, colors=OVERRIDES[cn], hand=True)
        if got: out[cn] = got
    if not out:
        print("herocolors: nothing read; keeping the old file"); return 1
    json.dump({"source": "picked from each hero's portrait; see tools/herocolors.py", "heroes": out},
              open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("herocolors: %d heroes, %d hand-picked%s" % (len(out), sum(1 for v in out.values() if v.get("hand")), ("; failed: " + ", ".join(fails)) if fails else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
