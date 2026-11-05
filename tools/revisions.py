#!/usr/bin/env python3
"""Compare two Deadlock data snapshots and append what changed for each hero to data/revisions.json.

Usage: python3 tools/revisions.py OLD_DIR NEW_DIR [--date YYYY-MM-DD] [--out data/revisions.json]

OLD_DIR and NEW_DIR each hold heroes.json and items.json. Only game data is compared, so changes to how the site
shows things never appear. Each run that finds changes adds one entry (newest first); a run on the same date
replaces that date's entry, so re-running the update job on one day doesn't stack duplicates.

Each change is stored raw (keys and old/new values); the site formats labels and units with the same helpers its
cards use, so the history reads the same way as the rest of the page.
"""
import datetime
import json
import os
import sys

# weapon numbers worth listing; the rest (DPS, damage per magazine, ...) are worked out from these
WEAPON_KEYS = ["bullet_damage", "bullets", "clip_size", "cycle_time", "reload_duration", "reload_single",
               "bullet_speed", "falloff_start_range", "falloff_end_range", "crit_bonus_start", "spread",
               "bullet_gravity_scale", "burst_shot_count", "intra_burst_cycle_time"]


def load(d, name):
    with open(os.path.join(d, name), encoding="utf-8") as f:
        return json.load(f)


def num(v):
    try:
        return float(str(v).replace("m", "").replace("s", "").replace("%", ""))
    except (TypeError, ValueError):
        return None


def same(a, b):
    if a == b:
        return True
    x, y = num(a), num(b)
    return x is not None and y is not None and abs(x - y) < 1e-9 and str(a).rstrip("0") == str(b).rstrip("0")


def scale_of(p):
    sf = (p or {}).get("scale_function") or {}
    return sf.get("stat_scale")


def ability_changes(a, b):
    """Changes to one ability (or weapon item's properties)."""
    out = []
    pa, pb = a.get("properties") or {}, b.get("properties") or {}
    for k in list(pb.keys()) + [k for k in pa if k not in pb]:
        x, y = pa.get(k), pb.get(k)
        vx = x.get("value") if isinstance(x, dict) else None
        vy = y.get("value") if isinstance(y, dict) else None
        if not same(vx, vy):
            nx, ny = num(vx), num(vy)
            kind = "new" if (vx is None or nx == 0) and ny not in (None, 0) else "rm" if (vy is None or ny == 0) and nx not in (None, 0) else "val"
            out.append({"kind": kind, "key": k, "old": vx, "new": vy})
        sx, sy = scale_of(x), scale_of(y)
        if sx is not None and sy is not None and not same(sx, sy):
            out.append({"kind": "scale", "key": k, "old": sx, "new": sy})
    ua, ub = a.get("upgrades") or [], b.get("upgrades") or []
    da, db = a.get("description") or {}, b.get("description") or {}
    for t in range(max(len(ua), len(ub))):
        pua = ((ua[t] if t < len(ua) else {}) or {}).get("property_upgrades") or []
        pub = ((ub[t] if t < len(ub) else {}) or {}).get("property_upgrades") or []
        dk = "t%d_desc" % (t + 1)
        if pua == pub and da.get(dk) == db.get(dk):
            continue
        # the tier's text, before and after (the site shows tier boxes when several things in a tier changed, or one line when only one number did)
        out.append({"kind": "tier", "tier": t + 1, "old": da.get(dk) or "", "new": db.get(dk) or ""})
        for i in range(max(len(pua), len(pub))):
            x = pua[i] if i < len(pua) else {}
            y = pub[i] if i < len(pub) else {}
            if x.get("bonus") != y.get("bonus") or x.get("name") != y.get("name"):
                sc = (y.get("upgrade_type") or x.get("upgrade_type")) == "EAddToScale"  # the upgrade adds to the stat's spirit scaling, not the stat
                out.append({"kind": "tierscale" if sc else "tierval", "tier": t + 1, "key": y.get("name") or x.get("name"), "old": x.get("bonus"), "new": y.get("bonus")})
    if (da.get("desc") or "") != (db.get("desc") or ""):
        out.append({"kind": "desc", "old": da.get("desc") or "", "new": db.get("desc") or ""})
    return out


