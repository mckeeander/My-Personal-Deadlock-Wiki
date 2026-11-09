#!/usr/bin/env python3
"""Build data/patchnotes.json and data/powerups.json from a checkout of github.com/deadlock-wiki/deadlock-data (MIT).

    python3 tools/wikidata.py <path to deadlock-data checkout>

patchnotes.json: official patch notes since SINCE (newest first), split into general notes, items and heroes, with
                 every hero, ability and item matched to the game data's class names so the app can link them.
                 Inline names are kept as tokens: [[h:Hero]] [[a:Ability]] [[i:Item]].
powerups.json:   what each map powerup gives (start and full-strength values, duration), from misc-data.json.
Nothing is written when the input is missing or yields nothing, so the last good copy stays.
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SINCE = "2026-05-22"  # the big May 2026 update; everything after it


def load(name):
    d = json.load(open(os.path.join(DATA, name), encoding="utf-8"))
    return d if isinstance(d, list) else d.get(name.split(".")[0], d)


heroes = load("heroes.json")
items = load("items.json")
by_class = {i.get("class_name"): i for i in items}
hero_by_name = {h["name"].lower(): h for h in heroes}
for _h in heroes:  # the notes sometimes drop "The" ("Doorman: ...")
    if _h["name"].lower().startswith("the "): hero_by_name.setdefault(_h["name"].lower()[4:], _h)
shop = {}
for i in items:
    if i.get("type") == "upgrade" and i.get("name") and not i.get("disabled"):
        shop.setdefault(i["name"].lower(), i)
abil_any = {}
for i in items:
    if i.get("type") == "ability" and i.get("name"):
        abil_any.setdefault(i["name"].lower(), i)


def hero_abilities(h):
    out = {}
    for v in (h.get("items") or {}).values():
        it = by_class.get(v)
        if it and it.get("type") == "ability" and it.get("name"):
            out[it["name"].lower()] = it
    return out


def inline(s):
    """Wiki markup to text with [[h:..]] [[a:..]] [[i:..]] tokens."""
    s = re.sub(r"\{\{Change\|[^}]*\}\}\s*", "", s)
    s = re.sub(r"\{\{HeroIcon\|([^}|]+)[^}]*\}\}", r"[[h:\1]]", s)
    s = re.sub(r"\{\{AbilityIcon\|([^}|]+)[^}]*\}\}", r"[[a:\1]]", s)
    s = re.sub(r"\{\{ItemIcon\|([^}|]+)[^}]*\}\}", r"[[i:\1]]", s)
    s = re.sub(r"\[\[(?![hai]:)(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", s)  # ordinary wiki links: just the text
    s = re.sub(r"\{\{[^}]*\}\}", "", s)
    s = re.sub(r"'{2,}", "", s)
    return re.sub(r"\s+", " ", s).strip()


def bullets(text):
    """'* x' / '** y' lines as (depth, text)."""
    out = []
    for ln in text.split("\n"):
        m = re.match(r"\s*(\*+)\s*(.*)", ln)
        if m and m.group(2).strip():
            out.append((len(m.group(1)), m.group(2)))
    return out


def parse_patch(date, txt):
    meta = dict(re.findall(r"^\|\s*(source|source_title)\s*=\s*(.*)$", txt, re.M))
    body = txt.split("| notes =", 1)[1] if "| notes =" in txt else txt
    patch = {"date": date, "title": meta.get("source_title", "").strip(), "source": meta.get("source", "").strip(),
             "general": [], "brawl": [], "items": [], "heroes": []}
    # top-level sections; text before the first "==" heading (or under "=== General ===") is general notes
    parts = re.split(r"^==\s*(?!=)(.+?)\s*==\s*$", body, flags=re.M)
    chunks = [("General", parts[0])] + list(zip(parts[1::2], parts[2::2]))
    for title, chunk in chunks:
        t = inline(title).lower()
        if "hero" in t:
            for blk in re.findall(r"\{\{HeroChanges(.*?)\n\}\}", chunk, re.S):
                hn = (re.search(r"\|hero=([^\n|]+)", blk) or [None, ""])[1].strip()
                h = hero_by_name.get(hn.lower())
                ent = {"hero": hn, "hc": h["class_name"] if h else None, "groups": []}
                habs = hero_abilities(h) if h else {}
                grp = None
                for depth, line in bullets(blk.split("|changes=", 1)[-1]):
                    if depth == 1:
                        a = re.match(r"\{\{AbilityIcon\|([^}|]+)[^}]*\}\}\s*$", line.strip())
                        if a:
                            nm = a.group(1).strip(); ab = habs.get(nm.lower()) or abil_any.get(nm.lower())
                            grp = {"ability": nm, "ac": ab["class_name"] if ab else None, "lines": []}
                        elif re.fullmatch(r"'''[^']+'''", line.strip()):
                            grp = {"label": inline(line), "lines": []}
                        else:  # a one-line change with no sub-points
                            grp = {"label": "", "lines": [inline(line)]}
                        ent["groups"].append(grp)
                    elif grp is not None:
                        grp["lines"].append(("  " * (depth - 2)) + inline(line))
                ent["groups"] = [g for g in ent["groups"] if g["lines"]]
                if ent["groups"]: patch["heroes"].append(ent)
        elif "item" in t:
            cur = None
            for ln in chunk.split("\n"):
                m = re.match(r"\s*===\s*(.+?)\s*===\s*$", ln)
                if m:
                    im = re.search(r"\{\{ItemIcon\|([^}|]+)", m.group(1))
                    nm = im.group(1).strip() if im else inline(m.group(1))
                    it = shop.get(nm.lower())
                    cur = {"item": nm, "ic": it["class_name"] if it else None, "lines": []}
                    patch["items"].append(cur); continue
                b = re.match(r"\s*(\*+)\s*(.*)", ln)
                if b and b.group(2).strip():
                    line = ("  " * (len(b.group(1)) - 1)) + inline(b.group(2))
                    if cur is None:
                        cur = {"item": "", "ic": None, "lines": []}; patch["items"].append(cur)
                    cur["lines"].append(line)
        elif "street brawl" in t:
            patch["brawl"] += [("  " * (d - 1)) + inline(x) for d, x in bullets(chunk)]
        elif t in ("general", "") or "general" in t or "misc" in t or "map" in t:
            flat(patch, chunk)
        else:  # any other section: keep it, titled, with the general notes
            ls = [("  " * (d - 1)) + inline(x) for d, x in bullets(chunk)]
            if ls: patch["general"] += ["## " + inline(title)] + ls
    return patch


def add_hero_line(patch, hn, ab, line):
    h = hero_by_name.get(hn.lower())
    ent = next((x for x in patch["heroes"] if x["hero"].lower() == hn.lower()), None)
    if not ent:
        ent = {"hero": hn, "hc": h["class_name"] if h else None, "groups": []}; patch["heroes"].append(ent)
    if ab:
        a = (hero_abilities(h) if h else {}).get(ab.lower()) or abil_any.get(ab.lower())
        grp = next((g for g in ent["groups"] if g.get("ability", "").lower() == ab.lower()), None)
        if not grp: grp = {"ability": ab, "ac": a["class_name"] if a else None, "lines": []}; ent["groups"].append(grp)
    else:
        grp = next((g for g in ent["groups"] if g.get("label") == "Stats"), None)
        if not grp: grp = {"label": "Stats", "lines": []}; ent["groups"].insert(0, grp)
    grp["lines"].append(line)


def add_item_line(patch, nm, line):
    cur = next((x for x in patch["items"] if x["item"].lower() == nm.lower()), None)
    if not cur:
        it = shop.get(nm.lower()); cur = {"item": nm, "ic": it["class_name"] if it else None, "lines": []}; patch["items"].append(cur)
    cur["lines"].append(line)


def flat(patch, chunk):
    """Older notes: one line per change ('Hero: Ability text', 'Item: text') under === headings."""
    head = ""
    for ln in chunk.split("\n"):
        m = re.match(r"\s*===\s*(.+?)\s*===\s*$", ln)
        if m:
            head = inline(m.group(1)); continue
        b = re.match(r"\s*(\*+)\s*(.*)", ln)
        if not b or not b.group(2).strip(): continue
        depth, raw = len(b.group(1)), b.group(2)
        x = inline(raw)
        hm = re.match(r"\[\[h:([^\]]+)\]\][’']?s?:?\s*(?:\[\[a:([^\]]+)\]\]:?\s*)?(.*)", x)
        im = re.match(r"\[\[i:([^\]]+)\]\]:\s*(.*)", x)
        nm = re.match(r"([A-Z][\w' .&-]{2,40}):\s+(.*)", x)
        hl = head.lower()
        if hm and depth == 1:
            add_hero_line(patch, hm.group(1).strip(), (hm.group(2) or "").strip(), hm.group(3).strip()); continue
        if im and depth == 1:
            add_item_line(patch, im.group(1).strip(), im.group(2).strip()); continue
        if nm and depth == 1 and "item" in hl and nm.group(1).lower() in shop:
            add_item_line(patch, nm.group(1), nm.group(2)); continue
        if nm and depth == 1 and "hero" in hl and nm.group(1).lower() in hero_by_name:
            add_hero_line(patch, nm.group(1), "", nm.group(2)); continue
        if "brawl" in hl:
            patch["brawl"].append(("  " * (depth - 1)) + x); continue
        if head and hl not in ("general",) and not any(l == "## " + head for l in patch["general"]):
            patch["general"].append("## " + head)
        patch["general"].append(("  " * (depth - 1)) + x)


def powerups(repo):
    m = json.load(open(os.path.join(repo, "data", "json", "misc-data.json"), encoding="utf-8"))
    NAMES = {"MODIFIER_VALUE_TECH_POWER": ("Spirit Power", ""), "MODIFIER_VALUE_COOLDOWN_REDUCTION_PERCENTAGE": ("Cooldown Reduction", "%"),
             "MODIFIER_VALUE_FIRE_RATE": ("Fire Rate", "%"), "MODIFIER_VALUE_AMMO_CLIP_SIZE_PERCENT": ("Ammo", "%"),
             "MODIFIER_VALUE_HEALTH_MAX": ("Max Health", ""), "MODIFIER_VALUE_HEALTH_REGEN_PER_SECOND": ("Health Regen", "/s"),
             "MODIFIER_VALUE_STAMINA": ("Max Stamina", ""), "MODIFIER_VALUE_SPRINT_SPEED_BONUS": ("Sprint Speed", " m/s"),
             "MODIFIER_VALUE_ZIP_LINE_SPEED_PERCENTAGE": ("Zipline Speed", "%"), "MODIFIER_VALUE_STAMINA_REGEN_PER_SECOND_PERCENTAGE": ("Stamina Recovery", "%")}
    out = {}
    for key, label in (("casting_powerup_pickup", "Casting Powerup"), ("gun_powerup_pickup", "Gun Powerup"),
                       ("movement_powerup_pickup", "Movement Powerup"), ("survival_powerup_pickup", "Survival Powerup")):
        mo = (m.get(key) or {}).get("Modifer") or {}
        vals = []
        for v in mo.get("ModifierValues") or []:
            nm = NAMES.get(v.get("ModifierValue"))
            if not nm: continue
            lo, hi = float(v.get("valueMin", 0)), float(v.get("valueMax", 0))
            if v.get("ModifierValue") == "MODIFIER_VALUE_SPRINT_SPEED_BONUS": lo, hi = lo / 39.37, hi / 39.37  # game units to metres
            r = lambda x: (("%.1f" % x).rstrip("0").rstrip(".")) if abs(x - round(x)) > 0.05 else str(int(round(x)))
            vals.append({"stat": nm[0], "min": r(lo), "max": r(hi), "unit": nm[1]})
        if vals:
            out[label] = {"duration": mo.get("Duration"), "from_min": mo.get("TimeMin"), "to_min": mo.get("TimeMax"), "values": vals}
    return out


def main():
    if len(sys.argv) < 2 or not os.path.isdir(sys.argv[1]):
        print("usage: wikidata.py <deadlock-data checkout>"); return 1
    repo = sys.argv[1]
    wdir = os.path.join(repo, "data", "changelogs", "wiki")
    patches = []
    for f in sorted(os.listdir(wdir), reverse=True):
        d = f[:-4]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) or d < SINCE: continue
        p = parse_patch(d, open(os.path.join(wdir, f), encoding="utf-8").read())
        if p["general"] or p["items"] or p["heroes"] or p["brawl"]: patches.append(p)
    for p in patches: p.pop("brawl", None)  # Street Brawl changes are left out
    patches = [p for p in patches if p["general"] or p["items"] or p["heroes"]]
    if patches:
        json.dump({"source": "github.com/deadlock-wiki/deadlock-data (MIT)", "patches": patches},
                  open(os.path.join(DATA, "patchnotes.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    pw = powerups(repo)
    if pw:
        json.dump({"source": "github.com/deadlock-wiki/deadlock-data (MIT), misc-data.json", "powerups": pw},
                  open(os.path.join(DATA, "powerups.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    miss = sorted({("hero " + h["hero"]) for p in patches for h in p["heroes"] if not h["hc"]} |
                  {("ability %s (%s)" % (g["ability"], h["hero"])) for p in patches for h in p["heroes"] for g in h["groups"] if "ability" in g and not g["ac"]} |
                  {("item " + i["item"]) for p in patches for i in p["items"] if i["item"] and not i["ic"]})
    print("%d patches since %s; powerups: %s" % (len(patches), SINCE, ", ".join(pw) or "none"))
    print("unmatched (shown without a link):", miss or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
