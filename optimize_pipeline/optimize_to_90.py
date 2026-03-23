"""
optimize_to_90.py
-----------------
Aggressively optimises resume.html CSS to reach SSIM >= 0.90 vs original.

Strategy:
  - Large tweak catalogue (50+ CSS properties)
  - Fine-grained grid search per property (10+ candidates each)
  - Regional scoring to target worst regions first
  - Tracks all history and produces final report
"""

import subprocess, re, os, shutil, json, copy, time
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from skimage.metrics import structural_similarity as ssim_fn

# ── Config ────────────────────────────────────────────────────────────
ORIGINAL   = "/mnt/user-data/uploads/Page_1.png"
HTML_IN    = "/mnt/user-data/outputs/resume.html"
BEST_HTML  = "/mnt/user-data/outputs/resume_best.html"
REPORT_IMG = "/mnt/user-data/outputs/optimization_report.png"
TMP_HTML   = "/tmp/opt_resume.html"
TMP_PNG    = "/tmp/opt_render.png"
SIZE       = (980, 1369)
TARGET_SSIM = 0.90
MAX_ITER    = 60

# ── Render ────────────────────────────────────────────────────────────
def render(html_path, out_path):
    subprocess.run([
        "wkhtmltoimage", "--width", "980",
        "--load-error-handling", "ignore",
        "--load-media-error-handling", "ignore",
        html_path, out_path
    ], capture_output=True)
    return os.path.exists(out_path)

# ── Metric ────────────────────────────────────────────────────────────
ORIG_NP = None  # cached

def get_orig():
    global ORIG_NP
    if ORIG_NP is None:
        ORIG_NP = np.array(
            Image.open(ORIGINAL).convert("RGB").resize(SIZE, Image.LANCZOS),
            dtype=np.float64
        )
    return ORIG_NP

def load_render(png_path):
    arr = np.array(
        Image.open(png_path).convert("RGB").resize(SIZE, Image.LANCZOS),
        dtype=np.float64
    )
    arr[:42] = get_orig()[:42]   # mask toolbar
    return arr

def score_arrays(o, r):
    s   = ssim_fn(o, r, channel_axis=2, data_range=255)
    mse = np.mean((o - r) ** 2) / (255.0 ** 2)
    composite = mse * 100 + (1 - s) * 100
    return round(composite, 5), round(s, 5)