def weapon_changes(a, b):
    wa, wb = a.get("weapon_info") or {}, b.get("weapon_info") or {}
    out = [{"kind": "wpn", "key": k, "old": wa.get(k), "new": wb.get(k)} for k in WEAPON_KEYS if not same(wa.get(k), wb.get(k))]
    return out + [c for c in ability_changes(a, b) if c["kind"] != "desc"]


def hero_changes(a, b):
    out = []
    for grp in ("starting_stats", "scaling_stats", "standard_level_up_upgrades"):
        ga, gb = a.get(grp) or {}, b.get(grp) or {}
        for k in list(gb.keys()) + [k for k in ga if k not in gb]:
            x, y = ga.get(k), gb.get(k)
            if grp == "starting_stats":
                x, y = (x or {}).get("value"), (y or {}).get("value")
            elif grp == "scaling_stats":
                x, y = (x or {}).get("scale"), (y or {}).get("scale")
            if not same(x, y):
                out.append({"kind": "hero", "grp": grp, "key": k, "old": x, "new": y})
    return out


def compare(old_dir, new_dir):
    ha = {h["class_name"]: h for h in load(old_dir, "heroes.json")}
    hb = {h["class_name"]: h for h in load(new_dir, "heroes.json")}
    ia = {x["class_name"]: x for x in load(old_dir, "items.json")}
    ib = {x["class_name"]: x for x in load(new_dir, "items.json")}
    heroes = {}
    for hc, h in hb.items():
        if h.get("disabled") or hc not in ha:
            continue
        groups = []
        hcs = hero_changes(ha[hc], h)
        if hcs:
            groups.append({"item": None, "type": "hero", "changes": hcs})
        items = h.get("items") or {}
        for slot in ("weapon_primary", "signature1", "signature2", "signature3", "signature4"):
            cn = items.get(slot)
            if not cn or cn not in ib or cn not in ia:
                continue
            a, b = ia[cn], ib[cn]
            if a == b:
                continue
            cs = weapon_changes(a, b) if slot == "weapon_primary" else ability_changes(a, b)
            if cs:
                groups.append({"item": cn, "name": b.get("name"), "type": "weapon" if slot == "weapon_primary" else "ability", "changes": cs})
        if groups:
            heroes[hc] = groups
    items = {}
    for cn, b in ib.items():  # shop items, kept for later use
        a = ia.get(cn)
        if b.get("type") != "upgrade" or not a or a == b or b.get("disabled"):
            continue
        cs = ability_changes(a, b)
        if cs:
            items[cn] = {"name": b.get("name"), "changes": cs}
    return heroes, items


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    opts = dict(a[2:].split("=", 1) for a in argv if a.startswith("--") and "=" in a)
    old_dir, new_dir = args[0], args[1]
    out = opts.get("out", os.path.join(new_dir, "revisions.json"))
    date = opts.get("date") or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    heroes, items = compare(old_dir, new_dir)
    hist = []
    if os.path.exists(out):
        with open(out, encoding="utf-8") as f:
            hist = json.load(f)
    hist = [e for e in hist if e.get("date") != date or not (heroes or items)]
    if heroes or items:
        prev = next((e for e in json.load(open(out, encoding="utf-8")) if e.get("date") == date), None) if os.path.exists(out) else None
        if prev:  # a second run on the same day: keep what the first run found and add anything new
            for hc, gs in prev.get("heroes", {}).items():
                heroes.setdefault(hc, gs)
            for cn, v in prev.get("items", {}).items():
                items.setdefault(cn, v)
        hist.insert(0, {"date": date, "heroes": heroes, "items": items})
        hist.sort(key=lambda e: e["date"], reverse=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, separators=(",", ":"))
    n = sum(len(c["changes"]) for gs in heroes.values() for c in gs)
    print("revisions: %d heroes, %d changes, %d items on %s" % (len(heroes), n, len(items), date))


if __name__ == "__main__":
    main(sys.argv[1:])
