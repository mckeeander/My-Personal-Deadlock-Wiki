"""items.json stores each of the game's inline SVG icons once, in item_icons.json, and puts a short token in the text where it went
("@@S3@@"); asset links start with "~A/" instead of the full address. That cuts the download by about a third.
expand() puts the full text back, for tools that compare or read descriptions."""
import json, os, re

PREFIX = "https://assets-bucket.deadlock-api.com/assets-api-res/"
TOKEN = re.compile(r"@@S(\d+)@@")


def load_icons(d):
    p = os.path.join(d, "item_icons.json")
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def expand(items, d):
    """Full SVGs and links back in place, using the item_icons.json next to items.json in directory d."""
    ic = load_icons(d)
    if not ic: return items
    svg, pre = ic.get("svg") or [], ic.get("prefix") or PREFIX

    def walk(v):
        if isinstance(v, str):
            if "@@S" in v: v = TOKEN.sub(lambda m: svg[int(m.group(1))] if int(m.group(1)) < len(svg) else "", v)
            if v.startswith("~A/"): v = pre + v[3:]
            return v
        if isinstance(v, list): return [walk(x) for x in v]
        if isinstance(v, dict): return {k: walk(x) for k, x in v.items()}
        return v
    return walk(items)


def compact(items):
    """(items with tokens, icon table): each distinct SVG kept once, asset links shortened."""
    svgs, idx = [], {}

    def walk(v):
        if isinstance(v, str):
            def sub(m):
                s = m.group(0)
                if s not in idx: idx[s] = len(svgs); svgs.append(s)
                return "@@S%d@@" % idx[s]
            if "<svg" in v: v = re.sub(r"<svg[\s\S]*?</svg>", sub, v)
            if v.startswith(PREFIX): v = "~A/" + v[len(PREFIX):]
            return v
        if isinstance(v, list): return [walk(x) for x in v]
        if isinstance(v, dict): return {k: walk(x) for k, x in v.items()}
        return v
    return walk(items), {"prefix": PREFIX, "svg": svgs}
