"""
render_html.py
--------------
Pipeline:
  1. Reads  html_info/content.md  and  html_info/template.html.
  2. Injects the MD text as DEFAULT_MD in the template's JavaScript and adds
     a DOMContentLoaded render call → writes  html_pipeline/resume.html
     (Task 1 – "load md content from html_info/content.md").
  3. Renders  html_pipeline/resume.html  via Playwright (Chromium headless)
     (Task 2 – "render the html file in html_info/template.html").
  4. Saves the PNG to  image_reference/Output_1.png
     (Task 3 – "save the image as image_reference/Output_1.png").

Hang-safety notes
-----------------
* Playwright page.goto has a 30 s timeout; PlaywrightTimeoutError exits cleanly.
* page.wait_for_timeout(1500) lets the JS MD-renderer finish before screenshot.
* Browser is always closed in a finally block so no zombie processes remain.

Usage:
    python html_pipeline/render_html.py
    python html_pipeline/render_html.py \\
        --template html_info/template.html \\
        --md       html_info/content.md    \\
        --html     html_pipeline/resume.html \\
        --out      image_reference/Output_1.png \\
        --width    1414 \\
        --height   2000
"""

import re
import argparse
import logging
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ── Paths (workspace root = 3 levels up from this script) ─────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
WORKSPACE  = SCRIPT_DIR.parent.parent.parent

DEFAULT_TEMPLATE     = WORKSPACE / "source"        / "template.html"
DEFAULT_CSS_TEMPLATE = WORKSPACE / "source"        / "template.css"
DEFAULT_MD_FILE      = WORKSPACE / "source"        / "content.md"
DEFAULT_RESUME       = WORKSPACE / "generated"     / "resume.html"
DEFAULT_RESUME_CSS   = WORKSPACE / "generated"     / "resume.css"
DEFAULT_OUT          = WORKSPACE / "generated"     / "Output_1.png"
LOG_FILE         = WORKSPACE / "generated" / "temp" / "render_html.log"

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ── Task 1: build resume.html + resume.css from template + content.md ───────────
def build_resume_html(
    template_path: Path,
    md_path: Path,
    out_path: Path,
    css_template_path: Path = DEFAULT_CSS_TEMPLATE,
    css_out_path: Path = DEFAULT_RESUME_CSS,
) -> Path:
    """
    Inject content.md into template.html's JS DEFAULT_MD variable, add an
    auto-render call on DOMContentLoaded, and save the result as resume.html.
    Also copies template.css → resume.css, adjusting font paths to be relative
    to html_pipeline/ instead of html_info/.
    """
    log.info("[build] Reading template : %s", template_path)
    template_html = template_path.read_text(encoding="utf-8")

    # ── CSS: copy template.css → resume.css with corrected font paths ─────────
    # Fonts live at source/fonts/; resume.css lives in generated/,
    # so relative paths need to go up one level and over into source/.
    log.info("[build] Reading CSS      : %s", css_template_path)
    css_content = css_template_path.read_text(encoding="utf-8")
    css_out = css_content.replace("./fonts/", "../source/fonts/")
    css_out_path.parent.mkdir(parents=True, exist_ok=True)
    css_out_path.write_text(css_out, encoding="utf-8")
    log.info("[build] resume.css written → %s", css_out_path)

    # Point the HTML's stylesheet link at resume.css instead of template.css
    template_html = template_html.replace(
        'href="./template.css"', 'href="./resume.css"', 1
    )

    log.info("[build] Reading markdown : %s", md_path)
    md_content = md_path.read_text(encoding="utf-8")

    # Escape so the MD text is safe inside a JS template literal (`...`)
    escaped_md = (
        md_content
        .replace("\\", "\\\\")   # backslashes first
        .replace("`",  "\\`")    # backticks
        .replace("${", "\\${")   # template-literal interpolations
    )

    new_const = f"const DEFAULT_MD = `{escaped_md}`;"

    # Replace the existing DEFAULT_MD template-literal block
    template_html, n_replacements = re.subn(
        r"const DEFAULT_MD\s*=\s*`[\s\S]*?`;",
        new_const,
        template_html,
    )

    if n_replacements == 0:
        log.warning(
            "[build] DEFAULT_MD block not found in template; "
            "inserting before 'let currentMD'"
        )
        template_html = template_html.replace(
            "let currentMD = DEFAULT_MD;",
            f"{new_const}\nlet currentMD = DEFAULT_MD;",
        )
    else:
        log.info("[build] DEFAULT_MD injected (%d occurrence(s) replaced)", n_replacements)

    # Add a DOMContentLoaded listener so the page content renders before
    # wkhtmltoimage captures it (idempotent guard prevents double-injection)
    auto_render = (
        "\n// ── Auto-render on load (injected by render_html.py) ──────────\n"
        "document.addEventListener('DOMContentLoaded', function () {\n"
        "  render(currentMD);\n"
        "});\n"
    )
    if "DOMContentLoaded" not in template_html:
        template_html = template_html.replace(
            "</script>",
            auto_render + "</script>",
            1,
        )
        log.info("[build] DOMContentLoaded render hook injected")
    else:
        log.info("[build] DOMContentLoaded hook already present – skipped")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(template_html, encoding="utf-8")
    log.info("[build] resume.html written → %s", out_path)
    return out_path


