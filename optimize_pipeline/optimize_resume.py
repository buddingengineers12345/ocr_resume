"""
optimize_resume.py
------------------
1. Renders resume.html → PNG via wkhtmltoimage
2. Scales both images to a common size
3. Computes composite metric: MSE + (1-SSIM) weighted
4. Analyses regional diffs (sidebar / main / top / bottom)
5. Proposes targeted CSS tweaks, applies them, re-renders
6. Repeats until metric stops improving or max_iterations hit
7. Saves best HTML and a full comparison report
"""

import subprocess, shutil, re, copy, os, json
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from skimage.metrics import structural_similarity as ssim
from skimage.metrics import mean_squared_error as mse_metric

# ── Config ────────────────────────────────────────────────────────────
ORIGINAL_PATH   = "/mnt/user-data/uploads/Page_1.png"
HTML_PATH       = "/mnt/user-data/outputs/resume.html"
RENDER_PATH     = "/tmp/resume_iter.png"
BEST_HTML_PATH  = "/mnt/user-data/outputs/resume_best.html"
REPORT_PATH     = "/mnt/user-data/outputs/optimization_report.png"
COMPARE_SIZE    = (980, 1369)   # canonical size for all comparisons
MAX_ITERATIONS  = 12
WKHTMLTOIMAGE   = "wkhtmltoimage"

# ── Utility: render HTML → PNG ────────────────────────────────────────
def render_html(html_path, out_path, width=980):
    result = subprocess.run([
        WKHTMLTOIMAGE,
        "--width", str(width),
        "--load-error-handling", "ignore",
        "--load-media-error-handling", "ignore",
        html_path, out_path
    ], capture_output=True)
    return os.path.exists(out_path)


# ── Utility: load & normalise both images to same size ───────────────
def load_pair(orig_path, rend_path, size=COMPARE_SIZE):
    orig = Image.open(orig_path).convert("RGB").resize(size, Image.LANCZOS)
    rend = Image.open(rend_path).convert("RGB").resize(size, Image.LANCZOS)
    # Crop toolbar strip from rendered (top ~40px at 980px width)
    rend_arr = np.array(rend)
    rend_arr[:40] = np.array(orig)[:40]          # replace toolbar with orig so it doesn't pollute score
    rend = Image.fromarray(rend_arr)
    return orig, rend


