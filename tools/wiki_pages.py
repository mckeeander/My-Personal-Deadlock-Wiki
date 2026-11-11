# Saves raw copies of chosen deadlock.wiki pages (rendered HTML and wikitext) plus an index of every
# article and category, so new sections can be built and tested against real content.
# Nothing is overwritten with an empty or failed result: the last good copy stays.
import datetime, json, os, time, urllib.parse, urllib.request

DATA = os.environ.get("DATA_DIR", "data")
RAW = os.path.join(DATA, "wiki_raw")
UA = "DeadlockCodex-personal/1.0 (+https://github.com/mckeeander/My-Personal-Deadlock-Wiki)"
BASES = ["https://deadlock.wiki/api.php", "https://deadlock.wiki/w/api.php"]
PAGES = ["Status Effects", "Mechanics"]  # pages to keep raw copies of; add more here
log = []

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def api(params):
    q = urllib.parse.urlencode(dict(params, format="json", formatversion="2"))
    last = None
    for base in BASES:
        try:
            j = get(base + "?" + q)
            if "error" in j:
                last = base + " -> " + str(j["error"].get("code")); continue
            return j
        except Exception as e:
            last = base + " -> " + repr(e)[:160]
    raise RuntimeError(last)

def listing(params, key):  # follows the API's "continue" until the list is complete
    out, cont = [], {}
    for _ in range(200):
        j = api(dict(params, **cont))
        out += j.get("query", {}).get(key, [])
        if "continue" not in j: break
        cont = j["continue"]; time.sleep(0.5)
    return out

def save(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(text)

def fname(title):
    return "".join(c if c.isalnum() else "_" for c in title).strip("_")

os.makedirs(RAW, exist_ok=True)
# 1. every article (main namespace, no redirects) and every category with its size
try:
    pages = listing({"action": "query", "list": "allpages", "apnamespace": 0, "apfilterredir": "nonredirects", "aplimit": "max"}, "allpages")
    cats = listing({"action": "query", "list": "allcategories", "aclimit": "max", "acprop": "size"}, "allcategories")
    if pages:
        idx = {"updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "deadlock.wiki",
               "pages": sorted(p["title"] for p in pages),
               "categories": sorted(({"name": c.get("category") or c.get("title", ""), "pages": c.get("pages", c.get("size", 0))} for c in cats), key=lambda c: -c["pages"])}
        save(os.path.join(DATA, "wiki_pages.json"), json.dumps(idx, ensure_ascii=False, indent=1))
        log.append("index: %d pages, %d categories" % (len(pages), len(cats)))
    else:
        log.append("index: empty result, kept previous")
except Exception as e:
    log.append("index failed: " + str(e))
# 2. raw copies of the chosen pages
for t in PAGES:
    try:
        j = api({"action": "parse", "page": t, "redirects": 1, "prop": "text|wikitext|categories|sections", "disableeditsection": 1})
        p = j.get("parse", {})
        if p.get("text") and p.get("wikitext"):
            base = os.path.join(RAW, fname(t))
            save(base + ".html", p["text"])
            save(base + ".wikitext", p["wikitext"])
            save(base + ".meta.json", json.dumps({"title": p.get("title"), "revid": p.get("revid"),
                 "categories": [c.get("category") for c in p.get("categories", [])],
                 "sections": [s.get("line") for s in p.get("sections", [])]}, ensure_ascii=False, indent=1))
            log.append("%s: html %d chars, wikitext %d chars, %d sections" % (t, len(p["text"]), len(p["wikitext"]), len(p.get("sections", []))))
        else:
            log.append("%s: no content, kept previous" % t)
    except Exception as e:
        log.append("%s failed: %s" % (t, e))
    time.sleep(1.2)
save(os.path.join(RAW, "log.txt"), "\n".join(log) + "\n")
print("\n".join(log))