# ── Tasks 2 & 3: render HTML → PNG ────────────────────────────────────────────
def render_html_to_png(
    html_path: Path,
    out_path: Path,
    width: int = 1414,
    height: int = 2000,
    crop_toolbar: bool = True,
) -> Path:
    """
    Render an HTML file to PNG using Playwright (Chromium, headless).

    Hang-safety
    -----------
    * browser and page operations have explicit timeouts (ms).
    * page.goto timeout=30000 ms – aborts if page never loads.
    * page.wait_for_timeout(1500) – lets the JS MD-renderer finish.
    * PlaywrightTimeoutError is caught to exit cleanly instead of hanging.
    """
    tmp_path = Path(str(out_path) + ".raw.png")

    log.info("[render] Starting Playwright Chromium (headless)")
    log.info("[render] Input HTML : %s", html_path)
    log.info("[render] Viewport   : %d × %d px", width, height)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            log.info("[render] Browser launched")
            try:
                page = browser.new_page(viewport={"width": width, "height": height})
                file_url = html_path.as_uri()
                log.info("[render] Navigating to: %s", file_url)
                page.goto(file_url, wait_until="domcontentloaded", timeout=30_000)
                log.info("[render] DOMContentLoaded – waiting 1.5 s for JS render")
                page.wait_for_timeout(1500)   # let render(currentMD) finish
                log.info("[render] Taking full-page screenshot → %s", tmp_path)
                page.screenshot(path=str(tmp_path), full_page=True)
            finally:
                browser.close()
                log.info("[render] Browser closed")
    except PlaywrightTimeoutError as exc:
        log.error("[render] Playwright timed out: %s", exc)
        log.error("[render] HANG CAUSE: page never reached DOMContentLoaded; "
                  "check the HTML file for blocking scripts or missing resources")
        sys.exit(1)

    if not tmp_path.exists():
        log.error("[render] Screenshot not found at %s", tmp_path)
        sys.exit(1)

    img = Image.open(tmp_path).convert("RGB")
    w, h = img.size
    log.info("[render] Raw screenshot size : %d × %d px", w, h)

    if crop_toolbar:
        toolbar_px = max(40, int(55 * width / 980))
        img = img.crop((0, toolbar_px, w, h - toolbar_px))
        log.info("[render] After toolbar crop   : %d × %d px", img.size[0], img.size[1])

    # Resize to target dimensions
    img = img.resize((width, height), Image.Resampling.LANCZOS)
    log.info("[render] After resize         : %d × %d px", img.size[0], img.size[1])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out_path), "PNG", optimize=True)
    tmp_path.unlink(missing_ok=True)
    log.info("[render] Saved → %s", out_path)
    return out_path


# ── Entry point ────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build resume.html from template + content.md, then render to PNG"
    )
    parser.add_argument(
        "--template", default=str(DEFAULT_TEMPLATE),
        help="Source template HTML  (default: html_info/template.html)",
    )
    parser.add_argument(
        "--md", default=str(DEFAULT_MD_FILE),
        help="Markdown content file  (default: html_info/content.md)",
    )
    parser.add_argument(
        "--html", default=str(DEFAULT_RESUME),
        help="Generated resume HTML  (default: html_pipeline/resume.html)",
    )
    parser.add_argument(
        "--css", default=str(DEFAULT_CSS_TEMPLATE),
        help="Source template CSS  (default: html_info/template.css)",
    )
    parser.add_argument(
        "--css-out", default=str(DEFAULT_RESUME_CSS),
        help="Generated resume CSS  (default: html_pipeline/resume.css)",
    )
    parser.add_argument(
        "--out", default=str(DEFAULT_OUT),
        help="Output PNG path  (default: image_reference/Output_1.png)",
    )
    parser.add_argument(
        "--width", default=1414, type=int,
        help="Viewport width in px  (default: 1414)",
    )
    parser.add_argument(
        "--height", default=2000, type=int,
        help="Viewport height in px  (default: 2000)",
    )
    parser.add_argument(
        "--no-crop", action="store_true",
        help="Skip toolbar-strip crop",
    )
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("render_html.py  START")
    log.info("  template : %s", args.template)
    log.info("  css      : %s", args.css)
    log.info("  markdown : %s", args.md)
    log.info("  html out : %s", args.html)
    log.info("  css out  : %s", args.css_out)
    log.info("  png out  : %s", args.out)
    log.info("  width    : %d px", args.width)
    log.info("  height   : %d px", args.height)
    log.info("=" * 60)

    # Task 1 – inject content.md → resume.html + build resume.css
    resume_path = build_resume_html(
        Path(args.template),
        Path(args.md),
        Path(args.html),
        css_template_path=Path(args.css),
        css_out_path=Path(args.css_out),
    )

    # Tasks 2 & 3 – render resume.html → Output_1.png
    render_html_to_png(
        resume_path,
        Path(args.out),
        width=args.width,
        height=args.height,
        crop_toolbar=not args.no_crop,
    )

    log.info("=" * 60)
    log.info("render_html.py  DONE")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
