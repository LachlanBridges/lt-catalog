from pathlib import Path
from datetime import datetime
import argparse
import re

from playwright.sync_api import sync_playwright

SECRETS_DIR = Path(__file__).parent.parent / "secrets"
OUTDIR = Path(__file__).parent.parent / "exports"

STATE = SECRETS_DIR / ".state.json"
EXPORT_URL = "https://www.librarything.com/export.php"

def sanitize(s: str) -> str:
    s = s.strip()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^A-Za-z0-9._,-]+", "", s)
    return s.lower()

def build_filename(fmt: str, since: str | None, collections: list[str] | None,
                   tags: list[str] | None, search: str | None) -> str:
    parts = ["lt-export"]
    if since:
        parts.append(f"since-{sanitize(since)}")
    else:
        parts.append("full")
    if collections:
        parts.append("col-" + sanitize(",".join(collections)))
    if tags:
        parts.append("tags-" + sanitize(",".join(tags)))
    if search:
        # keep first ~5 words to avoid novels
        snippet = " ".join(search.split()[:5])
        parts.append("search-" + sanitize(snippet))
    parts.append(fmt)
    return "_".join(parts) + (".json" if fmt == "json" else ".marc")

def pick_collections(page, collections: list[str] | None):
    """
    collections: list of visible labels to select, e.g. ["Owned","Your library"] or ["all"]
    If None: leave defaults as-is.
    """
    # Find the select that handles collections (name often like 'collections[]')
    sel = page.locator("select[name*='collection']")
    if not sel.first.count():
        return  # nothing we can do; page may default to all
    select = sel.first

    # Read options: text -> value
    options = select.locator("option")
    vals = []
    labels = []
    for i in range(options.count()):
        opt = options.nth(i)
        val = opt.get_attribute("value") or ""
        lab = (opt.text_content() or "").strip()
        if val:
            vals.append(val)
            labels.append(lab)

    if not collections:
        return

    if len(collections) == 1 and collections[0].lower() == "all":
        select.select_option([v for v in vals])
        return

    wanted = []
    wantset = {c.strip().lower() for c in collections}
    # match by visible label first
    for v, lab in zip(vals, labels):
        if lab.strip().lower() in wantset:
            wanted.append(v)
    # also allow passing raw values like "1"
    for c in collections:
        if c in vals and c not in wanted:
            wanted.append(c)

    if wanted:
        select.select_option(wanted)

def run_export(fmt="json", since=None, collections=None, tags=None, search=None, headed=False):
    if not STATE.exists():
        raise SystemExit(f".state.json not found at {STATE}. Run your state capture first.")
    OUTDIR.mkdir(parents=True, exist_ok=True)

    out_name = build_filename(fmt, since, collections, tags, search)
    out_path = OUTDIR / out_name

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed, channel="msedge")
        ctx = browser.new_context(storage_state=str(STATE))
        page = ctx.new_page()
        page.goto(EXPORT_URL, wait_until="domcontentloaded")

        # since (date) — a few likely names
        if since:
            for sel in ["input[name='entered_since']", "#entered_since", "input[name='books_entered_since']"]:
                if page.locator(sel).first.count():
                    page.fill(sel, since)
                    break

        # search (free-text)
        if search:
            for sel in ["input[name='search']", "#search", "input[name='q']"]:
                if page.locator(sel).first.count():
                    page.fill(sel, search)
                    break

        # tags (comma-separated in UI) — we’ll just fill whatever tag box exists
        if tags and len(tags):
            tags_str = ", ".join(tags)
            for sel in ["input[name='tags']", "#tags", "input[name='tags_filter']"]:
                if page.locator(sel).first.count():
                    page.fill(sel, tags_str)
                    break

        # collections (multi-select by visible label or value)
        if collections:
            pick_collections(page, collections)

        # format
        set_fmt = False
        if page.locator("select[name='export_format']").first.count():
            page.select_option("select[name='export_format']", value=fmt)
            set_fmt = True
        else:
            for r in (f"input[name='export_format'][value='{fmt}']",
                      f"input[type='radio'][value='{fmt}']"):
                if page.locator(r).first.count():
                    page.locator(r).first.check()
                    set_fmt = True
                    break
        # if not set, page usually defaults to JSON

        # submit export job
        clicked = False
        for sel in ("input[type='submit'][value*='Export']", "button:has-text('Export')"):
            if page.locator(sel).first.count():
                page.locator(sel).first.click(); clicked = True; break
        if not clicked:
            page.locator("form").first.evaluate("f => f.submit()")

        # wait for the AJAX 'Download' link
        page.wait_for_selector("#ajaxPane a", timeout=180_000)
        link = page.locator("#ajaxPane a").first

        # download
        with page.expect_download() as dl_info:
            link.click()
        dl = dl_info.value
        dl.save_as(str(out_path))
        print(f"saved {out_path}")

        ctx.close(); browser.close()

def parse_args():
    ap = argparse.ArgumentParser(description="LibraryThing export via Playwright (headless by default).")
    ap.add_argument("--since", help="YYYY-MM-DD (incremental export)")
    ap.add_argument("--collections", help="Comma-separated list of collection labels or 'all' (e.g. Owned,Your library)")
    ap.add_argument("--tags", help="Comma-separated tags to filter by")
    ap.add_argument("--search", help="Search string")
    ap.add_argument("--fmt", choices=["json", "marc"], default="json", help="Export format")
    ap.add_argument("--headed", action="store_true", help="Run with a visible browser")
    return ap.parse_args()

if __name__ == "__main__":
    args = parse_args()
    cols = [c.strip() for c in args.collections.split(",")] if args.collections else None
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else None
    run_export(
        fmt=args.fmt,
        since=args.since,
        collections=cols,
        tags=tags,
        search=args.search,
        headed=args.headed,
    )
