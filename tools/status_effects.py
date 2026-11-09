#!/usr/bin/env python3
"""Turn the hand-exported deadlock.wiki "Status Effects" page into data/status_effects.json.

Input:  data/wiki_raw/Status_Effects.wikitext  (Special:Export, saved from Safari; see its .meta.json)
Output: data/status_effects.json, every effect with its description and sources, each source matched to
        the game data (hero, ability and item class names) so the app can link it.
Prints a report of how each effect is filed in the app's glossary and anything that did not match.

Run:  python3 tools/status_effects.py
The page is licensed CC BY-SA 4.0 by the Deadlock Wiki contributors (credited in the app footer).
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

# Where each wiki effect lives in the app. A plain variant ("Fire Rate Buff") goes under the base term;
# only genuinely distinct effects get a term of their own (new: true, with the glossary category).
FILE_AS = {
    "Barrier": "barrier", "Fire Rate Buff": "fire-rate", "Health Regeneration": "health-regen",
    "Invincibility": "invulnerable", "Lifesteal": "lifesteal", "Movement Speed Buff": "move-speed",
    "Resistance Buff": "resist", "Spirit Power Buff": "spirit-power", "Stealth": "invisible",
    "Hidden on minimap": "hidden-minimap", "Unstoppable": "unstoppable", "Weapon Damage Buff": "weapon-damage",
    "Bleed": "bleed", "Burn": "burn", "Curse": "curse", "Damage Output Reduction": "damage-reduction",
    "Disarm": "disarm", "Displace": "displace", "Healing Reduction": "healing-reduction",
    "Immobilized": "immobilize", "Movement Silence": "movement-silence", "Movement Slow": "slow",
    "Silence": "silence", "Sleep": "sleep", "Stun": "stun", "Time Stop": "time-slow",  # the wiki: "also known as Time Slow"
    # hero-specific effects: each its own term
    "Affliction": "affliction", "Eternal Night": "eternal-night", "Fixation": "fixation", "Hotel Guest": "hotel-guest",
    "Lethal Venom": "lethal-venom", "Marked for Lifesteal": "marked-lifesteal", "Malice": "malice",
    "Parry Prevention": "parry-prevention", "Petrified": "petrified", "Rabbit Hex": "rabbit-hex",
    "Tether": "tether", "Wrecked": "wrecked",
    # countering debuffs
    "Purge": "purge", "Debuff Resistance (Stat)": "debuff-resist",
}
# "Resistance Buff" is split by what each source actually raises (game data): bullet_armor_up / tech_armor_up
RESIST_SPLIT = {"bullet_armor_up": "bullet-resist", "tech_armor_up": "spirit-resist"}
HERO_FIX = {"Silver (Transformed)": "Silver"}
ABIL_FIX = {"Tornado": "Dust Devil"}  # renamed in the game since the wiki page was written


def load(name):
    d = json.load(open(os.path.join(DATA, name), encoding="utf-8"))
    return d if isinstance(d, list) else d.get(name.split(".")[0], d)


def plain(s):
    """Wikitext to readable text, keeping hero/ability/item names."""
    s = re.sub(r"\{\{(?:HeroIcon|AbilityIcon|ItemIcon)\|([^}|]+)[^}]*\}\}", r"\1", s)
    s = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", s)
    s = re.sub(r"\{\{[^}]*\}\}", "", s)
    s = re.sub(r"'{2,}", "", s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    wt = open(os.path.join(DATA, "wiki_raw", "Status_Effects.wikitext"), encoding="utf-8").read()
    meta = json.load(open(os.path.join(DATA, "wiki_raw", "Status_Effects.meta.json"), encoding="utf-8"))
    heroes = load("heroes.json")
    items = load("items.json")
    hero_by_name = {h["name"]: h for h in heroes}
    by_class = {i.get("class_name"): i for i in items}
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

    missing = []

    def source(line):
        line = line.strip()
        hero = re.search(r"\{\{HeroIcon\|([^}|]+)", line)
        abil = re.findall(r"\{\{AbilityIcon\|([^}|]+)", line)
        item = re.search(r"\{\{ItemIcon\|([^}|]+)", line)
        rest = re.sub(r"\{\{(?:HeroIcon|AbilityIcon|ItemIcon)\|[^}]*\}\}('s|')?", "", line)
        note = re.sub(r"^[’']s?\s*", "", plain(rest)).strip(" -,")
        if re.fullmatch(r"(\([^()]*\)\s*)+", note): note = " · ".join(re.findall(r"\(([^()]*)\)", note))  # "(Tier 3) (Bullet Lifesteal)" -> "Tier 3 · Bullet Lifesteal"
        s = {"note": note} if note else {}
        if hero:
            hn = HERO_FIX.get(hero.group(1).strip(), hero.group(1).strip())
            h = hero_by_name.get(hn)
            s["hero"] = hn
            if h: s["hc"] = h["class_name"]
            else: missing.append("hero " + hn)
            if abil:
                ab = ABIL_FIX.get(abil[0].strip(), abil[0].strip()); s["ability"] = ab
                a = (hero_abilities(h) if h else {}).get(ab.lower()) or abil_any.get(ab.lower())
                if a: s["ac"] = a["class_name"]
                else: missing.append("ability %s (%s)" % (ab, hn))
                if len(abil) > 1: s["also"] = [x.strip() for x in abil[1:]]
            elif not note:
                s["note"] = "ability of the same name"
        elif item:
            nm = item.group(1).strip(); s["item"] = nm
            it = shop.get(nm.lower())
            if it: s["ic"] = it["class_name"]
            else: missing.append("item " + nm)
        elif abil:  # an ability named without its hero
            ab = abil[0].strip(); s["ability"] = ab
            a = abil_any.get(ab.lower())
            if a: s["ac"] = a["class_name"]
            else: missing.append("ability " + ab)
        else:
            s = {"text": plain(line)}
        return s

    effects = []
    part = None
    for blk in re.split(r"\n(?==)", wt):
        m = re.match(r"(==+)\s*(.+?)\s*==+", blk)
        if not m: continue
        lvl, title = len(m.group(1)), m.group(2)
        if lvl == 2:
            part = title; continue
        if title not in FILE_AS: continue
        body = blk[m.end():]
        box = re.search(r"\{\{StatusBox[^}]*\}\}", wt[:wt.index(blk)][-400:] if blk in wt else "")
        desc, sources, notes, adjacent, mode = [], [], [], [], "desc"
        for ln in body.split("\n"):
            s = ln.strip()
            if not s or s.startswith("{{StatusBox") or s.startswith("{{Main"): continue
            if s.startswith("'''Sources:'''"): mode = "src"; continue
            if s.startswith("{|") or s in ("|-", "|}"): mode = "src"; continue
            if s.startswith("|") and "||" in s:  # a table row: source || yes/no (removes debuffs from ultimates)
                cells = [c.strip() for c in s.lstrip("|").split("||")]
                x = source(cells[0])
                if len(cells) > 1 and cells[1].lower() == "yes": x["note"] = ((x.get("note") or "") + " · also ultimate debuffs").strip(" ·")
                sources.append(x); continue
            if s.startswith("'''Adjacent Effects:'''"): mode = "adj"; continue
            if s.startswith("*") and mode == "desc" and part != "Countering Debuffs" and not re.search(r"\{\{(HeroIcon|ItemIcon|AbilityIcon)\|", s):
                notes.append(plain(s.lstrip("* ")))
            elif s.startswith("*"):
                x = source(s.lstrip("* "))
                if set(x) == {"text"} and x["text"].endswith(".") and len(x["text"].split()) > 6: notes.append(x["text"])  # a rule about the effect, not a source
                else: (sources if mode != "adj" else adjacent).append(x)
            elif mode == "desc": desc.append(plain(s))
            else: notes.append(plain(s))
        kind = "hero" if part == "Hero Specific Effects" else ("buff" if part == "Buffs" else "debuff")
        if kind == "hero" and not sources:
            raw = " ".join(l for l in body.split("\n") if l.strip() and not l.strip().startswith("{{"))
            hm = re.search(r"\{\{HeroIcon\|[^}]+\}\}('s|')?\s*(\{\{AbilityIcon\|[^}]+\}\})?", raw)
            if hm:
                line = hm.group(0) if hm.group(2) else hm.group(0).rstrip("'s ") + "'s {{AbilityIcon|" + title + "}}"  # "ability of the same name"
                sources.append(source(line))
        icon = re.search(r"status icon=([^|}]+)", box.group(0)).group(1).strip() if box and "status icon=" in box.group(0) else None
        gone = [x for x in sources if ("item" in x and "ic" not in x) or ("ability" in x and "ac" not in x)]
        sources = [x for x in sources if x not in gone]
        if part == "Countering Debuffs": kind = "counter"
        rec = {"name": title, "kind": kind, "term": FILE_AS[title], "icon": icon,
               "desc": " ".join(desc), "sources": sources, "dropped": [x.get("item") or x.get("ability") for x in gone], "notes": notes, "adjacent": adjacent}
        if title == "Resistance Buff":
            split = {t: [] for t in list(RESIST_SPLIT.values()) + ["debuff-resist"]}
            for x in sources:
                # the wiki's own note says what it raises; then the stat's category; then the stat's name
                note, kinds = (x.get("note") or "").lower(), set()
                if "debuff" in note: kinds = {"debuff-resist"}
                elif "bullet" in note: kinds = {"bullet-resist"}
                elif "spirit" in note: kinds = {"spirit-resist"}
                if not kinds:
                    props = [p for p in ((by_class.get(x.get("ac") or x.get("ic")) or {}).get("properties") or {}).items() if isinstance(p[1], dict)]
                    kinds = {RESIST_SPLIT[p["css_class"]] for k, p in props if p.get("css_class") in RESIST_SPLIT}
                    if not kinds:
                        for k, p in props:
                            lab = (k + " " + str(p.get("label") or "")).lower()
                            if "bulletresist" in lab.replace(" ", "") or "bullet resist" in lab: kinds.add("bullet-resist")
                            if "techresist" in lab.replace(" ", "") or "spirit resist" in lab: kinds.add("spirit-resist")
                if not kinds: kinds = set(RESIST_SPLIT.values())  # general damage reduction: both
                for t in kinds: split[t].append(x)
            for t, xs in split.items():
                effects.append(dict(rec, term=t, sources=xs))
        else:
            effects.append(rec)

    out = {"source": "deadlock.wiki/Status_Effects", "revid": meta.get("revid"), "timestamp": meta.get("timestamp"),
           "license": "CC BY-SA 4.0, Deadlock Wiki contributors", "effects": effects}
    json.dump(out, open(os.path.join(DATA, "status_effects.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("%d effects, %d sources" % (len(effects), sum(len(e["sources"]) for e in effects)))
    for e in effects:
        n = len(e["sources"]); linked = sum(1 for s in e["sources"] if s.get("ac") or s.get("ic") or (s.get("hc") and "ability" not in s))
        print("  %-24s %-6s -> %-18s %2d sources (%d linked)" % (e["name"], e["kind"], e["term"], n, linked))
    print("unmatched:", sorted(set(missing)) or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
