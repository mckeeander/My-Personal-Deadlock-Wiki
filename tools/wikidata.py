#!/usr/bin/env python3
"""Build data/patchnotes.json and data/powerups.json from a checkout of github.com/deadlock-wiki/deadlock-data (MIT).

    python3 tools/wikidata.py <path to deadlock-data checkout>

patchnotes.json: official patch notes since SINCE (newest first), split into general notes, items and heroes, with
                 every hero, ability and item matched to the game data's class names so the app can link them.
                 Inline names are kept as tokens: [[h:Hero]] [[a:Ability]] [[i:Item]].
powerups.json:   what each map powerup gives (start and full-strength values, duration), from misc-data.json.
Nothing is written when the input is missing or yields nothing, so the last good copy stays.

The wiki adds a patch's notes by hand, sometimes a day or more after the patch. Until it does, the official notes are
read from Steam (the game's patch-note announcements) and turned into the same layout; once the wiki has that date,
its copy is used instead.
"""
import json, os, re, sys, time, urllib.request

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


STEAM_NEWS = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=1422450&count=15&maxlength=0&feeds=steam_community_announcements"


def steam_patches(have):
    """{date: wiki-layout text} for official patch notes on Steam whose date the wiki doesn't have yet."""
    try:
        req = urllib.request.Request(STEAM_NEWS, headers={"User-Agent": "personal-deadlock-wiki (data update)"})
        news = json.load(urllib.request.urlopen(req, timeout=30))["appnews"]["newsitems"]
    except Exception as e:
        print("steam news unavailable:", e); return {}
    out = {}
    for n in news:
        title = n.get("title") or ""
        if "patchnotes" not in (n.get("tags") or []) and not re.search(r"\bupdate\b", title, re.I): continue
        m = re.search(r"(\d{2})-(\d{2})-(\d{4})", title)  # "Minor Update - 11-26-2026"
        date = "%s-%s-%s" % (m.group(3), m.group(1), m.group(2)) if m else time.strftime("%Y-%m-%d", time.gmtime(n.get("date") or 0))
        if date in have or date in out or date < SINCE: continue
        txt = steam_to_wiki(n.get("contents") or "", title, n.get("url") or "")
        if txt: out[date] = txt
    return out


def steam_to_wiki(c, title, url):
    r"""Steam's BBCode notes in the wiki's Update layout. Section headings come as "[b]\[ Heroes ][/b]" or "[b]Heroes:[/b]";
    changes as "- Abrams: Shoulder Charge - text" and "- Capacitor: text". Lines before the first heading (the flavour text) are left out."""
    c = re.sub(r"\[/?(p|list|\*)\]", "\n", c).replace("\\[", "[").replace("\\]", "]")
    secs, sec, its, hs = [], None, {}, {}
    for raw in c.split("\n"):
        h = re.match(r"\s*\[(b|h[1-6])\]\s*\[?\s*(.+?)\s*\]?\s*:?\s*\[/\1\]\s*$", raw)
        if h: sec = h.group(2).strip().rstrip(":").strip(); secs.append((sec, [])); continue
        ln = re.sub(r"\[/?[a-z0-9]+(=[^\]]*)?\]", "", raw).strip()
        b = re.match(r"[-•]\s+(.*)", ln)
        if not b or sec is None: continue
        t, sl = b.group(1).strip(), sec.lower()
        if "hero" in sl:
            m = re.match(r"([^:]{2,30}):\s*(.*)", t)
            hero = hero_by_name.get(m.group(1).strip().lower()) if m else None
            if not hero: secs[-1][1].append(t); continue
            rest = m.group(2)
            a = re.match(r"(.{2,40}?)\s+-\s+(.*)", rest)
            ab = a.group(1).strip() if a and (a.group(1).strip().lower() in hero_abilities(hero) or a.group(1).strip().lower() in abil_any) else ""
            hs.setdefault(hero["name"], {}).setdefault(ab, []).append(a.group(2).strip() if ab else rest)
        elif "item" in sl:
            m = re.match(r"([^:]{2,40}):\s*(.*)", t)
            its.setdefault(m.group(1).strip() if m else "", []).append(m.group(2).strip() if m else t)
        else:
            secs[-1][1].append(t)
    if not (its or hs or any(ls for _, ls in secs)): return ""
    out = ["| source = " + url, "| source_title = " + title, "| notes ="]
    for nm, ls in secs:  # general and any other titled section (Street Brawl is dropped by the reader)
        if ls and "hero" not in nm.lower() and "item" not in nm.lower():
            out.append("== %s ==" % ("General" if re.search(r"general|gameplay update", nm, re.I) else nm)); out += ["* " + x for x in ls]
    if its:
        out.append("== Items ==")
        for nm, ls in its.items():
            if nm: out.append("=== {{ItemIcon|%s}} ===" % nm)
            out += ["* " + x for x in ls]
    if hs:
        out.append("== Heroes ==")
        for nm, groups in hs.items():
            out += ["{{HeroChanges", "|hero=" + nm, "|changes="]
            for ab, ls in sorted(groups.items(), key=lambda g: g[0] != ""):  # base stats first
                out.append("* {{AbilityIcon|%s}}" % ab if ab else "* '''Stats'''")
                out += ["** " + x for x in ls]
            out.append("}}")
    return "\n".join(out) + "\n"


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
    # some pages repeat a block of notes (a reply post quoting the original), and notes filed under an ability
    # lose its name, so "Siphon Life range increased" became "range increased": drop repeats, capitalise
    for x in [g for e in patch["heroes"] for g in e["groups"]] + patch["items"]:
        x["lines"] = tidy(x["lines"])
    patch["general"] = tidy(patch["general"])
    return patch


