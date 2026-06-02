"""Generate an animated GIF showing drift-doctor watch in action."""
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
    min-height: 260px;
}
.prompt { color: #89b4fa; }
.cmd    { color: #cdd6f4; }
.dim    { color: #585b70; }
.crit   { color: #f38ba8; font-weight: bold; }
.warn   { color: #fab387; font-weight: bold; }
.green  { color: #a6e3a1; }
.blue   { color: #89b4fa; }
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

_cmd0a = s("drift-doctor watch customers.csv \\", "cmd")
_cmd0b = s("    --interval 1h --skip customer_id \\", "cmd")
_cmd0c = s("    --notify https://hooks.slack.com/...", "cmd")
_prompt = s("$", "prompt")
_tilde  = s("~", "dim")

FRAMES = [
    # Frame 0 — command prompt
    [
        f'{_tilde} {_prompt} {_cmd0a}',
        f'{_cmd0b}',
        f'{_cmd0c}',
        f'<span class="dim">&#9608;</span>',
    ],
    # Frame 1 — starting
    [
        f'{s("~", "dim")} {s("$", "prompt")} {s("drift-doctor watch customers.csv --interval 1h --skip customer_id --notify ...", "cmd")}',
        f"",
        f'{s("Watching", "bold")} {s("customers.csv", "blue")}  {s("every 1h", "dim")}  {s("—  Ctrl+C to stop", "dim")}',
        f"",
        f'{s("[09:00:00]", "dim")} {s("Checking...", "white")}',
    ],
    # Frame 2 — findings
    [
        f'{s("~", "dim")} {s("$", "prompt")} {s("drift-doctor watch customers.csv --interval 1h --skip customer_id --notify ...", "cmd")}',
        f"",
        f'{s("Watching", "bold")} {s("customers.csv", "blue")}  {s("every 1h", "dim")}  {s("—  Ctrl+C to stop", "dim")}',
        f"",
        f'{s("[09:00:00]", "dim")} {s("Checking...", "white")}',
        f"",
        f'{s("Row count: 1,000 -> 1,000 (+0, +0.0%)  (snapshot: 20260601T140029Z)", "dim")}',
        f'{s("      Drift Findings  (3 issues)      ", "bold")}',
        f"",
        f'{s("  Sev    Column   Metric       Detail", "dim")}',
        f'{s(" ──────────────────────────────────────────────────────", "sep")}',
        f'  {s("CRIT", "crit")}   {s("phone", "white")}    {s("schema", "dim")}       {s("present -> missing", "white")}',
        f'  {s("CRIT", "crit")}   {s("age", "white")}      {s("mean_shift", "dim")}   {s("mean 34.3 -> 49.8  (+15.5)", "white")}',
        f'  {s("CRIT", "crit")}   {s("spend", "white")}    {s("null%", "dim")}        {s("1.6% -> 32.5%  (+30.9%)", "white")}',
        f"",
        f'  {s("3 critical", "crit")}',
    ],
    # Frame 3 — notification sent
    [
        f'{s("~", "dim")} {s("$", "prompt")} {s("drift-doctor watch customers.csv --interval 1h --skip customer_id --notify ...", "cmd")}',
        f"",
        f'{s("Watching", "bold")} {s("customers.csv", "blue")}  {s("every 1h", "dim")}  {s("—  Ctrl+C to stop", "dim")}',
        f"",
        f'{s("[09:00:00]", "dim")} {s("Checking...", "white")}',
        f"",
        f'  {s("3 critical", "crit")}',
        f'  {s("Notification sent.", "dim")}',
        f'  {s("Next check at 10:00:00 UTC", "dim")}',
        f"",
        f'{s("[10:00:00]", "dim")} {s("Checking...", "white")}',
    ],
    # Frame 4 — clean check
    [
        f'{s("~", "dim")} {s("$", "prompt")} {s("drift-doctor watch customers.csv --interval 1h --skip customer_id --notify ...", "cmd")}',
        f"",
        f'{s("Watching", "bold")} {s("customers.csv", "blue")}  {s("every 1h", "dim")}  {s("—  Ctrl+C to stop", "dim")}',
        f"",
        f'{s("[09:00:00]", "dim")} {s("Checking...", "white")}',
        f'  {s("3 critical", "crit")}  {s("Notification sent.", "dim")}',
        f'  {s("Next check at 10:00:00 UTC", "dim")}',
        f"",
        f'{s("[10:00:00]", "dim")} {s("Checking...", "white")}',
        f'  {s("No drift detected.", "green")}',
        f'  {s("Next check at 11:00:00 UTC", "dim")}',
    ],
]

DELAYS = [120, 80, 120, 100, 180]  # centiseconds per frame

def make_gif():
    out = Path(__file__).parent / "watch_demo.gif"
    tmp = Path(__file__).parent / "_frame.html"

    images = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 760, "height": 340})
        for i, lines in enumerate(FRAMES):
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
