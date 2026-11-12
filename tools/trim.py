"""Shrink data/heroes.json and data/items.json by dropping what the site never reads, so the phone downloads less each day.

What goes:
- hero fields with no use on the site (Street Brawl draft weights, Valve's own popular-items list, UI layout lists, models, test flags)
- item fields with no use (Corrupted/Broker info, crosshair settings, shop filters, update times, a mislabelled video link)
- inside each ability/item property: engine-only flags (token overrides, property types, tooltip placement flags, Street Brawl values)
- abilities and weapons that belong to no hero (unreleased heroes, test kits), unless something else on the site names them

What stays, though nothing shows it yet, because it could teach something later and is small:
level_info (souls needed per level and what each level unlocks), behaviours (projectile, can't be silenced...),
boss_damage_scale (abilities that do half damage to objectives), colors, physics.

usage: trim.py DATA_DIR
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import itemicons

HERO_DROP = {"item_draft_bucketing", "popular_items", "hero_stats_ui", "stats_display", "item_slot_info", "models",
             "hideout_rich_presence", "search_name", "gender", "assigned_players_only", "limited_testing", "needs_testing",
             "prerelease_only", "purchase_bonuses", "skin"}
ITEM_DROP = {"corrupted_info", "start_trained", "update_time", "custom_crosshair_settings", "use_custom_crosshair_settings",
             "crosshair_css_class", "shop_filters", "disabled_shop_filters", "shop_version", "videos", "grant_ammo_on_cast"}
PROP_DROP = {"can_set_token_override", "provided_property_type", "tooltip_is_important", "tooltip_is_elevated", "tooltip_section",
             "usage_flags", "loc_token_override", "street_brawl_value", "required_upgrade_bits"}
SCALE_DROP = {"subclass_name"}


def dep_names(v):
    """dependent_abilities comes as a list of {class_name: null} maps (sometimes plain names)."""
    out = []
    for d in v or []:
        if isinstance(d, str): out.append(d)
        elif isinstance(d, dict): out.extend(k for k in d.keys() if isinstance(k, str))
    return out


def main(data):
    hp, ip = os.path.join(data, "heroes.json"), os.path.join(data, "items.json")
    heroes, items = json.load(open(hp)), itemicons.expand(json.load(open(ip)), data) # items carried over from yesterday may hold tokens
    size0 = os.path.getsize(hp) + os.path.getsize(ip)

    # every name anything else on the site points at (patch history, revisions, wiki notes, the page itself) keeps its item
    named = ""
    for f in os.listdir(data):
        if f.endswith(".json") and f not in ("heroes.json", "items.json"):
            named += open(os.path.join(data, f), encoding="utf-8").read()
    page = os.path.join(os.path.dirname(os.path.abspath(data)), "index.html")
    if os.path.exists(page): named += open(page, encoding="utf-8").read()

    by = {i.get("class_name"): i for i in items if isinstance(i, dict)}
    keep = set()
    for h in heroes:
        for v in (h.get("items") or {}).values():
            if isinstance(v, str): keep.add(v)
    todo = list(keep)
    while todo:  # an ultimate's alternate form, and that form's own alternates
        for d in dep_names((by.get(todo.pop()) or {}).get("dependent_abilities")):
            if d not in keep: keep.add(d); todo.append(d)

    out, dropped = [], 0
    for i in items:
        cn = i.get("class_name")
        if i.get("type") in ("ability", "weapon") and cn not in keep and ('"' + str(cn) + '"') not in named:
            dropped += 1; continue
        for k in ITEM_DROP: i.pop(k, None)
        for p in (i.get("properties") or {}).values():
            if not isinstance(p, dict): continue
            for k in PROP_DROP: p.pop(k, None)
            if isinstance(p.get("scale_function"), dict):
                for k in SCALE_DROP: p["scale_function"].pop(k, None)
        out.append(i)
    for h in heroes:
        for k in HERO_DROP: h.pop(k, None)

    json.dump(heroes, open(hp, "w"), ensure_ascii=False, separators=(",", ":"))
    out, icons = itemicons.compact(out) # each inline icon stored once, links shortened: about a third smaller to download
    json.dump(out, open(ip, "w"), ensure_ascii=False, separators=(",", ":"))
    json.dump(icons, open(os.path.join(data, "item_icons.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    size1 = os.path.getsize(hp) + os.path.getsize(ip) + os.path.getsize(os.path.join(data, "item_icons.json"))
    print("trim: %.1f MB -> %.1f MB, %d unused abilities/weapons removed" % (size0 / 1e6, size1 / 1e6, dropped))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data")
