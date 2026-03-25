"""Render HTML templates with embedded markdown to a PNG using Playwright.

**Module Overview:**
This script builds a resume PDF by combining a template HTML file with markdown
content, extracting font size specifications from the markdown, and rendering the
result to a PNG image using headless Chromium.

**Three-stage pipeline:**

1. **Font Extraction** (extract_font_vars_from_md)
   - Parse markdown for embedded font size markers like "(font_size: 32px)"
   - Map font sizes to semantic CSS variables (--fs-name, --fs-pill, etc.)
   - Support section-aware extraction (work, awards, profile, contact, projects)

2. **HTML/CSS Generation** (build_resume_html)
   - Inject markdown content into template.html's DEFAULT_MD JavaScript constant
   - Apply extracted font variables to template.css as CSS custom properties
   - Inject font variables into HTML inline styles for pre-render parity
   - Add auto-render hook on DOMContentLoaded
   - Generate resume.html and resume.css in output directory

3. **PNG Rendering** (render_html_to_png)
   - Launch headless Chromium and navigate to generated resume.html
   - Wait for JavaScript markdown renderer to complete
   - Capture full-page screenshot
   - Crop browser toolbars and resize to target dimensions
   - Save final PNG with optimization

**Input files:**
- source/template.html: HTML template with DEFAULT_MD placeholder and #resume div
- source/template.css: CSS with custom properties for font sizes
- source/content.md: Markdown with font size markers

**Output files:**
- generated/resume.html: Injected HTML ready to render
- generated/resume.css: CSS with applied font variables and corrected paths
- generated/Output_1.png: Final rendered resume PNG

**Safety features:**
- Explicit timeouts on all browser and page operations (30s for page load)
- Graceful handling of PlaywrightTimeoutError with detailed error messages
- Comprehensive logging to file and stdout
- Cleanup of temporary files

Usage:
     python pipeline/render/render_html.py [--template PATH] [--md PATH] [--html PATH]
                                           [--css PATH] [--css-out PATH] [--out PATH]
                                           [--width W] [--height H] [--no-crop]
"""

import re
import argparse
import logging
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ── Paths (workspace root = 2 levels up from this script) ─────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
WORKSPACE  = SCRIPT_DIR.parent.parent

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


FONT_VAR_MAP = {
    "name": "--fs-name",
    "pill": "--fs-pill",
    "contactItem": "--fs-contact-item",
    "awardsItem": "--fs-awards-item",
    "profileItem": "--fs-profile-item",
    "workHeader": "--fs-work-header",
    "jobPos": "--fs-job-pos",
    "jobCompany": "--fs-job-company",
    "jobDates": "--fs-job-dates",
    "projName": "--fs-proj-name",
    "bullet": "--fs-bullet",
}


def _extract_value_and_font(raw: str) -> tuple[str, str]:
    """Extract value and font size from a markdown line.
    
    Parses a line to extract:
    - The text value (everything after " : " separator, or the whole line if no separator)
    - The font size (if present as "(font_size: XXpx)" at the end)
    
    Args:
        raw: A markdown line potentially containing a colon separator and font size marker.
        
    Returns:
        tuple[str, str]: (cleaned_value, font_size_or_empty_string)
        Example: ("John Doe", "32px") or ("Contact", "")
    """
    idx = raw.find(" : ")
    value = raw[idx + 3 :].strip() if idx != -1 else raw.strip()
    m = re.search(r"\(font_size\s*:\s*([0-9.]+\s*px)\)\s*$", value, flags=re.IGNORECASE)
    if not m:
        return value.strip(), ""
    clean_value = re.sub(
        r"\s*\(font_size\s*:\s*[0-9.]+\s*px\)\s*$",
        "",
        value,
        flags=re.IGNORECASE,
    ).strip()
    return clean_value, m.group(1).replace(" ", "")