def tidy(lines):
    out, seen = [], set()
    for ln in lines:
        body = ln.lstrip(" ")
        if re.match(r"[a-z]+\b(?![_.(])", body): ln = ln[:len(ln) - len(body)] + body[0].upper() + body[1:]
        if ln in seen: continue
        seen.add(ln); out.append(ln)
    return out


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


def crates(repo):
    """Permanent pickups from breakable crates: the value at each level and when each level starts dropping."""
    m = json.load(open(os.path.join(repo, "data", "json", "misc-data.json"), encoding="utf-8"))
    g = json.load(open(os.path.join(repo, "data", "json", "generic-data.json"), encoding="utf-8"))
    TYPES = {"spirit": ("Spirit Power", ""), "firerate": ("Fire Rate", "%"), "ammo": ("Ammo", "%"), "hp": ("Max Health", ""),
             "cd": ("Cooldown Reduction", "%"), "wp": ("Weapon Damage", "%"), "bulletresist": ("Bullet Resist", "%"),
             "spiritresist": ("Spirit Resist", "%"), "range": ("Ability Range", "%"), "movespeed": ("Move Speed", " m/s")}
    loot = (g.get("BreakablePowerupLootParams") or {}).get("PickupsByMatchTimeMins") or {}
    starts = sorted(int(k) for k in loot)
    out = {}
    for t, (stat, unit) in TYPES.items():
        vals, weight = [], None
        for suf in ("", "_lv2", "_lv3"):
            sv = ((m.get(t + "_permanent_pickup" + suf) or {}).get("Modifer") or {}).get("ScriptValues") or []
            v = float(sv[0]["value"]) if sv and "value" in sv[0] else None
            if v is not None and t == "movespeed": v = v / 39.37  # game units to metres
            vals.append(None if v is None else (("%.2f" % v).rstrip("0").rstrip(".")))
        if loot: weight = (loot.get(str(starts[0])) or {}).get(t + "_permanent_pickup")
        if any(vals): out[stat] = {"values": vals, "unit": unit, "weight": weight}
    return {"levels_from_min": starts, "spawns": g.get("BreakableSpawnTimeDesc"), "pickups": out} if out else None


