# streamlit_app.py — MoviePy, sneller renderen met lagere resolutie/kwaliteit
import os, re, time
import numpy as np
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

# --- Pillow compat: LANCZOS + alias voor ANTIALIAS (Pillow 10+) ---
try:
    _RESAMPLING = Image.Resampling.LANCZOS  # Pillow 10+
except AttributeError:
    _RESAMPLING = Image.LANCZOS             # oudere Pillow
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = _RESAMPLING

# --- Paden/constanten ---
APP_DIR = os.path.dirname(__file__)
BG_VIDEO = os.path.join(APP_DIR, "background.mp4")       # vaste video
MUSIC    = os.path.join(APP_DIR, "news_tune.mp3")        # vast geluid (optioneel)
LOGO     = os.path.join(APP_DIR, "default_logo.png")     # vast logo
OUT_DIR  = os.path.join(APP_DIR, "output")
os.makedirs(OUT_DIR, exist_ok=True)

TARGET_DURATION = 30   # SEC — ALTIJD MAX 30s
TARGET_FPS = 24        # Lager fps = sneller renderen

st.set_page_config(page_title="MNWS TikTok — sneller renderen", layout="centered")
st.title("🎬 MNWS TikTok — vaste video + audio + logo (snel, 30s)")

# ----------------- Helpers -----------------
def load_font(size: int):
    for p in [
        "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf",  "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]:
        if os.path.isfile(p):
            try:
                return ImageFont.truetype(p, size=size)
            except Exception:
                pass
    return ImageFont.load_default()

def wrap_text(draw, text, font, max_width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textbbox((0, 0), t, font=font)[2] <= max_width or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

def make_overlay(
    w, h, title, desc,
    title_font_size=58, desc_font_size=40,
    txt="#000000", bar="#FFFFFF",
    opacity=0.85, top=220, padding=24, radius=28
):
    """Witte (semi-transparante) balk met titel + beschrijving (onafhankelijke fontgroottes)."""
    img = Image.new("RGBA", (w, h), (0,0,0,0))
    d   = ImageDraw.Draw(img)
    fT  = load_font(title_font_size)
    fD  = load_font(desc_font_size)

    lines = []
    max_w = int(w*0.9)
    for ln in wrap_text(d, title, fT, max_w): lines.append(("t", ln))
    if desc.strip():
        lines.append(("gap",""))
        for ln in wrap_text(d, desc, fD, max_w): lines.append(("d", ln))

    heights, widths = [], []
    for kind, ln in lines:
        f  = fT if kind in ("t","gap") else fD
        bb = d.textbbox((0,0), ln, font=f)
        lw = bb[2]-bb[0]
        if ln:
            lh = bb[3]-bb[1]
        else:
            lh = max(12, int(min(title_font_size, desc_font_size) * 0.35))
        widths.append(lw); heights.append(lh)

    txt_w = max(widths) if widths else 0
    txt_h = sum(heights) + (len(lines)-1)*int(min(title_font_size, desc_font_size)*0.25)

    box_w = min(txt_w + padding*2, int(w*0.95))
    box_h = txt_h + padding*2
    x = (w - box_w)//2
    y = max(0, min(h - box_h, top))

    # Balkkleur
    r,g,b = (255,255,255)
    if bar.startswith("#") and len(bar) in (4,7):
        if len(bar)==4: bar = "#" + "".join([c*2 for c in bar[1:]])
        r,g,b = int(bar[1:3],16), int(bar[3:5],16), int(bar[5:7],16)
    a = int(255*float(opacity))
    d.rounded_rectangle((x,y,x+box_w,y+box_h), radius=radius, fill=(r,g,b,a))

    # Tekst
    ty = y + padding
    spacing = int(min(title_font_size, desc_font_size) * 0.25)
    for i,(kind, ln) in enumerate(lines):
        f = fT if kind in ("t","gap") else fD
        lw = d.textbbox((0,0), ln, font=f)[2]
        lx = x + (box_w - lw)//2
        if ln: d.text((lx, ty), ln, font=f, fill=txt)
        ty += heights[i] + spacing

    return img

def sanitize(text: str) -> str:
    text = re.sub(r"[^\w\-]+","_", text.strip())
    return text[:60].strip("_") or f"video_{int(time.time())}"

def make_cover_video(video_path, W, H, duration=30):
    """Altijd exact 'duration' seconden: subclip of loop, daarna hard cap; cover crop naar (W,H)."""
    from moviepy.editor import VideoFileClip
    clip = VideoFileClip(video_path)

    if clip.duration >= duration:
        base = clip.subclip(0, duration)
    else:
        loops = int(duration // clip.duration) + 1
        base = clip.loop(n=loops).subclip(0, duration)

    # schalen en croppen naar W×H
    scale = max(W/base.w, H/base.h)
    base = base.resize(scale).crop(
        x_center=base.w*scale/2,
        y_center=base.h*scale/2,
        width=W,
        height=H
    )

    # extra zekerheid: hard cap
    return base.subclip(0, duration)

# ----------------- UI -----------------
title = st.text_input("Titel", "Voorbeeldtitel")
desc  = st.text_area("Korte beschrijving", "Korte uitleg of context bij dit nieuws.")

col1, col2 = st.columns(2)
with col1:
    res = st.selectbox("Resolutie (vertical)", ["1080x1920 (HQ)", "720x1280 (sneller)"], index=1)
    if res.startswith("1080"):
        W, H = 1080, 1920
    else:
        W, H = 720, 1280
    logo_width  = st.slider("Logo breedte (px)", 80, int(W*0.8), min(220, int(W*0.4)))
    top_offset  = st.slider("Titel/tekst positie (px vanaf boven)", 0, int(H*0.8), int(H*0.20))
with col2:
    title_font_size = st.slider("Titel lettergrootte", 28, 120, 56 if W==720 else 58)
    desc_font_size  = st.slider("Beschrijving lettergrootte", 20, 100, 36 if W==720 else 40)
    text_color  = st.color_picker("Tekstkleur", "#000000")
    bar_color   = st.color_picker("Balkkleur", "#FFFFFF")
    bar_opacity = st.slider("Balk opaciteit", 0.0, 1.0, 0.85)

if st.button("▶️ Render 30s video (sneller)"):
    try:
        # Preflight
        if not os.path.isfile(BG_VIDEO): st.error("'background.mp4' ontbreekt"); st.stop()
        if not os.path.isfile(LOGO):     st.error("'default_logo.png' ontbreekt"); st.stop()

        # Imports pas hier (betere foutmelding als package mist)
        from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, afx

        # Vooruitgang UI
        step = st.empty()
        prog = st.progress(0)
        step.write("🎞️ Video voorbereiden…")
        prog.progress(10)

        # Video: ALTIJD exact 30s, cover crop naar gekozen resolutie
        bg = make_cover_video(BG_VIDEO, W, H, duration=TARGET_DURATION)

        step.write("🖼️ Overlay renderen…")
        prog.progress(35)
        ov_img  = make_overlay(
            W, H, title, desc,
            title_font_size=title_font_size,
            desc_font_size=desc_font_size,
            txt=text_color, bar=bar_color,
            opacity=bar_opacity, top=top_offset
        )
        ov_clip = ImageClip(np.array(ov_img)).set_duration(TARGET_DURATION)

        # Logo
        step.write("🏷️ Logo plaatsen…")
        prog.progress(55)
        pil_logo = Image.open(LOGO).convert("RGBA")
        ratio    = logo_width / pil_logo.width
        pil_logo = pil_logo.resize((logo_width, int(pil_logo.height*ratio)), _RESAMPLING)
        logo_clip= ImageClip(np.array(pil_logo)).set_duration(TARGET_DURATION).set_position((24,24))

        # Compositie
        step.write("🎬 Compositie samenstellen…")
        prog.progress(70)
        layers = [bg, ov_clip, logo_clip]
        final  = CompositeVideoClip(layers, size=(W, H))

        # Audio (altijd hard cap 30s, NIET loopen)
        audioclip = None
        if os.path.isfile(MUSIC):
            try:
                step.write("🔊 Audio knippen tot 30s…")
                prog.progress(80)
                whole = AudioFileClip(MUSIC)
                audioclip = whole.subclip(0, min(TARGET_DURATION, getattr(whole, "duration", TARGET_DURATION)))
                # Fade in/out + volume
                audioclip = afx.audio_fadein(audioclip, 0.6)
                audioclip = afx.audio_fadeout(audioclip, 0.6)
                audioclip = audioclip.volumex(0.5)
                final = final.set_audio(audioclip)
            except Exception:
                pass

        # Export — lagere kwaliteit/meer snelheid:
        # - preset="veryfast" (sneller) 
        # - CRF 27 (kleinere file; hoger getal = lagere kwaliteit/snellere encoding)
        out_path = os.path.join(OUT_DIR, f"{sanitize(title)}_{W}x{H}_24fps.mp4")
        step.write("💾 Exporteren naar MP4…")
        prog.progress(90)
        final.write_videofile(
            out_path,
            fps=TARGET_FPS,
            codec="libx264",
            audio_codec="aac",
            threads=4,
            preset="veryfast",
            ffmpeg_params=["-crf", "27", "-pix_fmt", "yuv420p"]
        )

        try:
            if audioclip: audioclip.close()
            final.close()
        except Exception:
            pass

        prog.progress(100)
        step.write("✅ Klaar!")
        st.success(f"Gereed: {os.path.basename(out_path)}")
        with open(out_path, "rb") as f:
            st.download_button("⬇ Download MP4", f, file_name=os.path.basename(out_path), mime="video/mp4")

    except ModuleNotFoundError as e:
        st.error(f"Package ontbreekt: {e}. Installeer met:  pip install streamlit moviepy Pillow numpy imageio imageio-ffmpeg")
    except Exception as e:
        st.error(f"Fout bij renderen: {e}")