def extract_font_vars_from_md(md_content: str) -> dict[str, str]:
    """Extract all CSS font size variables from markdown content.
    
    Parses markdown structure to identify and extract font sizes attached to different
    semantic elements (name, contact items, awards, work headers, bullets, etc.).
    Builds a complete font variable map using the FONT_VAR_MAP dictionary.
    Only the first occurrence of each variable is stored (set_once pattern).
    
    Markdown structure expected:
    - "# Name (font_size: 32px)" → name font size
    - "## Section : Title (font_size: 16px)" → section header font size
    - "### Job | Company | Dates" → jobPos, jobCompany, jobDates fonts
    - "#### Project Name (font_size: 14px)" → projName font
    - "- Bullet item (font_size: 12px)" → bullet, awardsItem, or profileItem font
    
    Args:
        md_content: Raw markdown content from content.md
        
    Returns:
        dict[str, str]: Font variable map {key: "XXpx" or ""} 
        Keys are: name, pill, contactItem, awardsItem, profileItem, 
                  workHeader, jobPos, jobCompany, jobDates, projName, bullet
    """
    fonts = {key: "" for key in FONT_VAR_MAP}
    section = ""

    def set_once(key: str, size: str) -> None:
        if size and not fonts[key]:
            fonts[key] = size

    for raw_line in md_content.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("# "):
            _, size = _extract_value_and_font(line[2:])
            set_once("name", size)
            section = ""
            continue

        if line.startswith("## "):
            inner = line[3:].strip()
            label = inner.split(" : ", 1)[0].lower()
            _, size = _extract_value_and_font(inner)
            if "contact" in label:
                section = "contact"
                set_once("pill", size)
            elif "award" in label:
                section = "awards"
                set_once("pill", size)
            elif "profile" in label:
                section = "profile"
                set_once("pill", size)
            elif "work" in label:
                section = "work"
                set_once("workHeader", size)
            else:
                section = ""
            continue

        if line.startswith("### "):
            section = "work"
            for idx, chunk in enumerate(line[4:].split("|")):
                _, size = _extract_value_and_font(chunk.strip())
                if idx == 0:
                    set_once("jobPos", size)
                elif idx == 1:
                    set_once("jobCompany", size)
                elif idx == 2:
                    set_once("jobDates", size)
            continue

        if line.startswith("#### "):
            section = "project"
            _, size = _extract_value_and_font(line[5:])
            set_once("projName", size)
            continue

        if line.startswith("- "):
            _, size = _extract_value_and_font(line[2:])
            if section == "awards":
                set_once("awardsItem", size)
            elif section == "profile":
                set_once("profileItem", size)
            elif section in {"work", "project"}:
                set_once("bullet", size)
            continue

        if section == "contact":
            _, size = _extract_value_and_font(line)
            set_once("contactItem", size)

    return fonts


def apply_font_vars_to_css(css_content: str, font_vars: dict[str, str]) -> str:
    """Apply extracted font variables to CSS file by updating CSS custom properties.
    
    Replaces CSS custom property values (e.g., --fs-name: 32px;) with extracted
    font sizes from markdown. Uses regex to find and replace each property definition.
    Only updates properties that have non-empty font values in font_vars.
    
    Args:
        css_content: Raw CSS text from template.css
        font_vars: Font variable map from extract_font_vars_from_md()
        
    Returns:
        str: Updated CSS with font sizes applied to custom properties.
        Example: "--fs-name: 32px;" if font_vars["name"] == "32px"
    """
    updated = css_content
    for key, css_var in FONT_VAR_MAP.items():
        size = font_vars.get(key, "")
        if not size:
            continue
        pattern = rf"({re.escape(css_var)}\s*:\s*)[^;]+;"
        updated, _ = re.subn(pattern, rf"\\1{size};", updated)
    return updated


def apply_font_vars_to_html(html_content: str, font_vars: dict[str, str]) -> str:
    """Apply extracted font variables to HTML by injecting inline styles.
    
    Injects all font variables as CSS custom properties into the #resume div's inline
    style attribute. This ensures variables are available for the renderer's MD-to-HTML
    conversion and achieves parity with the CSS file. If #resume already has a style
    attribute, merges the new declarations; otherwise adds a new style attribute.
    
    Args:
        html_content: Raw HTML text from template.html
        font_vars: Font variable map from extract_font_vars_from_md()
        
    Returns:
        str: Updated HTML with font variables injected into #resume element's inline style.
        Example: <div id="resume" style="--fs-name: 32px; --fs-pill: 14px; ...">
    """
    declarations = " ".join(
        f"{FONT_VAR_MAP[key]}: {size};"
        for key, size in font_vars.items()
        if size and key in FONT_VAR_MAP
    )
    if not declarations:
        return html_content

    def _inject_style(match: re.Match[str]) -> str:
        attrs = match.group(1)
        style_match = re.search(r'style="([^"]*)"', attrs)
        if style_match:
            existing = style_match.group(1).strip()
            spacer = " " if existing and not existing.endswith(";") else ""
            merged = f"{existing}{spacer}{declarations}".strip()
            attrs = re.sub(r'style="[^"]*"', f'style="{merged}"', attrs, count=1)
        else:
            attrs = f'{attrs} style="{declarations}"'
        return f"<div id=\"resume\"{attrs}>"

    html_content, _ = re.subn(r'<div id="resume"([^>]*)>', _inject_style, html_content, count=1)
    return html_content