def mechanics(repo):
    """Objectives and neutrals: only fields whose meaning is clear (health, souls, spawn times, backdoor protection)."""
    J = lambda f: json.load(open(os.path.join(repo, "data", "json", f), encoding="utf-8"))
    n, g = J("npc-data.json"), J("generic-data.json")
    op, rj = g.get("ObjectiveParams") or {}, g.get("RejuvParams") or {}
    def num(o, *path):
        for k in path:
            if not isinstance(o, dict) or k not in o: return None
            o = o[k]
        return o if isinstance(o, (int, float)) and not isinstance(o, bool) else None
    bp = (n.get("npc_boss_tier1") or {}).get("BackdoorProtectionModifier") or {}
    mb_mod = ((n.get("npc_super_neutral") or {}).get("IntrinsicModifiers") or [{}])[0] or {}  # the Mid Boss's regen and resists
    try: misc = J("misc-data.json")
    except Exception: misc = {}
    out = {
        "trooper": {"health": num(n, "trooper_normal", "MaxHealth"), "melee_health": num(n, "trooper_melee", "MaxHealth"), "dps_vs_heroes": num(n, "trooper_normal", "VSPlayer", "BaseDPS")},
        "guardian": {"health": num(n, "npc_boss_tier1", "MaxHealth"), "souls": op.get("Tier1GoldKill"), "dps_vs_heroes": num(n, "npc_boss_tier1", "PlayerDPS")},
        "walker": {"health": num(n, "npc_boss_tier2", "MaxHealth"), "souls": op.get("Tier2GoldKill")},
        "base_guardian": {"health": num(n, "npc_barrack_boss", "MaxHealth"), "souls": op.get("BaseGuardiansGoldKill")},
        "shrine": {"souls": op.get("ShrinesGoldKill")},
        "patron": {"health": num(n, "npc_boss_tier3", "MaxHealth"), "phase2_health": num(n, "npc_boss_tier3", "Phase2Health"),
                   "growth1": num(n, "npc_boss_tier3", "ObjectiveHealthGrowthPhase1", "GrowthPerMinute"), "growth1_from_min": num(n, "npc_boss_tier3", "ObjectiveHealthGrowthPhase1", "GrowthStartTimeInMinutes"),
                   "growth2": num(n, "npc_boss_tier3", "ObjectiveHealthGrowthPhase2", "GrowthPerMinute")},
        "mid_boss": {"health": num(n, "npc_super_neutral", "StartingHealth"), "health_per_min": num(n, "npc_super_neutral", "HealthGainPerMinute"),
                     # the shield soaks up this much damage every second, plus the second number for each minute of the match
                     "shield_per_sec": num(n, "npc_super_neutral", "ShieldLogic", "BaseAbsorptionPerSecond"), "shield_per_min": num(n, "npc_super_neutral", "ShieldLogic", "ScalingAbsorptionPerMinute"),
                     "regen": num(mb_mod, "HEALTH_REGEN_PER_SECOND"), "bullet_resist": num(mb_mod, "BULLET_ARMOR_DAMAGE_RESIST"), "spirit_resist": num(mb_mod, "ABILITY_DAMAGE_REDUCTION_PERCENT"),
                     "debuff_resist": num(mb_mod, "STATUS_RESISTANCE"), "shred_resist": num(mb_mod, "RESIST_REDUCTION_RESISTANCE"),
                     "dps": num(n, "npc_super_neutral", "Weapon", "DPS"), "range": num(n, "npc_super_neutral", "Weapon", "FalloffEndRange"),
                     "respawn_sec": num(n, "npc_super_neutral", "SpawnInterval")},
        # the trooper-health and respawn multipliers in RejuvParams are left over from before the Jul/Aug 2025 rework (see patch notes); only the duration is current
        "rejuvenator": {"duration": rj.get("RejuvinatorBuffDuration"), "crystals": rj.get("RejuvinatorDropCount"), "drop_sec": rj.get("RejuvinatorDropDuration"),
                        "revive_health_pct": num(misc, "citadel_item_pickup_rejuv", "RebirthModifier", "RespawnLifePct"),
                        "revive_delay_sec": num(misc, "citadel_item_pickup_rejuv", "RebirthModifier", "RespawnDelay")},
        "mid_boss_first_sec": num(n, "npc_super_neutral", "InitialSpawnDelay"),
        "crate_first_sec": ((g.get("BreakableSpawnTimeDesc") or [{}])[0] or {}).get("InitialSpawnTime"),
        "rift_interval_sec": (lambda c: c.get("citadel_koth_respawn_interval") if isinstance(c.get("citadel_koth_respawn_interval"), (int, float)) else None)(J("convars.json")),
        "backdoor": {"mitigation": bp.get("BackdoorProtectionDamageMitigationFromPlayers"), "regen": bp.get("HealthPerSecondRegen")},
        "camps": [{"tier": i + 1, "health": num(n, k, "MaxHealth"), "souls": num(n, k, "GoldReward"), "from_sec": num(n, k, "InitialSpawnDelay"),
                   "souls_pct_per_min": num(n, k, "GoldRewardBonusPercentPerMinute")}
                  for i, k in enumerate(("neutral_trooper_weak", "neutral_trooper_normal", "neutral_trooper_strong"))],
    }
    cv = J("convars.json")
    c = lambda k: (lambda v: v.get("value") if isinstance(v, dict) else v)(cv.get(k))
    out["economy"] = {"starting_souls": c("citadel_player_starting_gold"), "kill_min": c("citadel_player_gold_reward_min"), "kill_max": c("citadel_player_gold_reward_max"),
                      "kill_ramp_sec": c("citadel_player_gold_reward_time"), "first_kill_bonus": c("citadel_player_gold_reward_first_kill_bonus"),
                      "killer_assist_ratio": c("citadel_player_gold_killer_to_assist_ratio"), "assist_window_sec": c("citadel_bounty_player_assist_window"),
                      "trooper_instant_ratio": c("citadel_trooper_instant_gold_ratio_laning"), "comeback_redirect": c("citadel_comeback_redirect_fraction"),
                      "tick_start_sec": c("citadel_tick_gold_start_time")}
    out["mid_boss"].update({"souls": c("citadel_super_neutral_gold_reward"), "souls_per_min": c("citadel_super_neutral_gold_reward_bonus_per_minute")})
    # the Soul Urn and the Unstable Rift
    kc = (misc or {}).get("citadel_koth_cashin") or {}
    out["urn"] = {"first_sec": c("citadel_crate_spawn_initial_delay"), "respawn_sec": c("citadel_crate_respawn_interval"), "souls": c("citadel_crate_reward_base"), "souls_per_min": c("citadel_crate_reward_time_multiplier")}
    out["rift"] = {"respawn_sec": c("citadel_koth_respawn_interval"), "souls_base": c("citadel_koth_reward_base"), "souls_per_min": c("citadel_koth_reward_time_multiplier"),
                   "capture_sec": kc.get("TotalTimeToCapture"), "capture_sec_behind": kc.get("TotalTimeToCaptureFavored"), "capture_sec_ahead": kc.get("TotalTimeToCaptureUnfavored"),
                   "draw_sec": kc.get("TimeToGiveUp"), "radius_m": round(((kc.get("AuraModifier") or {}).get("AuraRadius") or 0) * 0.0254) or None}
    # trooper waves: the first one, then the gap between waves as the match goes on, and how many troopers come in a squad
    out["trooper"].update({"wave_first_sec": c("citadel_trooper_spawn_initial"), "wave_sec": c("citadel_trooper_spawn_interval_early"),
                           "wave_late_sec": c("citadel_trooper_spawn_interval_late"), "wave_late_min": c("citadel_trooper_spawn_interval_late_time"),
                           "wave_very_late_sec": c("citadel_trooper_spawn_interval_very_late"), "wave_very_late_min": c("citadel_trooper_spawn_interval_very_late_time"),
                           "squad": c("citadel_trooper_squad_size")})
    # walker attacks and trooper types
    w = (n.get("npc_boss_tier2") or {}).get("BoundAbilities") or {}
    ap = lambda slot, k: num(w, slot, "AbilityProperties", k)
    out["walker"].update({"rocket_damage": ap("ESlot_Signature_1", "Damage"), "rocket_cd": ap("ESlot_Signature_1", "AbilityCooldown"),
                          "rocket_fire_dps": ap("ESlot_Signature_1", "FireDPS"), "rocket_fire_sec": ap("ESlot_Signature_1", "FireDuration"),
                          "rocket_shred": ap("ESlot_Signature_1", "BulletArmorReduction"), "laser_dps": ap("ESlot_Signature_2", "DPS"),
                          "laser_maxhp_dps": ap("ESlot_Signature_2", "MaxHPDPS"), "laser_sec": ap("ESlot_Signature_2", "AbilityDuration"),
                          "stomp_cd": ap("ESlot_Signature_3", "AbilityCooldown"), "wave_damage": ap("ESlot_Signature_4", "Damage"),
                          "wave_at_health": num(n, "npc_boss_tier2", "AoeWaveHealthThreshold")})
    md = (n.get("trooper_medic") or {}).get("AOEHealthPickup") or {}
    out["trooper"].update({"medic_health": num(n, "trooper_medic", "MaxHealth"), "medic_heal": md.get("RegenFixed"), "medic_heal_pct": md.get("MissingPctRegen"), "medic_heal_sec": md.get("RegenDuration")})
    # the shop
    out["shop"] = {"tier_prices": [p for p in (g.get("ItemPricePerTier") or []) if p and p < 9000], "sell_ratio": c("citadel_item_sell_price_ratio")}
    # the game's own words when a status effect stops you
    try:
        Lz = json.load(open(os.path.join(repo, "data", "localizations", "english.json"), encoding="utf-8"))
        T = lambda k: re.sub(r"<[^>]+>", "", Lz.get(k) or "") or None
        S = {"stun": ("Citadel_StatusEffectStun", "CITADEL_ABILITY_INVALID_STUNNED"), "sleep": ("Citadel_StatusEffectSleep", "CITADEL_ABILITY_INVALID_ASLEEP"),
             "silence": ("Citadel_StatusEffectSilence", "CITADEL_ABILITY_INVALID_SILENCED"), "disarm": ("Citadel_StatusEffectDisarmed", "CITADEL_ABILITY_INVALID_DISARMED"),
             "immobilize": ("Citadel_StatusEffectImmobilize", "CITADEL_ABILITY_INVALID_ROOTED"), "movement-silence": (None, "CITADEL_ABILITY_INVALID_SILENCE_MOVEMENT_ABILITIES"),
             "curse": ("Citadel_StatusEffectCurse", "CITADEL_ABILITY_INVALID_MUTED"), "displace": ("Citadel_StatusEffectDisplacement", None),
             "petrified": ("Citadel_StatusEffectPetrify", None), "tether": ("Citadel_StatusEffectTethered", None), "bleed": ("Citadel_StatusEffectBleed", None),
             "burn": ("Citadel_StatusEffectBurn", None), "unstoppable": ("Citadel_StatusEffectUnstoppable", None), "invisible": ("Citadel_StatusEffectInvisible", None),
             "stamina": (None, "CITADEL_ABILITY_INVALID_OUT_OF_STAMINA")}
        out["status_text"] = {k: {"name": T(a) if a else None, "msg": T(b) if b else None} for k, (a, b) in S.items() if (a and T(a)) or (b and T(b))}
    except Exception: pass
    try: out["soul_unlocks"] = J("soul-unlock-data.json")
    except Exception: pass
    return out if out["guardian"]["health"] else None


