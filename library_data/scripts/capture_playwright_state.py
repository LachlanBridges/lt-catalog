from playwright.sync_api import sync_playwright
from library_data.config import SECRETS_DIR, ensure_dirs

STATE = SECRETS_DIR / ".state.json"
PROFILE = SECRETS_DIR / ".lt_profile"  # persistent profile dir

def main():
    ensure_dirs()
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            headless=False,
            channel="msedge",  # or "chrome" if you have it
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.new_page()
        page.goto("https://www.librarything.com/", wait_until="domcontentloaded")
        print("\n[manual] Log in normally. Pass the human check. Then open https://www.librarything.com/export.php")
        print("[manual] When the export page is fully loaded, press ENTER here.\n")
        try:
            input()
        except EOFError:
            pass
        # sanity: try to detect export controls
        try:
            page.goto("https://www.librarything.com/export.php", wait_until="domcontentloaded")
            page.wait_for_selector("form", timeout=5000)
        except Exception:
            print("[warn] Couldn't auto-verify export form; saving state anyway.")
        ctx.storage_state(path=str(STATE))
        print(f"[ok] Saved session to {STATE}")
        ctx.close()

if __name__ == "__main__":
    main()