# ── Task 1: build resume.html + resume.css from template + content.md ───────────
def build_resume_html(
    template_path: Path,
    md_path: Path,
    out_path: Path,
    css_template_path: Path = DEFAULT_CSS_TEMPLATE,
    css_out_path: Path = DEFAULT_RESUME_CSS,
) -> Path:
    """Build resume.html and resume.css by injecting markdown content and font variables.
    
    **Core workflow:**
    1. Extract markdown content and parse all font size markers (e.g., "(font_size: 32px)")
    2. Read template.html and template.css
    3. Update CSS custom properties with extracted font sizes
    4. Update HTML inline styles with font variables
    5. Inject markdown into template's DEFAULT_MD JavaScript constant
    6. Add DOMContentLoaded listener to auto-render markdown on page load
    7. Save updated files as resume.html and resume.css
    
    **CSS path adjustments:**
    - Template uses "./fonts/" relative path (assumes CSS is in source/)
    - Generated resume.css lives in generated/, so paths are rewritten to
      "../source/fonts/" to maintain correct relative paths to font files
    
    Args:
        template_path: Source template HTML file
        md_path: Markdown content file to inject
        out_path: Output path for generated resume.html
        css_template_path: Source template CSS file (default: source/template.css)
        css_out_path: Output path for generated resume.css (default: generated/resume.css)
        
    Returns:
        Path: The output_path after successful generation
    """
    log.info("[build] Reading template : %s", template_path)
    template_html = template_path.read_text(encoding="utf-8")

    log.info("[build] Reading markdown : %s", md_path)
    md_content = md_path.read_text(encoding="utf-8")
    font_vars = extract_font_vars_from_md(md_content)
    log.info("[build] Extracted font vars: %s", {k: v for k, v in font_vars.items() if v})

    # ── CSS: copy template.css → resume.css with corrected font paths ─────────
    # Fonts live at source/fonts/; resume.css lives in generated/,
    # so relative paths need to go up one level and over into source/.
    log.info("[build] Reading CSS      : %s", css_template_path)
    css_content = css_template_path.read_text(encoding="utf-8")
    css_out = css_content.replace("./fonts/", "../source/fonts/")
    css_out = apply_font_vars_to_css(css_out, font_vars)
    css_out_path.parent.mkdir(parents=True, exist_ok=True)
    css_out_path.write_text(css_out, encoding="utf-8")
    log.info("[build] resume.css written → %s", css_out_path)

    # Point the HTML's stylesheet link at resume.css instead of template.css
    template_html = template_html.replace(
        'href="./template.css"', 'href="./resume.css"', 1
    )

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

    # Apply extracted font vars directly to #resume inline style for pre-render parity.
    template_html = apply_font_vars_to_html(template_html, font_vars)

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
    """Render an HTML file to PNG using Playwright (Chromium, headless).
    
    **Rendering workflow:**
    1. Launch headless Chromium browser with specified viewport dimensions
    2. Navigate to HTML file and wait for DOMContentLoaded event
    3. Wait 1.5s for JavaScript markdown renderer to complete
    4. Capture full-page screenshot
    5. Crop browser toolbar from top and bottom (if enabled)
    6. Resize to target dimensions using Lanczos resampling
    7. Save as PNG with optimization
    
    **Hang-safety:**
    * browser.launch() and page operations have explicit timeouts
    * page.goto timeout=30000ms – aborts if page never loads
    * page.wait_for_timeout(1500) – lets the JS MD-renderer finish
    * PlaywrightTimeoutError is caught and logged for clean exit
    
    Args:
        html_path: Path to HTML file to render
        out_path: Output PNG file path
        width: Viewport and final image width in pixels (default: 1414)
        height: Viewport and final image height in pixels (default: 2000)
        crop_toolbar: Whether to crop browser toolbar from top/bottom (default: True)
        
    Returns:
        Path: The output_path after successful rendering
        
    Raises:
        SystemExit: On PlaywrightTimeoutError or file I/O failures
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
                file_url = html_path.resolve().as_uri()
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
    """Main entry point: orchestrate resume HTML generation and PNG rendering.
    
    **High-level workflow:**
    1. Parse command-line arguments to configure input/output paths and dimensions
    2. Call build_resume_html() to:
       - Extract font variables from markdown
       - Inject markdown into HTML template
       - Apply fonts to CSS and inline styles
       - Generate resume.html and resume.css
    3. Call render_html_to_png() to:
       - Render resume.html in headless Chromium
       - Capture screenshot and crop/resize
       - Save final PNG output
    
    **Configurable parameters:**
    - Input paths: template HTML, CSS, markdown content
    - Output paths: resume.html, resume.css, Output PNG
    - Render dimensions: viewport width/height and crop options
    
    **Logging:**
    - Logs to generated/temp/render_html.log and stdout
    - Provides detailed progress tracking at each stage
    """
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