def main():
    if len(sys.argv) < 2 or not os.path.isdir(sys.argv[1]):
        print("usage: wikidata.py <deadlock-data checkout>"); return 1
    repo = sys.argv[1]
    wdir = os.path.join(repo, "data", "changelogs", "wiki")
    texts = {f[:-4]: open(os.path.join(wdir, f), encoding="utf-8").read() for f in os.listdir(wdir) if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.txt", f)}
    fresh = steam_patches(texts)  # notes the wiki hasn't written up yet, straight from Steam
    if fresh: print("from Steam (not on the wiki yet):", ", ".join(sorted(fresh)))
    texts.update(fresh)
    patches = []
    for d in sorted(texts, reverse=True):
        if d < SINCE: continue
        p = parse_patch(d, texts[d])
        if p["general"] or p["items"] or p["heroes"] or p["brawl"]: patches.append(p)
    # every patch since the first wiki entry, per hero and per item, for the patch history on hero pages (and later item pages)
    hist = {"heroes": {}, "items": {}}
    for d in sorted(texts, reverse=True):
        p = parse_patch(d, texts[d])
        gid = re.search(r"steam_community_announcements/(\d+)", p["source"] or "")
        meta = {"date": d, "title": p["title"], "source": ("https://store.steampowered.com/news/app/1422450/view/" + gid.group(1)) if gid else p["source"]}
        for h in p["heroes"]:
            if h["hc"]: hist["heroes"].setdefault(h["hc"], []).append(dict(meta, groups=h["groups"]))
        for it in p["items"]:
            if it["ic"]: hist["items"].setdefault(it["ic"], []).append(dict(meta, lines=it["lines"]))
    if hist["heroes"]:
        json.dump({"source": "github.com/deadlock-wiki/deadlock-data (MIT)", **hist}, open(os.path.join(DATA, "patchhistory.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    for p in patches: p.pop("brawl", None)  # Street Brawl changes are left out
    patches = [p for p in patches if p["general"] or p["items"] or p["heroes"]]
    if patches:
        json.dump({"source": "github.com/deadlock-wiki/deadlock-data (MIT)", "patches": patches},
                  open(os.path.join(DATA, "patchnotes.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    mc = mechanics(repo)
    if mc:
        json.dump({"source": "github.com/deadlock-wiki/deadlock-data (MIT), npc-data.json / generic-data.json", "mechanics": mc},
                  open(os.path.join(DATA, "mechanics.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    pw = powerups(repo)
    cr = crates(repo)
    if pw:
        json.dump({"source": "github.com/deadlock-wiki/deadlock-data (MIT), misc-data.json", "powerups": pw, "crates": cr},
                  open(os.path.join(DATA, "powerups.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    miss = sorted({("hero " + h["hero"]) for p in patches for h in p["heroes"] if not h["hc"]} |
                  {("ability %s (%s)" % (g["ability"], h["hero"])) for p in patches for h in p["heroes"] for g in h["groups"] if "ability" in g and not g["ac"]} |
                  {("item " + i["item"]) for p in patches for i in p["items"] if i["item"] and not i["ic"]})
    print("%d patches since %s; powerups: %s" % (len(patches), SINCE, ", ".join(pw) or "none"))
    print("unmatched (shown without a link):", miss or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