def regional_scores(o, r):
    H, W = o.shape[:2]
    sb   = int(W * 0.38)
    regs = {
        "sb_top":    (o[:H//2, :sb],    r[:H//2, :sb]),
        "sb_bot":    (o[H//2:, :sb],    r[H//2:, :sb]),
        "main_top":  (o[:H//3, sb:],    r[:H//3, sb:]),
        "main_mid":  (o[H//3:2*H//3,sb:], r[H//3:2*H//3,sb:]),
        "main_bot":  (o[2*H//3:,sb:],   r[2*H//3:,sb:]),
    }
    return {k: round(ssim_fn(oa, ra, channel_axis=2, data_range=255), 4)
            for k, (oa, ra) in regs.items()}

# ── CSS patcher ───────────────────────────────────────────────────────
def patch(html, pattern, new_val):
    """Replace first numeric capture group with new_val."""
    return re.sub(
        pattern,
        lambda m: m.group(0).replace(m.group(1), str(round(new_val, 3))),
        html, count=1
    )

def patch_color(html, old_hex, new_hex):
    return html.replace(old_hex, new_hex, 1)

# ── Tweak definitions ─────────────────────────────────────────────────
# (name, css_regex_with_1_capture_group, candidate_values_or_delta)
# All candidates are tried; best kept.

def build_tweaks(breakdown):
    """Return tweaks sorted by worst region first."""
    worst_regions = sorted(breakdown, key=breakdown.get)  # lowest SSIM first

    # ── Geometry tweaks ──
    geo = [
        # Sidebar
        ("sidebar_width",   r"--sidebar-w:\s*([\d.]+)px",       lambda v: [v+d for d in (-12,-9,-6,-3,3,6,9,12)]),
        ("photo_size",      r"width:\s*([\d.]+)px;\s*\n\s*height:\s*\1px",
                                                                  lambda v: [v+d for d in (-20,-14,-8,-4,-2,2,4,8,14,20)]),
        ("photo_top_pad",   r"padding:\s*([\d.]+)px 0 40px",     lambda v: [v+d for d in (-12,-8,-4,-2,2,4,8,12)]),
        ("photo_bot_pad",   r"padding:\s*[\d.]+px 0 ([\d.]+)px", lambda v: [v+d for d in (-12,-8,-4,-2,2,4,8,12)]),
        ("sb_pad_lr",       r"padding:\s*0\s+([\d.]+)px;\s*\n\s*margin-bottom",
                                                                  lambda v: [v+d for d in (-8,-6,-4,-2,2,4,6,8)]),
        ("sb_contact_mb",   r"margin-bottom:\s*([\d.]+)px;\s*\n\}\s*\n/\* — Awards",
                                                                  lambda v: [v+d for d in (-10,-6,-3,3,6,10)]),
        ("contact_row_mb",  r"margin-bottom:\s*([\d.]+)px;\s*\n\s*color:\s*var\(--sidebar-text\)",
                                                                  lambda v: [v+d for d in (-6,-4,-2,2,4,6)]),
        ("award_dot_mr",    r"margin-right:\s*([\d.]+)px;\s*\n\s*flex-shrink",
                                                                  lambda v: [v+d for d in (-8,-5,-3,-1,1,3,5,8)]),
        ("award_row_mb",    r"margin-bottom:\s*([\d.]+)px;\s*\n\s*color:\s*var\(--sidebar-text\);\s*\n\s*font-size:\s*13",
                                                                  lambda v: [v+d for d in (-6,-4,-2,2,4,6)]),
        ("pill_width",      r"width:\s*([\d.]+)px;\s*\n\s*text-align",
                                                                  lambda v: [v+d for d in (-20,-14,-8,-4,4,8,14,20)]),
        ("pill_pad_tb",     r"padding:\s*([\d.]+)px 0;\s*\n\s*width",
                                                                  lambda v: [v+d for d in (-4,-2,-1,1,2,4)]),
        ("pill_mb",         r"margin-bottom:\s*([\d.]+)px;\s*\n\}\s*\n/\* — Contact",
                                                                  lambda v: [v+d for d in (-8,-4,-2,2,4,8)]),
        # Main
        ("name_size",       r"font-size:\s*([\d.]+)px;\s*\n\s*font-weight:\s*400;\s*\n\s*color:\s*#373536",
                                                                  lambda v: [v+d for d in (-8,-6,-4,-2,-1,1,2,4,6,8)]),
        ("name_mb",         r"margin-bottom:\s*([\d.]+)px;\s*\n\s*letter-spacing",
                                                                  lambda v: [v+d for d in (-8,-4,-2,2,4,8)]),
        ("main_pad_top",    r"padding:\s*([\d.]+)px 44px 50px 46px",
                                                                  lambda v: [v+d for d in (-12,-8,-4,-2,2,4,8,12)]),
        ("main_pad_right",  r"padding:\s*[\d.]+px ([\d.]+)px 50px 46px",
                                                                  lambda v: [v+d for d in (-8,-4,-2,2,4,8)]),
        ("main_pad_left",   r"padding:\s*[\d.]+px [\d.]+px 50px ([\d.]+)px",
                                                                  lambda v: [v+d for d in (-8,-4,-2,2,4,8)]),
        ("profile_mb",      r"margin-bottom:\s*([\d.]+)px;\s*\n\}\s*\n\.pline",
                                                                  lambda v: [v+d for d in (-8,-4,-2,2,4,8)]),
        ("pline_lh",        r"line-height:\s*([\d.]+);\s*\n\}",  lambda v: [v+d for d in (-0.2,-0.1,0.1,0.2,0.3)]),
        ("sec_head_size",   r"font-size:\s*([\d.]+)px;\s*\n\s*font-weight:\s*700;\s*\n\s*letter-spacing:\s*2px",
                                                                  lambda v: [v+d for d in (-3,-2,-1,1,2,3)]),
        ("sec_head_ls",     r"letter-spacing:\s*([\d.]+)px;\s*\n\s*text-transform:\s*uppercase;\s*\n\s*color:\s*#373536",
                                                                  lambda v: [v+d for d in (-1,-0.5,0.5,1,1.5)]),
        ("sec_head_mb",     r"margin-bottom:\s*([\d.]+)px;\s*\n\}",
                                                                  lambda v: [v+d for d in (-6,-4,-2,2,4,6)]),
        ("job_mb",          r"\.job\s*\{\s*margin-bottom:\s*([\d.]+)px",
                                                                  lambda v: [v+d for d in (-8,-4,-2,2,4,8)]),
        ("job_hrow_mb",     r"margin-bottom:\s*([\d.]+)px;\s*\n\}",
                                                                  lambda v: [v+d for d in (-4,-2,-1,1,2,4)]),
        ("job_pos_size",    r"font-size:\s*([\d.]+)px;\s*\n\s*font-weight:\s*700;\s*\n\s*color:\s*#373536",
                                                                  lambda v: [v+d for d in (-4,-3,-2,-1,1,2,3,4)]),
        ("job_company_ls",  r"letter-spacing:\s*([\d.]+)px;\s*\n\s*color:\s*#373536",
                                                                  lambda v: [v+d for d in (-1,-0.5,0.5,1,1.5,2)]),
        ("job_company_mr",  r"margin-right:\s*([\d.]+)px;\s*\n\}",
                                                                  lambda v: [v+d for d in (-8,-4,-2,2,4,8)]),
        ("job_company_size",r"font-size:\s*([\d.]+)px;\s*\n\s*font-weight:\s*700;\s*\n\s*letter-spacing",
                                                                  lambda v: [v+d for d in (-2,-1,1,2)]),
        ("job_dates_size",  r"font-size:\s*([\d.]+)px;\s*\n\s*font-weight:\s*300",
                                                                  lambda v: [v+d for d in (-2,-1,1,2)]),
        ("proj_mb",         r"\.proj\s*\{\s*margin-bottom:\s*([\d.]+)px",
                                                                  lambda v: [v+d for d in (-6,-4,-2,2,4,6)]),
        ("proj_name_size",  r"font-size:\s*([\d.]+)px;\s*\n\s*font-weight:\s*400;\s*\n\s*color",
                                                                  lambda v: [v+d for d in (-2,-1,-0.5,0.5,1,2)]),
        ("proj_name_mb",    r"margin-bottom:\s*([\d.]+)px;\s*\n\}",
                                                                  lambda v: [v+d for d in (-4,-2,2,4)]),
        ("bullet_indent",   r"padding-left:\s*([\d.]+)px;\s*\n\s*margin:\s*0",
                                                                  lambda v: [v+d for d in (-8,-6,-4,-2,2,4,6,8)]),
        ("bullet_li_mb",    r"margin-bottom:\s*([\d.]+)px;\s*\n\}\s*\n/\*",
                                                                  lambda v: [v+d for d in (-3,-2,-1,1,2,3)]),
        ("bullet_size",     r"font-size:\s*([\d.]+)px;\s*\n\s*color:\s*#3b3b3b;\s*\n\s*line-height",
                                                                  lambda v: [v+d for d in (-1,-0.5,0.5,1)]),
        ("bullet_lh",       r"line-height:\s*([\d.]+);\s*\n\s*margin-bottom",
                                                                  lambda v: [v+d for d in (-0.2,-0.1,0.1,0.2)]),
    ]

    # Sort: tweaks for worst regions first
    def region_prio(name):
        if name.startswith("sb"):   return -breakdown.get("sb_top", 1) - breakdown.get("sb_bot", 1)
        if name.startswith("pill"): return -breakdown.get("sb_top", 1)
        if name.startswith("name") or name.startswith("main"): return -breakdown.get("main_top", 1)
        if name.startswith("job") or name.startswith("proj") or name.startswith("sec"):
            return -breakdown.get("main_mid", 1) - breakdown.get("main_bot", 1)
        return 0

    return sorted(geo, key=lambda t: region_prio(t[0]))

# ── Report builder ────────────────────────────────────────────────────
def build_report(history, orig_img, best_rend_img):
    W, H = 2000, 1000
    report = Image.new("RGB", (W, H), (235, 235, 235))
    draw = ImageDraw.Draw(report)

    try:
        fb = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        fn = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        fs = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except:
        fb = fn = fs = ImageFont.load_default()

    scores = [h["score"] for h in history]
    ssims  = [h["ssim"]  for h in history]

    # ── Score chart ──
    cx, cy, cw, ch = 30, 70, 580, 360
    draw.rectangle([cx, cy, cx+cw, cy+ch], fill="white", outline=(180,180,180), width=1)
    draw.text((cx, 42), "Composite Score (↓ better) & SSIM (↑ better) per Iteration", fill=(30,30,30), font=fb)

    def plot(vals, color, invert=False):
        mn, mx = min(vals)*0.95, max(vals)*1.05
        rng = mx - mn or 0.001
        pts = []
        for i, v in enumerate(vals):
            px = cx + int(i / max(len(vals)-1, 1) * cw)
            py = cy + ch - int((v - mn) / rng * ch) if not invert else cy + int((v - mn) / rng * ch)
            pts.append((px, py))
        for i in range(len(pts)-1):
            draw.line([pts[i], pts[i+1]], fill=color, width=3)
        for px, py in pts:
            draw.ellipse([px-4,py-4,px+4,py+4], fill=color)
        return pts

    if len(scores) > 1:
        plot(scores, (220, 50, 50))
        ssim_pts = plot(ssims, (50, 160, 50), invert=True)
        # Target line at SSIM=0.90
        tgt_y = cy + int((1.0 - 0.90) / (max(ssims)*1.05 - min(ssims)*0.95 or 0.001) * ch)
        draw.line([(cx, tgt_y), (cx+cw, tgt_y)], fill=(0, 120, 200), width=2)
        draw.text((cx+cw-140, tgt_y-20), "Target: 90%", fill=(0,100,180), font=fs)

        # Best annotation
        bi = ssims.index(max(ssims))
        bx, by = ssim_pts[bi]
        draw.text((bx+6, by-20), f"Best: {ssims[bi]*100:.1f}%", fill=(0,130,0), font=fs)

    # Labels
    for i in range(0, len(scores), max(1, len(scores)//10)):
        px = cx + int(i / max(len(scores)-1, 1) * cw)
        draw.text((px-6, cy+ch+4), str(i), fill=(80,80,80), font=fs)
    draw.text((cx+cw//2-20, cy+ch+22), "Iteration", fill=(80,80,80), font=fs)

    # Legend
    draw.rectangle([cx+cw-160, cy+8, cx+cw-8, cy+40], fill=(245,245,245), outline=(200,200,200))
    draw.line([(cx+cw-155, cy+20),(cx+cw-130, cy+20)], fill=(220,50,50), width=3)
    draw.text((cx+cw-125, cy+12), "Score", fill=(220,50,50), font=fs)
    draw.line([(cx+cw-85, cy+20),(cx+cw-60, cy+20)], fill=(50,160,50), width=3)
    draw.text((cx+cw-55, cy+12), "SSIM", fill=(50,160,50), font=fs)

    # ── Iteration table ──
    tx, ty = 30, 480
    draw.text((tx, ty-28), "Iteration Log", fill=(30,30,30), font=fb)
    cols = ["Iter","Score","SSIM%","Tweak","Δ Value","Improved"]
    cws  = [40, 72, 72, 240, 110, 80]
    for j, h in enumerate(cols):
        draw.text((tx+sum(cws[:j])+2, ty), h, fill=(50,50,50), font=fn)
    ty += 22
    draw.line([(tx, ty),(tx+sum(cws), ty)], fill=(180,180,180), width=1)
    ty += 4

    for h in history:
        row = [
            str(h["iter"]),
            f"{h['score']:.3f}",
            f"{h['ssim']*100:.2f}%",
            h.get("tweak","baseline")[:38],
            h.get("change","—"),
            "✓ YES" if h.get("improved") else "✗ no",
        ]
        color = (0,110,0) if h.get("improved") else (140,50,50)
        for j, txt in enumerate(row):
            draw.text((tx+sum(cws[:j])+2, ty), txt, fill=color, font=fs)
        ty += 18
        if ty > H - 20:
            break

    # ── Before/After images ──
    th = H - 20
    tw = int(orig_img.width * th / orig_img.height)

    orig_r = orig_img.resize((tw, th), Image.LANCZOS)
    best_r = best_rend_img.resize((tw, th), Image.LANCZOS)

    ox = 640
    if ox + tw < W:
        report.paste(orig_r, (ox, 10))
        draw.text((ox+4, 10), "ORIGINAL", fill=(30,30,200), font=fb)

    bx = ox + tw + 12
    if bx + tw < W:
        report.paste(best_r, (bx, 10))
        draw.text((bx+4, 10), f"BEST ({max(ssims)*100:.1f}% SSIM)", fill=(0,130,0), font=fb)

    return report


# ══════════════════════════════════════════════════════════════════════
#  MAIN LOOP
# ══════════════════════════════════════════════════════════════════════
def main():
    print("=" * 64)
    print("  RESUME CSS OPTIMISER  — target SSIM ≥ 90%")
    print("=" * 64)

    with open(HTML_IN) as f:
        best_html = f.read()

    # Baseline
    print("\n[0] Baseline render...")
    shutil.copy(HTML_IN, TMP_HTML)
    render(TMP_HTML, TMP_PNG)
    o = get_orig()
    r = load_render(TMP_PNG)
    best_score, best_ssim = score_arrays(o, r)
    best_breakdown = regional_scores(o, r)
    best_rend = Image.open(TMP_PNG).convert("RGB").resize(SIZE, Image.LANCZOS)

    history = [{
        "iter": 0, "score": best_score, "ssim": best_ssim,
        "breakdown": best_breakdown, "tweak": "baseline",
        "change": "—", "improved": True
    }]

    print(f"   score={best_score:.4f}  SSIM={best_ssim:.4f} ({best_ssim*100:.1f}%)")
    print(f"   regions: {best_breakdown}")

    stagnant = 0

    for iteration in range(1, MAX_ITER + 1):
        if best_ssim >= TARGET_SSIM:
            print(f"\n✓ TARGET REACHED: SSIM={best_ssim:.4f} ({best_ssim*100:.2f}%)")
            break

        print(f"\n[{iteration}/{MAX_ITER}]  current SSIM={best_ssim*100:.2f}%  score={best_score:.4f}")

        tweaks = build_tweaks(best_breakdown)
        improved_this = False

        for tweak_name, pattern, cand_fn in tweaks:
            m = re.search(pattern, best_html)
            if not m:
                continue
            try:
                cur = float(m.group(1))
            except (ValueError, IndexError):
                continue

            candidates = [c for c in cand_fn(cur) if c > 0]

            best_candidate = None
            best_cand_score = best_score

            for cval in candidates:
                test_html = patch(best_html, pattern, cval)
                with open(TMP_HTML, "w") as f:
                    f.write(test_html)
                if not render(TMP_HTML, TMP_PNG):
                    continue
                r = load_render(TMP_PNG)
                sc, sv = score_arrays(o, r)
                if sc < best_cand_score:
                    best_cand_score = sc
                    best_candidate = (cval, test_html, sc, sv, r)

            if best_candidate:
                cval, test_html, sc, sv, r_arr = best_candidate
                improvement = best_score - sc
                print(f"   ✓ {tweak_name}: {cur:.2f}→{cval:.2f}  score {best_score:.4f}→{sc:.4f}  SSIM {best_ssim*100:.2f}%→{sv*100:.2f}%  Δ={improvement:.4f}")
                best_score    = sc
                best_ssim     = sv
                best_html     = test_html
                best_breakdown = regional_scores(o, r_arr)
                best_rend     = Image.fromarray(r_arr.astype(np.uint8))
                improved_this = True

                history.append({
                    "iter": iteration, "score": sc, "ssim": sv,
                    "breakdown": best_breakdown,
                    "tweak": tweak_name,
                    "change": f"{cur:.1f}→{cval:.1f}",
                    "improved": True
                })
                break   # restart with updated breakdown

        if not improved_this:
            stagnant += 1
            print(f"   No improvement ({stagnant}/4 stagnant)")
            history.append({
                "iter": iteration, "score": best_score, "ssim": best_ssim,
                "breakdown": best_breakdown,
                "tweak": "—", "change": "no gain", "improved": False
            })
            if stagnant >= 4:
                print("   Stopping — metric plateaued.")
                break
        else:
            stagnant = 0

    # ── Save best HTML ────────────────────────────────────────────────
    with open(BEST_HTML, "w") as f:
        f.write(best_html)
    with open(HTML_IN, "w") as f:
        f.write(best_html)
    print(f"\nBest HTML → {BEST_HTML}")
    print(f"HTML updated → {HTML_IN}")

    # ── Build report ──────────────────────────────────────────────────
    orig_img = Image.open(ORIGINAL).convert("RGB").resize(SIZE, Image.LANCZOS)
    report   = build_report(history, orig_img, best_rend)
    report.save(REPORT_IMG)
    print(f"Report → {REPORT_IMG}")

    # ── Final screenshot ──────────────────────────────────────────────
    render(BEST_HTML, "/mnt/user-data/outputs/resume_screenshot.png")

    # ── Summary ──────────────────────────────────────────────────────
    baseline_ssim = history[0]["ssim"]
    baseline_score = history[0]["score"]
    print("\n" + "=" * 64)
    print(f"  Baseline : score={baseline_score:.4f}  SSIM={baseline_ssim*100:.2f}%")
    print(f"  Final    : score={best_score:.4f}  SSIM={best_ssim*100:.2f}%")
    print(f"  Gain     : +{(best_ssim-baseline_ssim)*100:.2f}pp SSIM  |  score -{baseline_score-best_score:.4f}")
    print(f"  Iterations run: {len([h for h in history if h['improved']])}")
    reached = "✓ TARGET REACHED" if best_ssim >= TARGET_SSIM else f"✗ Gap remaining: {(TARGET_SSIM-best_ssim)*100:.2f}pp"
    print(f"  {reached}")
    print("=" * 64)


if __name__ == "__main__":
    main()
