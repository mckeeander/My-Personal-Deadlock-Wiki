"""The daily job's safety net: open the site in a headless browser on today's data and make sure every page still works.

Checks that every data file parses, that the hero and item counts haven't collapsed, and that every hero page, shop item,
shop tab, the glossary and search all render with nothing missing or broken. If any check fails it exits 1 and writes a
one-line reason to check_result.txt, and the job keeps yesterday's data instead.

usage: check.py [SITE_DIR]   (needs: pip install playwright; uses the runner's Google Chrome, no browser download)
"""
import functools, glob, http.server, json, os, shutil, subprocess, sys, threading

SITE = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
DATA = os.path.join(SITE, "data")
RESULT = os.path.join(SITE, "check_result.txt")
MIN_HEROES, MIN_SHOP = 30, 150


def fail(problems):
    msg = problems[0] if len(problems) == 1 else "%s (and %d more problem%s)" % (problems[0], len(problems) - 1, "" if len(problems) == 2 else "s")
    open(RESULT, "w").write(msg + "\n")
    print("CHECK FAILED:\n  " + "\n  ".join(problems[:40]))
    sys.exit(1)


def last_count(name):
    """How many entries yesterday's committed copy had, so a sudden drop stands out."""
    try:
        out = subprocess.run(["git", "-C", SITE, "show", "HEAD:data/" + name], capture_output=True, check=True).stdout
        return len(json.loads(out))
    except Exception:
        return 0


def main():
    problems = []
    for f in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        try: json.load(open(f, encoding="utf-8"))
        except Exception as e: problems.append("%s doesn't parse (%s)" % (os.path.basename(f), str(e)[:60]))
    if problems: fail(problems)

    heroes = json.load(open(os.path.join(DATA, "heroes.json")))
    items = json.load(open(os.path.join(DATA, "items.json")))
    for name, now in (("heroes.json", len(heroes)), ("items.json", len(items))):
        before = last_count(name)
        if before and now < before * 0.9:
            problems.append("%s shrank from %d to %d entries" % (name, before, now))
    if problems: fail(problems)

    from playwright.sync_api import sync_playwright
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    handler = functools.partial(Quiet, directory=SITE)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d/" % srv.server_address[1]
    chrome = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=chrome, args=["--no-sandbox"]) if chrome else p.chromium.launch()
        pg = b.new_context(viewport={"width": 402, "height": 874}, is_mobile=True, has_touch=True).new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)[:160]))

        def route(r):  # the page reads data from raw.githubusercontent.com: serve today's local files instead; no outside requests
            u = r.request.url
            if "raw.githubusercontent.com" in u and "/data/" in u:
                path = os.path.join(DATA, u.split("/data/")[1].split("?")[0])
                return r.fulfill(path=path) if os.path.exists(path) else r.fulfill(status=404, body="")
            if u.startswith(base): return r.continue_()
            return r.abort()
        pg.route("**/*", route)
        pg.goto(base + "index.html")
        try:
            pg.wait_for_function("window.state && state.heroes && state.heroes.length > 0 && document.querySelector('#main .hg')", timeout=60000)
        except Exception:
            fail(["the hero list never appeared" + (": " + errors[0] if errors else "")])
        pg.wait_for_timeout(1500)

        found = pg.evaluate("""(async () => {
          var bad = [], BROKEN = /undefined|NaN|\\[object |Infinity/;
          function txt(sel) { var e = document.querySelector(sel); return e ? e.textContent : ""; }
          var hs = state.heroes, shop = state.items.filter(function (i) { return i.type === "upgrade" && i.shopable !== false && !i.disabled; });
          if (hs.length < %d) bad.push("only " + hs.length + " heroes");
          if (shop.length < %d) bad.push("only " + shop.length + " shop items");
          for (const h of hs) {
            try { state.tab = "heroes"; state.hero = h.class_name; render(); } catch (e) { bad.push(h.name + ": page broke (" + e.message + ")"); continue; }
            document.querySelectorAll("#main details").forEach(function (d) { d.open = true; });
            var m = document.querySelector("#main"), t = m.textContent;
            var cards = m.querySelectorAll("section.ab").length, rows = m.querySelectorAll("#stats1 .scd, #stats1 .sctb, #stats1 .srow").length; // stat cards and shared tiles (the old list's rows too)
            if (cards < 4) bad.push(h.name + ": " + cards + " ability cards");
            if (rows < 8) bad.push(h.name + ": " + rows + " base stats");
            if (!m.querySelector("section.wpn")) bad.push(h.name + ": no weapon card");
            var hit = t.match(BROKEN); if (hit) bad.push(h.name + ": shows '" + hit[0] + "'");
            var thin = Array.prototype.filter.call(m.querySelectorAll("section.ab"), function (s) { var d = s.querySelector(".desc"); return !d || d.textContent.trim().length < 15; });
            if (thin.length) bad.push(h.name + ": " + thin.length + (thin.length === 1 ? " ability" : " abilities") + " with no description");
          }
          state.hero = null;
          for (const it of shop) {
            try { var d = document.createElement("div"); d.innerHTML = itemBodyHtml(it); var t = d.textContent;
              if (t.trim().length < 40) bad.push(it.name + ": item card nearly empty");
              var hit = t.match(BROKEN); if (hit) bad.push(it.name + ": shows '" + hit[0] + "'");
            } catch (e) { bad.push(it.name + ": item card broke (" + e.message + ")"); }
          }
          for (const t of ["weapon", "vitality", "spirit"]) {
            try { state.tab = t; render(); var n = document.querySelectorAll("#main button.it2").length; if (n < 30) bad.push(t + " shop shows " + n + " items"); }
            catch (e) { bad.push(t + " shop broke (" + e.message + ")"); }
          }
          try { state.tab = "glossary"; render(); if (txt("#main").length < 500) bad.push("glossary nearly empty"); } catch (e) { bad.push("glossary broke (" + e.message + ")"); }
          try { state.sidx = null; if (buildSearch().length < hs.length * 4) bad.push("search index too small"); } catch (e) { bad.push("search broke (" + e.message + ")"); }
          state.tab = "heroes"; render();
          return bad;
        })()""" % (MIN_HEROES, MIN_SHOP))
        b.close()
    srv.shutdown()
    problems = found + ["page error: " + e for e in errors]
    if problems: fail(problems)
    open(RESULT, "w").write("ok\n")
    print("check: ok (%d heroes, %d items)" % (len(heroes), len(items)))


if __name__ == "__main__":
    main()
