from booking.config import OUT

def save_debug(page, prefix):
    OUT.mkdir(exist_ok=True)
    try:
        (OUT / f"{prefix}.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
    try:
        (OUT / f"{prefix}.txt").write_text(page.locator("body").inner_text(), encoding="utf-8")
    except Exception:
        pass
    try:
        page.screenshot(path=str(OUT / f"{prefix}.png"), full_page=True)
    except Exception:
        pass