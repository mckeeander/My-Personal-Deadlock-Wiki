#!/usr/bin/env python3
"""The orders top-ranked players spend ability points in, per hero, from the Deadlock API's match statistics, into data/ability_order.json.

Same matches as Popular items (the rank cut-off popular.py worked out, last 30 days). Orders are grouped by play style: the
first two abilities a player maxes (four points each: unlock, then tiers 1, 2 and 3). Up to three styles are kept per hero,
and only ones that are really different: a style must be at least MIN_SHARE of the orders, and one that maxes the same ability
first as a style already kept needs SAME_FIRST_SHARE. For each style, every point (ability, nth point in it) gets the average
time it's spent and the share of that style's players who get that far; the app places points by time.

Run:  python3 tools/abilityorder.py      (one request per hero; run after popular.py, whose rank cut-off it reuses)
"""
import json, os, sys, time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from popular import get, load, DATA  # same API helper and data loader

MIN_SHARE = 0.08         # a style needs at least this share of the hero's orders
SAME_FIRST_SHARE = 0.10  # ...and this much if it maxes the same ability first as one already kept
MIN_POINTS = 12          # orders shorter than this (very short matches) say little about a style
MIN_REACH = 0.05         # points fewer than this share of a style's players reach are left out (the last points come late, when many matches are over)


def badge_cutoff():
    try:
        return json.load(open(os.path.join(DATA, "popular.json"), encoding="utf-8"))["badge"]
    except Exception:
        dist = sorted(get("/analytics/badge-distribution"), key=lambda x: -x["badge_level"])
        total, run, badge = sum(x["total_matches"] for x in dist), 0, None
        for x in dist:
            run += x["total_matches"]
            if run / total > 0.05: break
            badge = x["badge_level"]
        return badge


def style(order):
    seen, maxed = defaultdict(int), []
    for a in order:
        seen[a] += 1
        if seen[a] == 4: maxed.append(a)
    return tuple(maxed[:2])


def main():
    heroes = [h for h in load("heroes.json") if h.get("id") and not h.get("disabled") and h.get("player_selectable", True)]
    ids = {i["class_name"]: i["id"] for i in load("items.json") if i.get("id") and i.get("class_name")}
    badge, since = badge_cutoff(), int(time.time()) - 30 * 86400
    out = {}
    for h in heroes:
        slots = {}
        for n in range(4):
            c = (h.get("items") or {}).get("signature%d" % (n + 1))
            if c in ids: slots[ids[c]] = n
        if len(slots) < 4: continue
        try:
            rows = get("/analytics/ability-order-stats?hero_id=%d&min_average_badge=%d&min_unix_timestamp=%d&min_matches=5" % (h["id"], badge, since))
        except Exception as e:
            print("  %s: %s" % (h.get("name"), e)); continue
        rows = [r for r in rows if len(r.get("abilities") or []) >= MIN_POINTS and all(a in slots for a in r["abilities"])]
        groups = defaultdict(list)
        for r in rows: groups[style(r["abilities"])].append(r)
        total = sum(r["matches"] for r in rows)
        if not total: continue
        kept = []
        for key, rs in sorted(groups.items(), key=lambda kv: -sum(r["matches"] for r in kv[1])):
            if len(key) < 2: continue
            share = sum(r["matches"] for r in rs) / total
            if share < MIN_SHARE or len(kept) == 3: break
            if any(k[0][0] == key[0] for k in kept) and share < SAME_FIRST_SHARE: continue
            if any(k[0] == key for k in kept): continue
            kept.append((key, rs, share))
        builds = []
        for key, rs, share in kept:
            n = sum(r["matches"] for r in rs)
            tsum, wsum = defaultdict(float), defaultdict(float)
            for r in rs:
                cnt = defaultdict(int)
                for a, t in zip(r["abilities"], r.get("avg_upgrade_times_s") or []):
                    cnt[a] += 1; ev = (slots[a], cnt[a] - 1)  # (ability slot, 0 = unlock, 1-3 = tier)
                    tsum[ev] += t * r["matches"]; wsum[ev] += r["matches"]
            pts = sorted(([ev[0], ev[1], round(tsum[ev] / wsum[ev]), round(wsum[ev] / n, 2)] for ev in wsum if wsum[ev] / n >= MIN_REACH), key=lambda p: p[2])
            builds.append({"max": [slots[a] for a in key], "share": round(share, 3), "n": n, "pts": pts})
        if builds: out[h["class_name"]] = {"n": total, "builds": builds}
        time.sleep(0.4)
    if not out:
        print("no data; keeping the old file"); return 1
    json.dump({"source": "api.deadlock-api.com (match statistics)", "days": 30, "badge": badge, "updated": time.strftime("%Y-%m-%d"),
               "fields": "pts: [ability slot 0-3, 0 unlock / 1-3 tier, average time (s), share of the style's players who get that far]", "heroes": out},
              open(os.path.join(DATA, "ability_order.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("ability order: %d heroes, %d with more than one style" % (len(out), sum(1 for v in out.values() if len(v["builds"]) > 1)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
