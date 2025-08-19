# streamlit_app.py  (FFmpeg-variant, snel renderen)
import os, re, time, shlex, subprocess, tempfile, shutil
import streamlit as st

APP_DIR = os.path.dirname(__file__)
BG_VIDEO = os.path.join(APP_DIR, "background.mp4")
LOGO     = os.path.join(APP_DIR, "default_logo.png")
MUSIC    = os.path.join(APP_DIR, "news_tune.mp3")
OUT_DIR  = os.path.join(APP_DIR, "output")
os.makedirs(OUT_DIR, exist_ok=True)

TARGET_DURATION = 30  # seconden hard cap

st.set_page_config(page_title="MNWS TikTok — FFmpeg snel", layout="centered")
st.title("🎬 MNWS TikTok — FFmpeg (snel), 30s hard cap")

# ---------- helpers ----------
def find_font():
    """Zoek een bruikbaar TTF font voor drawtext (Windows/Linux/Cloud)."""
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None

def hex_to_rgba_str(hex_color, alpha):
    """'#RRGGBB' -> 'r:g:b@alpha' voor drawtext boxcolor."""
    if not hex_color.startswith("#"):
        return f"255:255:255@{alpha}"
    if len(hex_color) == 4:
        hex_color = "#" + "".join([c*2 for c in hex_color[1:]])
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return f"{r}:{g}:{b}@{alpha}"

def hex_to_rgb_str(hex_color):
    if not hex_color.startswith("#"):
        return "255:255:255"
    if len(hex_color) == 4:
        hex_color = "#" + "".join([c*2 for c in hex_color[1:]])
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return f"{r}:{g}:{b}"

def ensure_ffmpeg():
    exe = shutil.which("ffmpeg")
    if not exe:
        st.error("❌ FFmpeg niet gevonden. Installeer FFmpeg en voeg het toe aan je PATH.\n\n"
                 "- Windows: download een build van https://www.gyan.dev/ffmpeg/builds/ (release full) en voeg de map `bin` toe aan PATH.\n"
                 "- macOS: `brew install ffmpeg`\n"
                 "- Linux/Cloud: meestal al aanwezig.")
        st.stop()
    return exe

def write_textfile(txt: str):
    """Schrijf tekst naar tijdelijk bestand (om escaping-gedoe in drawtext te vermijden)."""
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8")
    tf.write(txt.replace("\r\n", "\n").replace("\r", "\n"))
    tf.flush()
    tf.close()
    return tf.name

def build_ffmpeg_cmd(ffmpeg, W, H, logo_w, title_txt, desc_txt,
                     title_fs, desc_fs, title_y, desc_y,
                     text_rgb, box_rgba, box_border, out_path):
    """
    Bouw één ffmpeg command dat:
      - background.mp4 covert naar 30s (loop/trim) en cover-cropt naar (W,H)
      - logo scaled en overlay linksboven
      - titel + desc met drawtext (box=1)
      - audio trimmed naar 30s met fade in/out en volume
    """

    # Inputs:
    #  0: background
    #  1: logo (png)
    #  2: music (mp3) (optioneel)
    inputs = [
        "-stream_loop", "-1",  # loop de input (alleen geldig voor sommige containers; we cap met -t)
        "-t", str(TARGET_DURATION),
        "-i", BG_VIDEO,
        "-i", LOGO,
    ]
    have_music = os.path.isfile(MUSIC)
    if have_music:
        inputs += ["-i", MUSIC]

    # Tekst via textfile (betrouwbaar i.v.m. escaping)
    title_file = write_textfile(title_txt)
    desc_file  = write_textfile(desc_txt)

    fontfile = find_font()
    if not fontfile:
        st.warning("⚠️ Geen systeemfont gevonden — FFmpeg drawtext kan falen zonder fontfile.")
        fontfile = ""  # laat ffmpeg zelf kiezen (kan mislukken)

    # kleurstrings
    fontcolor = f"rgb({text_rgb})"
    boxcolor  = f"{box_rgba}"  # r:g:b@a
    # overlay pipeline:
    # [0:v] scale+crop -> [bg]
    # [1:v] scale logo -> [logo]
    # [bg][logo] overlay -> [v0]
    # [v0] drawtext (title) -> [v1]
    # [v1] drawtext (desc)  -> [v]
    vf = [
        f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H}[bg];"
        f"[1:v]scale={logo_w}:-1[logo];"
        f"[bg][logo]overlay=24:24[v0];"
        f"[v0]drawtext=fontfile='{fontfile}':"
        f"textfile='{title_file}':"
        f"fontsize={title_fs}:fontcolor={fontcolor}:"
        f"x=(w-text_w)/2:y={title_y}:"
        f"box=1:boxcolor={boxcolor}:boxborderw={box_border}[v1];"
        f"[v1]drawtext=fontfile='{fontfile}':"
        f"textfile='{desc_file}':"
        f"fontsize={desc_fs}:fontcolor={fontcolor}:"
        f"x=(w-text_w)/2:y={desc_y}:"
        f"box=1:boxcolor={boxcolor}:boxborderw={box_border}[v]"
    ]
    vmap = ["-map", "[v]"]

    # audio: trim/fade/volume
    if have_music:
        # cut to 30s, fade in/out, volume 0.5
        af = f"atrim=0:{TARGET_DURATION},afade=t=in:ss=0:d=0.6,afade=t=out:st={TARGET_DURATION-0.6}:d=0.6,volume=0.5"
        amap = ["-map", "2:a", "-af", af]
    else:
        # geen audio
        amap = []

    # encoding
    enc = [
        "-shortest",
        "-t", str(TARGET_DURATION),
        "-c:v", "libx264",
        "-preset", "faster",
        "-r", "30",
        "-pix_fmt", "yuv420p",
    ]
    if have_music:
        enc += ["-c:a", "aac", "-b:a", "128k"]

    cmd = [ffmpeg, "-y"] + inputs + [
        "-filter_complex", vf[0],
    ] + vmap + amap + enc + [out_path]

    return cmd, (title_file, desc_file)