# ── Core metric ───────────────────────────────────────────────────────
def compute_metric(orig, rend):
    """
    Returns a composite score (lower = better) plus a breakdown dict.
    Score = MSE_norm + 100*(1-SSIM)
    """
    o = np.array(orig, dtype=np.float64)
    r = np.array(rend, dtype=np.float64)

    # Global
    mse_val  = float(np.mean((o - r)**2))
    mse_norm = mse_val / (255.0**2)              # normalised 0-1
    ssim_val = float(ssim(o, r, channel_axis=2, data_range=255))
    score    = mse_norm * 100 + (1 - ssim_val) * 100

    # Regional breakdown (split into quadrants + sidebar)
    H, W = o.shape[:2]
    sb_w = int(W * 0.379)                        # sidebar ~37.9%

    def region_score(oa, ra):
        m = float(np.mean((oa.astype(np.float64) - ra.astype(np.float64))**2)) / (255.0**2)
        s = float(ssim(oa, ra, channel_axis=2, data_range=255))
        return round(m * 100 + (1 - s) * 100, 3)

    breakdown = {
        "sidebar_top":    region_score(o[:H//2, :sb_w],   r[:H//2, :sb_w]),
        "sidebar_bottom": region_score(o[H//2:, :sb_w],   r[H//2:, :sb_w]),
        "main_top":       region_score(o[:H//3, sb_w:],   r[:H//3, sb_w:]),
        "main_mid":       region_score(o[H//3:2*H//3, sb_w:], r[H//3:2*H//3, sb_w:]),
        "main_bottom":    region_score(o[2*H//3:, sb_w:], r[2*H//3:, sb_w:]),
    }

    return round(score, 4), round(mse_norm * 100, 4), round(ssim_val, 4), breakdown


# ── CSS property patcher ──────────────────────────────────────────────
def get_css_value(html, prop_pattern, group=1):
    """Extract a numeric CSS value from the HTML string."""
    m = re.search(prop_pattern, html)
    return float(m.group(group)) if m else None

def patch_css(html, pattern, new_value_str):
    """Replace first capture group in pattern with new_value_str."""
    return re.sub(pattern, lambda m: m.group(0).replace(m.group(1), new_value_str), html, count=1)


# ── Tweak catalogue ───────────────────────────────────────────────────
# Each tweak: (description, region_it_targets, pattern, delta_fn)
# delta_fn(current_val) → list of candidate values to try

def make_tweaks(breakdown):
    """Return ordered list of tweaks to try, prioritised by worst region."""
    worst = sorted(breakdown, key=lambda k: breakdown[k], reverse=True)
    tweaks = []

    for region in worst:
        score = breakdown[region]
        if score < 0.5:
            continue

        if "sidebar" in region:
            tweaks += [
                ("sidebar_width",
                 r"--sidebar-w:\s*([\d.]+)px",
                 lambda v: [v-6, v-3, v+3, v+6]),
                ("photo_size",
                 r"width:\s*(216)px;\s*\n\s*height:\s*216px",
                 lambda v: [v-8, v-4, v+4, v+8]),
                ("pill_width",
                 r"width:\s*(220)px;\s*\n.*?text-align",
                 lambda v: [v-10, v-5, v+5, v+10]),
                ("sb_padding",
                 r"padding:\s*0\s+(30)px",
                 lambda v: [v-4, v-2, v+2, v+4]),
                ("award_dot",
                 r"margin-right:\s*(12)px;\s*\n\s*flex-shrink",
                 lambda v: [v-4, v-2, v+2, v+4]),
                ("photo_top_pad",
                 r"padding:\s*(36)px 0 40px",
                 lambda v: [v-6, v-3, v+3, v+6]),
            ]

        if "main" in region:
            tweaks += [
                ("name_size",
                 r"font-size:\s*(62)px;\s*\n\s*font-weight:\s*400;\s*\n\s*color:\s*#111",
                 lambda v: [v-4, v-2, v+2, v+4]),
                ("main_padding_top",
                 r"padding:\s*(38)px 44px 50px 46px",
                 lambda v: [v-6, v-3, v+3, v+6]),
                ("main_padding_left",
                 r"padding:\s*38px 44px 50px (46)px",
                 lambda v: [v-4, v-2, v+2, v+4]),
                ("profile_mb",
                 r"margin-bottom:\s*(28)px;\s*\n\}\s*\n\.pline",
                 lambda v: [v-4, v-2, v+2, v+4]),
                ("job_pos_size",
                 r"font-size:\s*(21)px;\s*\n\s*font-weight:\s*700;\s*\n\s*color:\s*#111;\s*\n\}",
                 lambda v: [v-2, v-1, v+1, v+2]),
                ("proj_name_size",
                 r"font-size:\s*(13\.5)px;\s*\n\s*font-weight:\s*400",
                 lambda v: [v-0.5, v+0.5]),
                ("bullet_indent",
                 r"padding-left:\s*(20)px;\s*\n\s*margin:\s*0",
                 lambda v: [v-4, v-2, v+2, v+4]),
                ("job_mb",
                 r"\.job\s*\{\s*margin-bottom:\s*(32)px",
                 lambda v: [v-4, v-2, v+2, v+4]),
                ("sec_head_mb",
                 r"margin-bottom:\s*(22)px;\s*\n\}",
                 lambda v: [v-4, v-2, v+2, v+4]),
            ]

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for t in tweaks:
        if t[0] not in seen:
            seen.add(t[0])
            unique.append(t)
    return unique


# ── Report image ──────────────────────────────────────────────────────
def build_report(history, orig, final_rend):
    """Create a visual report: score chart + before/after comparison."""
    scores = [h["score"] for h in history]
    iters  = list(range(len(scores)))

    W, H = 1800, 900
    report = Image.new("RGB", (W, H), (240, 240, 240))
    draw   = ImageDraw.Draw(report)

    try:
        font_b = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        font   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        font_s = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
    except Exception:
        font_b = font = font_s = ImageFont.load_default()

    # ── Score chart (left 700px) ──
    cx, cy, cw, ch = 40, 80, 660, 380
    draw.rectangle([cx, cy, cx+cw, cy+ch], fill="white", outline=(180,180,180))
    draw.text((cx, 50), "Composite Score per Iteration  (lower = better)", fill=(30,30,30), font=font_b)

    if len(scores) > 1:
        mn, mx = min(scores)*0.95, max(scores)*1.05
        rng = mx - mn or 1
        pts = []
        for i, s in enumerate(scores):
            px = cx + int(i / max(len(scores)-1, 1) * cw)
            py = cy + ch - int((s - mn) / rng * ch)
            pts.append((px, py))

        # Grid lines
        for gi in range(5):
            gy = cy + int(gi * ch / 4)
            draw.line([(cx, gy), (cx+cw, gy)], fill=(220,220,220), width=1)
            val = mx - gi * (mx-mn) / 4
            draw.text((cx-60, gy-8), f"{val:.2f}", fill=(100,100,100), font=font_s)

        # Line
        for i in range(len(pts)-1):
            draw.line([pts[i], pts[i+1]], fill=(220, 60, 60), width=3)
        for px, py in pts:
            draw.ellipse([px-5, py-5, px+5, py+5], fill=(220, 60, 60))

        # Annotation: best score
        best_i = scores.index(min(scores))
        bx, by = pts[best_i]
        draw.text((bx+8, by-22), f"Best: {scores[best_i]:.3f}", fill=(0,140,0), font=font_s)

    # Iteration labels
    for i, h in enumerate(history):
        px = cx + int(i / max(len(scores)-1, 1) * cw)
        draw.text((px-10, cy+ch+6), str(i), fill=(80,80,80), font=font_s)
    draw.text((cx + cw//2 - 30, cy+ch+25), "Iteration", fill=(80,80,80), font=font_s)

    # ── History table (below chart) ──
    tx, ty = 40, 510
    draw.text((tx, ty), "Iteration Log", fill=(30,30,30), font=font_b)
    ty += 30
    headers = ["Iter", "Score", "SSIM", "Tweak Applied", "Change"]
    col_w   = [50, 80, 80, 380, 100]
    for j, h_txt in enumerate(headers):
        draw.text((tx + sum(col_w[:j]), ty), h_txt, fill=(60,60,60), font=font)
    ty += 22
    draw.line([(tx, ty), (tx+sum(col_w), ty)], fill=(180,180,180), width=1)
    ty += 4

    for h in history:
        cols = [
            str(h["iter"]),
            f"{h['score']:.3f}",
            f"{h['ssim']:.4f}",
            h.get("tweak", "baseline")[:55],
            h.get("change", "—"),
        ]
        color = (0, 120, 0) if h.get("improved") else (160, 50, 50)
        for j, txt in enumerate(cols):
            draw.text((tx + sum(col_w[:j]), ty), txt, fill=color, font=font_s)
        ty += 20
        if ty > H - 40:
            break

    # ── Before / After (right side) ──
    th = H - 40
    tw = int(orig.width * th / orig.height)
    orig_r = orig.resize((tw, th), Image.LANCZOS)
    rend_r = final_rend.resize((tw, th), Image.LANCZOS)

    rx1 = 720
    if rx1 + tw < W:
        report.paste(orig_r,  (rx1, 20))
        draw.text((rx1, 2), "ORIGINAL", fill=(30,30,180), font=font_b)

    rx2 = rx1 + tw + 10
    if rx2 + tw < W:
        report.paste(rend_r, (rx2, 20))
        draw.text((rx2, 2), "RENDERED (best)", fill=(0,130,0), font=font_b)

    return report


# ══════════════════════════════════════════════════════════════════════
#  MAIN OPTIMISATION LOOP
# ══════════════════════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("  RESUME CSS OPTIMISER")
    print("=" * 60)

    # Read original HTML
    with open(HTML_PATH, "r") as f:
        best_html = f.read()

    # Load original reference
    orig_img = Image.open(ORIGINAL_PATH).convert("RGB").resize(COMPARE_SIZE, Image.LANCZOS)

    # Baseline render
    print("\n[0] Rendering baseline...")
    shutil.copy(HTML_PATH, "/tmp/resume_current.html")
    render_html("/tmp/resume_current.html", RENDER_PATH)
    orig_c, rend_c = load_pair(ORIGINAL_PATH, RENDER_PATH)
    best_score, best_mse, best_ssim, best_breakdown = compute_metric(orig_c, rend_c)
    best_rend = rend_c.copy()

    history = [{
        "iter": 0, "score": best_score, "ssim": best_ssim,
        "mse": best_mse, "breakdown": best_breakdown,
        "tweak": "baseline", "change": "—", "improved": True
    }]

    print(f"   Baseline  →  score={best_score:.4f}  SSIM={best_ssim:.4f}  MSE={best_mse:.4f}")
    print(f"   Region breakdown: {best_breakdown}")

    no_improve_count = 0

    for iteration in range(1, MAX_ITERATIONS + 1):
        print(f"\n[{iteration}] Building tweak candidates...")
        tweaks = make_tweaks(best_breakdown)

        if not tweaks:
            print("   No more meaningful tweaks. Stopping.")
            break

        improved_this_iter = False

        for tweak_name, pattern, delta_fn in tweaks:
            # Extract current value
            m = re.search(pattern, best_html)
            if not m:
                continue
            try:
                current_val = float(m.group(1))
            except (ValueError, IndexError):
                continue

            candidates = delta_fn(current_val)
            print(f"   Testing tweak '{tweak_name}' (current={current_val}) → {candidates}")

            for candidate in candidates:
                if candidate <= 0:
                    continue
                test_html = patch_css(best_html, pattern, str(round(candidate, 2)))

                # Write temp file and render
                tmp_html = f"/tmp/resume_tweak_{iteration}.html"
                with open(tmp_html, "w") as f:
                    f.write(test_html)
                if not render_html(tmp_html, RENDER_PATH):
                    continue

                orig_t, rend_t = load_pair(ORIGINAL_PATH, RENDER_PATH)
                score, mse_v, ssim_v, breakdown = compute_metric(orig_t, rend_t)
                print(f"      {tweak_name}={candidate:.2f}  →  score={score:.4f}  SSIM={ssim_v:.4f}")

                if score < best_score:
                    improvement = best_score - score
                    print(f"      ✓ IMPROVED by {improvement:.4f}!")
                    best_score    = score
                    best_mse      = mse_v
                    best_ssim     = ssim_v
                    best_breakdown = breakdown
                    best_html     = test_html
                    best_rend     = rend_t.copy()
                    improved_this_iter = True

                    history.append({
                        "iter": iteration, "score": score, "ssim": ssim_v,
                        "mse": mse_v, "breakdown": breakdown,
                        "tweak": tweak_name,
                        "change": f"{current_val:.1f}→{candidate:.1f}",
                        "improved": True
                    })
                    break   # move on to next tweak after any improvement

            if improved_this_iter:
                break       # restart tweak loop with updated breakdown

        if not improved_this_iter:
            no_improve_count += 1
            history.append({
                "iter": iteration, "score": best_score, "ssim": best_ssim,
                "mse": best_mse, "breakdown": best_breakdown,
                "tweak": "none", "change": "no improvement", "improved": False
            })
            print(f"   No improvement this iteration ({no_improve_count}/3).")
            if no_improve_count >= 3:
                print("   Stopping early — metric plateaued.")
                break
        else:
            no_improve_count = 0

    # ── Save best HTML ────────────────────────────────────────────────
    with open(BEST_HTML_PATH, "w") as f:
        f.write(best_html)
    # Also overwrite main HTML with best
    with open(HTML_PATH, "w") as f:
        f.write(best_html)
    print(f"\nBest HTML saved → {BEST_HTML_PATH}")
    print(f"HTML also updated → {HTML_PATH}")

    # ── Final render for report ───────────────────────────────────────
    render_html(BEST_HTML_PATH, RENDER_PATH)
    _, final_rend = load_pair(ORIGINAL_PATH, RENDER_PATH)

    # ── Build and save report ─────────────────────────────────────────
    print("Building report image...")
    report = build_report(history, orig_img, final_rend)
    report.save(REPORT_PATH)
    print(f"Report saved → {REPORT_PATH}")

    # ── Summary ───────────────────────────────────────────────────────
    baseline = history[0]["score"]
    final    = best_score
    pct      = (baseline - final) / baseline * 100 if baseline else 0
    print("\n" + "=" * 60)
    print(f"  FINAL RESULTS")
    print(f"  Baseline score : {baseline:.4f}")
    print(f"  Best score     : {final:.4f}")
    print(f"  Improvement    : {pct:.1f}%")
    print(f"  Final SSIM     : {best_ssim:.4f}  (1.0 = perfect)")
    print(f"  Region scores  : {best_breakdown}")
    print("=" * 60)

    return history


if __name__ == "__main__":
    main()
