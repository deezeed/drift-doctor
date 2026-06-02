"""Generate an animated GIF showing the drift-doctor workflow."""
from pathlib import Path
from PIL import Image
import io
from playwright.sync_api import sync_playwright

TERMINAL_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    background: #1e1e2e;
    font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
    font-size: 13.5px;
    line-height: 1.55;
    padding: 0;
}
.window {
    width: 720px;
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 20px 60px rgba(0,0,0,.6);
}
.titlebar {
    background: #313244;
    padding: 10px 14px;
    display: flex;
    align-items: center;
    gap: 7px;
}
.dot { width: 12px; height: 12px; border-radius: 50%; }
.dot.red    { background: #f38ba8; }
.dot.yellow { background: #f9e2af; }
.dot.green  { background: #a6e3a1; }
.title { color: #6c7086; font-size: 12px; margin-left: 8px; }
.body {
    background: #1e1e2e;
    padding: 16px 20px 20px;
    min-height: 280px;
}
.prompt { color: #89b4fa; }
.cmd    { color: #cdd6f4; }
.dim    { color: #585b70; }
.crit   { color: #f38ba8; font-weight: bold; }
.warn   { color: #fab387; font-weight: bold; }
.ok     { color: #a6e3a1; }
.blue   { color: #89b4fa; }
.cyan   { color: #89dceb; }
.white  { color: #cdd6f4; }
.bold   { font-weight: bold; }
.sep    { color: #45475a; }
"""

def terminal_html(lines: list[str]) -> str:
    body = "\n".join(f"<div>{l}</div>" for l in lines)
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>{TERMINAL_CSS}</style></head><body>
<div class="window">
  <div class="titlebar">
    <div class="dot red"></div>
    <div class="dot yellow"></div>
    <div class="dot green"></div>
    <span class="title">Terminal</span>
  </div>
  <div class="body">{body}</div>
</div></body></html>"""

def s(text, cls="white"):
    return f'<span class="{cls}">{text}</span>'

_p  = s("$", "prompt")
_tl = s("~", "dim")

FRAMES = [
    # Frame 0 — version check
    [
        f'{_tl} {_p} {s("drift-doctor --version", "cmd")}',
        f'{s("drift-doctor 0.10.2", "cyan")}',
        f"",
        f'{_tl} {_p} {s("drift-doctor check customers.csv --skip customer_id", "cmd")}',
        f'<span class="dim">&#9608;</span>',
    ],
    # Frame 1 — onboarding hint (no snapshot yet)
    [
        f'{_tl} {_p} {s("drift-doctor check customers.csv --skip customer_id", "cmd")}',
        f"",
        f'{s("No snapshot found for", "white")} {s("customers.csv", "bold")}',
        f'  {s("Create one first:", "dim")} {s("drift-doctor snapshot customers.csv", "cyan")}',
        f"",
        f'{_tl} {_p} {s("drift-doctor snapshot customers.csv", "cmd")}',
        f'<span class="dim">&#9608;</span>',
    ],
    # Frame 2 — snapshot taken, then check
    [
        f'{_tl} {_p} {s("drift-doctor snapshot customers.csv", "cmd")}',
        f'{s("Snapshot written: .driftdoctor/customers_20260602T160000Z.json", "dim")}',
        f"",
        f'{_tl} {_p} {s("drift-doctor check customers.csv --skip customer_id", "cmd")}',
        f"",
        f'{s("Row count: 1,000 -> 1,000 (+0, +0.0%)  (snapshot: 20260602T160000Z)", "dim")}',
        f'{s("      Drift Findings  (3 issues)      ", "bold")}',
        f"",
        f'{s("  Sev    Column   Metric       Detail", "dim")}',
        f'{s(" ──────────────────────────────────────────────────────", "sep")}',
        f'  {s("CRIT", "crit")}   {s("phone", "white")}    {s("schema", "dim")}       {s("present -> missing", "white")}',
        f'  {s("CRIT", "crit")}   {s("age", "white")}      {s("null%", "dim")}        {s("1.6% -> 32.5%  (+30.9%)", "white")}',
        f'  {s("CRIT", "crit")}   {s("spend", "white")}    {s("PSI", "dim")}          {s("PSI=0.42  (crit >0.25)", "white")}',
        f"",
        f'  {s("3 critical", "crit")}',
    ],
    # Frame 3 — snapshots list
    [
        f'{_tl} {_p} {s("drift-doctor snapshots customers.csv", "cmd")}',
        f"",
        f'{s("Snapshots for", "bold")} {s("customers", "cyan")}  {s("(.driftdoctor)", "dim")}',
        f'  {s("File", "dim")}                                    {s("Created (UTC)", "dim")}          {s("Size", "dim")}',
        f'  {s("customers_20260602T160000Z.json", "cyan")}    {s("2026-06-02 16:00:00", "white")}    {s("12 KB", "dim")}',
        f'  {s("customers_20260601T090000Z.json", "cyan")}    {s("2026-06-01 09:00:00", "white")}    {s("11 KB", "dim")}',
        f"",
        f'  {s("2 snapshot(s).  Use --ref or --since to select one.", "dim")}',
    ],
    # Frame 4 — watch clean check
    [
        f'{_tl} {_p} {s("drift-doctor watch customers.csv --interval 1h --fail-on any", "cmd")}',
        f"",
        f'{s("Watching", "bold")} {s("customers.csv", "blue")}  {s("every 1h", "dim")}  {s("—  Ctrl+C to stop", "dim")}',
        f"",
        f'{s("[16:00:00]", "dim")} {s("Checking...", "white")}',
        f'  {s("3 critical", "crit")}  {s("Notification sent.", "dim")}',
        f'  {s("Next check at 17:00:00 UTC", "dim")}',
        f"",
        f'{s("[17:00:00]", "dim")} {s("Checking...", "white")}',
        f'  {s("No drift detected.", "ok")}',
        f'  {s("Next check at 18:00:00 UTC", "dim")}',
    ],
]

DELAYS = [140, 200, 220, 200, 200]  # centiseconds per frame

def make_gif():
    out = Path(__file__).parent / "watch_demo.gif"
    tmp = Path(__file__).parent / "_frame.html"

    images = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 760, "height": 380})
        for lines in FRAMES:
            html = terminal_html(lines)
            tmp.write_text(html, encoding="utf-8")
            page.goto(tmp.as_uri())
            page.wait_for_load_state("networkidle")
            png = page.screenshot()
            img = Image.open(io.BytesIO(png)).convert("P", palette=Image.ADAPTIVE, colors=128)
            images.append(img)
        browser.close()

    tmp.unlink(missing_ok=True)

    images[0].save(
        str(out),
        save_all=True,
        append_images=images[1:],
        duration=[d * 10 for d in DELAYS],
        loop=0,
        optimize=True,
    )
    print(f"GIF saved: {out}  ({out.stat().st_size // 1024} KB)")

if __name__ == "__main__":
    make_gif()