def run_ffmpeg_with_progress(cmd, duration_s=30):
    """
    Draai ffmpeg en update Streamlit progress o.b.v. 'time=' uit stderr.
    """
    prog = st.progress(0)
    status = st.empty()

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    last_pct = 0
    try:
        while True:
            line = proc.stderr.readline()
            if not line:
                if proc.poll() is not None:
                    break
                time.sleep(0.05)
                continue
            if "time=" in line:
                # parse tijdcode
                # e.g. time=00:00:12.34
                try:
                    tstr = line.split("time=")[1].split(" ")[0].strip()
                    hh, mm, ss = tstr.split(":")
                    cur = float(hh)*3600 + float(mm)*60 + float(ss)
                    pct = int(min(100, max(0, (cur / duration_s) * 100)))
                    if pct != last_pct:
                        prog.progress(pct)
                        status.write(f"🚧 Renderen… {pct}%")
                        last_pct = pct
                except Exception:
                    pass
    finally:
        proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("FFmpeg faalde. Check of FFmpeg aanwezig is en of de bestanden kloppen.")
    prog.progress(100)
    status.write("✅ Klaar!")

# ---------- UI ----------
title   = st.text_input("Titel", "Voorbeeldtitel")
desc    = st.text_area("Korte beschrijving", "Korte uitleg of context bij dit nieuws.")

col1, col2 = st.columns(2)
with col1:
    res = st.selectbox("Resolutie (vertical)", ["1080x1920", "720x1280"], index=0)
    W, H = map(int, res.split("x"))
    logo_w = st.slider("Logo breedte (px)", 80, 600, 220)
    box_opacity = st.slider("Box opaciteit", 0.0, 1.0, 0.85)
with col2:
    title_fs = st.slider("Titel fontsize", 30, 120, 64)
    desc_fs  = st.slider("Beschrijving fontsize", 20, 100, 42)
    title_y  = st.slider("Titel Y (px vanaf boven)", 0, H-200, int(H*0.20))
    desc_y   = st.slider("Beschrijving Y (px vanaf boven)", 0, H-100, int(H*0.55))

text_color = st.color_picker("Tekstkleur", "#000000")
box_color  = st.color_picker("Boxkleur", "#FFFFFF")

if st.button("▶️ Render 30s video (FFmpeg)"):
    try:
        if not os.path.isfile(BG_VIDEO):
            st.error("'background.mp4' ontbreekt in deze map.")
            st.stop()
        if not os.path.isfile(LOGO):
            st.error("'default_logo.png' ontbreekt in deze map.")
            st.stop()

        ffmpeg = ensure_ffmpeg()

        out_name = re.sub(r"[^\w\-]+","_", title.strip()) or f"video_{int(time.time())}"
        out_path = os.path.join(OUT_DIR, f"{out_name}_{W}x{H}.mp4")

        text_rgb = hex_to_rgb_str(text_color)
        box_rgba = hex_to_rgba_str(box_color, box_opacity)

        cmd, tmp_txts = build_ffmpeg_cmd(
            ffmpeg, W, H, logo_w,
            title_txt=title, desc_txt=desc,
            title_fs=title_fs, desc_fs=desc_fs,
            title_y=title_y, desc_y=desc_y,
            text_rgb=text_rgb, box_rgba=box_rgba, box_border=20,
            out_path=out_path
        )

        st.write("🛠️ FFmpeg command:")
        st.code(" ".join(shlex.quote(c) for c in cmd), language="bash")

        run_ffmpeg_with_progress(cmd, duration_s=TARGET_DURATION)

        # opruimen temp textfiles
        for p in tmp_txts:
            try: os.unlink(p)
            except Exception: pass

        st.success(f"Gereed: {os.path.basename(out_path)}")
        with open(out_path, "rb") as f:
            st.download_button("⬇ Download MP4", f, file_name=os.path.basename(out_path), mime="video/mp4")

    except Exception as e:
        st.error(f"Fout bij renderen: {e}")
