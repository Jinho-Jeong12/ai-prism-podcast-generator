import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import subprocess
import os
import json
import threading
import shutil
import uuid
from pathlib import Path

BASE_DIR    = Path(__file__).parent
CONFIG_FILE = BASE_DIR / ".podcast_config.json"

# ─── 기본값 (최초 실행 또는 미설정 시) ────────────────────────
_DEFAULT_CUE_INTRO = str(BASE_DIR / "확정 cue 본 Intro 2.mp3")
_DEFAULT_INTRO     = str(BASE_DIR / "You're listening to AI Prism, from Seoul Economic Daily..mp3")
_DEFAULT_OUTRO     = str(BASE_DIR / "You've been listening to AI Prism, from Seoul Economic Daily..mp3")
_DEFAULT_CUE_OUTRO = str(BASE_DIR / "확정 cue 본 Intro 2.mp3")

_DEFAULT_CATEGORIES = [
    "CEO", "Early Career", "Finance Daily", "Founders", "Front Page Daily",
    "Global", "Industry Daily", "Real Estate", "Retail Investors",
    "Securities Daily", "Stock Investors", "Students & Grads",
]

_DEFAULT_COVERS = {
    "CEO":              str(BASE_DIR / "covers" / "ceos cover.png"),
    "Early Career":     str(BASE_DIR / "covers" / "early career cover.png"),
    "Finance Daily":    str(BASE_DIR / "covers" / "finance daily cover.png"),
    "Founders":         str(BASE_DIR / "covers" / "founders cover.png"),
    "Front Page Daily": str(BASE_DIR / "covers" / "front page daily cover.png"),
    "Global":           str(BASE_DIR / "covers" / "global investors cover.png"),
    "Industry Daily":   str(BASE_DIR / "covers" / "industry daily cover.png"),
    "Real Estate":      str(BASE_DIR / "covers" / "real estate cover.png"),
    "Retail Investors": str(BASE_DIR / "covers" / "retail investors cover.png"),
    "Securities Daily": str(BASE_DIR / "covers" / "securities daily cover.png"),
    "Stock Investors":  str(BASE_DIR / "covers" / "stock investors cover.png"),
    "Students & Grads": str(BASE_DIR / "covers" / "students & grads cover.png"),
}

MAX_TASKS = 6

_MONTHS = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}{['th','st','nd','rd','th'][min(n % 10, 4)]}"


def format_date_english(date_str: str) -> str:
    try:
        parts = date_str.strip().replace("-", "/").split("/")
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        return f"{_MONTHS[month]} {_ordinal(day)}, {year}"
    except Exception:
        return date_str


_FONT_CANDIDATES = [
    r"C:/Windows/Fonts/arialbd.ttf",
    r"C:/Windows/Fonts/arial.ttf",
    r"C:/Windows/Fonts/calibrib.ttf",
    r"C:/Windows/Fonts/verdanab.ttf",
]


def _find_drawtext_font() -> str:
    for f in _FONT_CANDIDATES:
        if Path(f.replace("/", "\\")).exists():
            return f
    return ""


# ─── 설정 저장/불러오기 ────────────────────────────────────────
def load_config():
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(data):
    try:
        CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def cfg_audio(cfg: dict) -> dict:
    a = cfg.get("audio", {})
    return {
        "cue_intro": a.get("cue_intro", _DEFAULT_CUE_INTRO),
        "intro":     a.get("intro",     _DEFAULT_INTRO),
        "outro":     a.get("outro",     _DEFAULT_OUTRO),
        "cue_outro": a.get("cue_outro", _DEFAULT_CUE_OUTRO),
    }


def cfg_categories(cfg: dict) -> list:
    return list(cfg.get("categories", _DEFAULT_CATEGORIES))


def cfg_covers(cfg: dict) -> dict:
    result = dict(_DEFAULT_COVERS)
    result.update(cfg.get("covers", {}))
    return result


# ─── FFmpeg 탐색 ───────────────────────────────────────────────
def default_desktop():
    for p in [Path.home() / "OneDrive" / "Desktop", Path.home() / "Desktop"]:
        if p.exists():
            return p
    return Path.home()


def _try_ffmpeg(ff: str) -> bool:
    try:
        r = subprocess.run([ff, "-version"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def find_ffmpeg():
    candidates = []
    winget_base = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    if winget_base.exists():
        for pkg in winget_base.glob("Gyan.FFmpeg_*"):
            for ff in sorted(pkg.rglob("bin/ffmpeg.exe"), reverse=True):
                candidates.append((str(ff), str(ff.parent / "ffprobe.exe")))
    if shutil.which("ffmpeg"):
        candidates.append(("ffmpeg", "ffprobe"))
    local = BASE_DIR / "ffmpeg" / "bin" / "ffmpeg.exe"
    if local.exists():
        candidates.append((str(local), str(local.parent / "ffprobe.exe")))
    for ff, fp in candidates:
        if _try_ffmpeg(ff):
            return ff, fp
    return None, None


# ─── 미디어 처리 ───────────────────────────────────────────────
def get_audio_duration(ffprobe, path):
    r = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, encoding="utf-8", errors="replace",
    )
    return float(json.loads(r.stdout)["format"]["duration"])


def build_video(category, podcast_path, output_path, progress_cb, log_cb,
                task_id="", date_str="", audio=None, cover_path=None):
    ffmpeg, ffprobe = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError(
            "FFmpeg 를 찾을 수 없습니다.\n"
            "'팟캐스트 생성기 실행.bat' 를 통해 실행하면 자동으로 설치를 시도합니다."
        )

    if audio is None:
        audio = {
            "cue_intro": _DEFAULT_CUE_INTRO,
            "intro":     _DEFAULT_INTRO,
            "outro":     _DEFAULT_OUTRO,
            "cue_outro": _DEFAULT_CUE_OUTRO,
        }

    cue_intro_f = Path(audio["cue_intro"])
    intro_f     = Path(audio["intro"])
    outro_f     = Path(audio["outro"])
    cue_outro_f = Path(audio["cue_outro"])

    bg_image = Path(cover_path) if cover_path else None
    if not bg_image or not bg_image.exists():
        raise FileNotFoundError(
            f"커버 이미지를 찾을 수 없습니다:\n{bg_image}\n\n"
            f"⚙ 설정 → 카테고리 & 커버 탭에서\n"
            f"'{category}' 항목의 커버 이미지를 지정해 주세요."
        )

    for f, name in [
        (cue_intro_f,        "인트로 시그니처 사운드"),
        (intro_f,            "인트로 음성"),
        (outro_f,            "아웃트로 음성"),
        (cue_outro_f,        "아웃트로 시그니처 사운드"),
        (Path(podcast_path), "팟캐스트 파일"),
    ]:
        if not f.exists():
            raise FileNotFoundError(f"{name}를 찾을 수 없습니다:\n{f}")

    log_cb("🎵 오디오 분석 중...")
    progress_cb(10)
    cue_dur    = get_audio_duration(ffprobe, cue_intro_f)
    fade_start = max(0.0, cue_dur - 1.5)

    log_cb("🎚️  오디오 합치는 중...")
    progress_cb(25)

    uid        = task_id or uuid.uuid4().hex[:8]
    tmp_audio  = BASE_DIR / f"_tmp_combined_{uid}.aac"
    tmp_output = BASE_DIR / f"_tmp_output_{uid}.mp4"

    def run_ff(*args):
        return subprocess.run(
            list(args), capture_output=True,
            encoding="utf-8", errors="replace",
        )

    try:
        filter_graph = (
            f"[0]afade=t=out:st={fade_start:.3f}:d=1.5[cue1];"
            f"[4]afade=t=out:st={fade_start:.3f}:d=1.5[cue2];"
            f"[cue1][1:a][2:a][3:a][cue2]concat=n=5:v=0:a=1[out]"
        )
        r = run_ff(
            ffmpeg, "-y",
            "-i", str(cue_intro_f),
            "-i", str(intro_f),
            "-i", str(podcast_path),
            "-i", str(outro_f),
            "-i", str(cue_outro_f),
            "-filter_complex", filter_graph,
            "-map", "[out]",
            "-c:a", "aac", "-b:a", "192k",
            str(tmp_audio),
        )
        if r.returncode != 0:
            raise RuntimeError(f"오디오 처리 오류:\n{r.stderr[-2000:]}")

        log_cb("🎬 영상 렌더링 중...")
        progress_cb(60)

        vf = (
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
        )

        if date_str.strip():
            font_path = _find_drawtext_font()
            safe_date = format_date_english(date_str).replace("'", "").replace(":", "\\:")
            fontsize  = 150
            if font_path:
                safe_font = font_path.replace(":", "\\:")
                vf += (
                    f",drawtext=fontfile='{safe_font}'"
                    f":text='{safe_date}'"
                    ":x=60:y=100"
                    f":fontsize={fontsize}"
                    ":fontcolor=white"
                    ":shadowcolor=black@0.8:shadowx=4:shadowy=4"
                )
            else:
                vf += (
                    f",drawtext=text='{safe_date}'"
                    ":x=60:y=100"
                    f":fontsize={fontsize}"
                    ":fontcolor=white"
                    ":shadowcolor=black@0.8:shadowx=4:shadowy=4"
                )

        r = run_ff(
            ffmpeg, "-y",
            "-loop", "1",
            "-i", str(bg_image),
            "-i", str(tmp_audio),
            "-c:v", "libx264", "-tune", "stillimage",
            "-c:a", "copy",
            "-pix_fmt", "yuv420p",
            "-vf", vf,
            "-shortest",
            str(tmp_output),
        )
        if r.returncode != 0:
            raise RuntimeError(f"영상 렌더링 오류:\n{r.stderr[-2000:]}")

        shutil.move(str(tmp_output), str(output_path))
        progress_cb(100)
        log_cb(f"✅ 완료! {Path(output_path).name}")

    finally:
        tmp_audio.unlink(missing_ok=True)
        tmp_output.unlink(missing_ok=True)


# ─── 설정 창 ───────────────────────────────────────────────────
class SettingsWindow(tk.Toplevel):
    C = {
        "BG":    "#1a1a2e",
        "CARD":  "#16213e",
        "ACCENT":"#0f3460",
        "HL":    "#e94560",
        "FG":    "#eaeaea",
        "MUTED": "#8892b0",
    }
    FONT   = ("Malgun Gothic", 9)
    FONT_B = ("Malgun Gothic", 9, "bold")

    def __init__(self, parent, cfg: dict, on_save):
        super().__init__(parent)
        self.title("설정")
        self.configure(bg=self.C["BG"])
        self.resizable(False, True)
        self._cfg     = cfg
        self._on_save = on_save
        self._audio   = dict(cfg_audio(cfg))
        self._cats    = list(cfg_categories(cfg))
        self._covers  = dict(cfg_covers(cfg))
        self._cat_rows: list[dict] = []
        self._output_path = cfg.get("last_output", str(default_desktop()))
        self._build()
        self.grab_set()
        w, h = 570, 640
        x = parent.winfo_x() + (parent.winfo_width()  - w) // 2
        y = parent.winfo_y() + (parent.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self):
        C = self.C

        hdr = tk.Frame(self, bg=C["ACCENT"], pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚙  설정", font=("Malgun Gothic", 13, "bold"),
                 bg=C["ACCENT"], fg=C["FG"]).pack()

        # 저장 위치
        out_sec = tk.Frame(self, bg=C["BG"])
        out_sec.pack(fill="x", padx=12, pady=(10, 0))
        tk.Label(out_sec, text="기본 저장 위치", bg=C["BG"], fg=C["MUTED"],
                 font=self.FONT_B, anchor="w").pack(fill="x", pady=(0, 3))
        out_row = tk.Frame(out_sec, bg=C["CARD"], pady=7, padx=10)
        out_row.pack(fill="x")
        self._out_var = tk.StringVar(value=self._output_path)
        tk.Label(out_row, textvariable=self._out_var, bg=C["CARD"], fg=C["FG"],
                 font=self.FONT, anchor="w",
                 wraplength=390, justify="left").pack(side="left", fill="x", expand=True)
        tk.Button(out_row, text="📁 변경", bg=C["ACCENT"], fg=C["FG"],
                  font=self.FONT, relief="flat", padx=8, cursor="hand2",
                  command=self._pick_output).pack(side="right")

        # 커스텀 탭 바
        tab_bar = tk.Frame(self, bg=C["BG"])
        tab_bar.pack(fill="x", padx=12, pady=(12, 0))

        self._tab_contents: list[tk.Frame] = []
        self._tab_btns: list[tk.Button]    = []

        tab_wrap = tk.Frame(self, bg=C["BG"])
        tab_wrap.pack(fill="both", expand=True, padx=12, pady=(0, 4))

        def switch_tab(idx: int):
            for i, (btn, frame) in enumerate(zip(self._tab_btns, self._tab_contents)):
                if i == idx:
                    btn.config(bg=C["HL"], fg="white",
                               relief="flat", cursor="arrow")
                    frame.pack(fill="both", expand=True)
                else:
                    btn.config(bg=C["ACCENT"], fg=C["FG"],
                               relief="flat", cursor="hand2")
                    frame.pack_forget()

        tab_labels = ["  오디오  ", "  카테고리 & 커버  "]
        for i, label in enumerate(tab_labels):
            btn = tk.Button(tab_bar, text=label,
                            bg=C["ACCENT"], fg=C["FG"],
                            font=("Malgun Gothic", 10, "bold"),
                            relief="flat", padx=16, pady=8,
                            cursor="hand2",
                            command=lambda i=i: switch_tab(i))
            btn.pack(side="left", padx=(0, 2))
            self._tab_btns.append(btn)

            content = tk.Frame(tab_wrap, bg=C["BG"])
            self._tab_contents.append(content)

        self._build_audio_tab(self._tab_contents[0])
        self._build_cat_tab(self._tab_contents[1])

        switch_tab(0)

        btn_row = tk.Frame(self, bg=C["BG"])
        btn_row.pack(fill="x", padx=12, pady=(4, 12))
        tk.Button(btn_row, text="✅  저장 후 닫기",
                  bg=C["HL"], fg="white", font=self.FONT_B,
                  relief="flat", padx=16, pady=6, cursor="hand2",
                  command=self._close).pack(side="right")

    def _pick_output(self):
        folder = filedialog.askdirectory(title="기본 저장 폴더 선택")
        if folder:
            self._output_path = folder
            self._out_var.set(folder)

    # ── 오디오 탭 ──────────────────────────────────────────────
    def _build_audio_tab(self, parent):
        C = self.C
        fields = [
            ("cue_intro", "① 인트로 시그니처  (띠링 사운드)"),
            ("intro",     "② 인트로 음성  (You're listening to...)"),
            ("outro",     "③ 아웃트로 음성  (You've been listening to...)"),
            ("cue_outro", "④ 아웃트로 시그니처  (띠링 사운드)"),
        ]
        self._audio_vars: dict[str, tk.StringVar] = {}

        tk.Label(parent,
                 text="각 항목의 파일을 변경하면 즉시 기본값으로 저장됩니다.",
                 bg=C["BG"], fg=C["MUTED"], font=self.FONT).pack(
                 anchor="w", padx=14, pady=(10, 6))

        for key, label in fields:
            grp = tk.Frame(parent, bg=C["BG"])
            grp.pack(fill="x", padx=14, pady=(0, 8))

            tk.Label(grp, text=label, bg=C["BG"], fg=C["MUTED"],
                     font=self.FONT_B, anchor="w").pack(fill="x")

            row = tk.Frame(grp, bg=C["CARD"], pady=7, padx=10)
            row.pack(fill="x", pady=(3, 0))

            cur_path = self._audio.get(key, "")
            var = tk.StringVar(value=Path(cur_path).name if cur_path else "미지정")
            self._audio_vars[key] = var

            tk.Label(row, textvariable=var, bg=C["CARD"], fg=C["FG"],
                     font=self.FONT, anchor="w",
                     wraplength=370, justify="left").pack(side="left", fill="x", expand=True)
            tk.Button(row, text="📂 변경", bg=C["ACCENT"], fg=C["FG"],
                      font=self.FONT, relief="flat", padx=8, cursor="hand2",
                      command=lambda k=key: self._pick_audio(k)).pack(side="right")

            tk.Frame(parent, bg=C["ACCENT"], height=1).pack(fill="x", padx=14)

    def _pick_audio(self, key: str):
        path = filedialog.askopenfilename(
            title="오디오 파일 선택",
            filetypes=[("오디오 파일", "*.mp3 *.wav *.m4a *.aac"), ("모든 파일", "*.*")],
        )
        if path:
            self._audio[key] = path
            self._audio_vars[key].set(Path(path).name)

    # ── 카테고리 & 커버 탭 ────────────────────────────────────
    def _build_cat_tab(self, parent):
        C = self.C
        tk.Label(parent,
                 text="카테고리 이름 수정, 커버 이미지 변경, 항목 추가/삭제가 가능합니다.",
                 bg=C["BG"], fg=C["MUTED"], font=self.FONT).pack(
                 anchor="w", padx=14, pady=(10, 6))

        wrap = tk.Frame(parent, bg=C["BG"])
        wrap.pack(fill="both", expand=True, padx=14, pady=(0, 6))

        canvas = tk.Canvas(wrap, bg=C["BG"], highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._cat_frame = tk.Frame(canvas, bg=C["BG"])
        win_id = canvas.create_window((0, 0), window=self._cat_frame, anchor="nw")
        self._cat_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
            lambda e: canvas.itemconfig(win_id, width=e.width))
        canvas.bind("<Enter>",
            lambda _: canvas.bind_all("<MouseWheel>",
                lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units")))
        canvas.bind("<Leave>", lambda _: canvas.unbind_all("<MouseWheel>"))

        for cat in self._cats:
            self._add_cat_row(cat, self._covers.get(cat, ""))

        add_row = tk.Frame(parent, bg=C["BG"])
        add_row.pack(fill="x", padx=14, pady=(0, 4))
        tk.Button(add_row, text="＋ 카테고리 추가", bg=C["ACCENT"], fg=C["FG"],
                  font=self.FONT_B, relief="flat", padx=12, pady=4, cursor="hand2",
                  command=self._add_category).pack(side="left")

    def _add_cat_row(self, cat_name: str, cover_path: str):
        C = self.C
        row = tk.Frame(self._cat_frame, bg=C["CARD"], pady=6, padx=8,
                       highlightbackground=C["ACCENT"], highlightthickness=1)
        row.pack(fill="x", pady=(0, 4))

        name_var  = tk.StringVar(value=cat_name)
        cover_var = tk.StringVar(
            value=Path(cover_path).name if cover_path else "커버 미지정"
        )
        info = {
            "name_var":   name_var,
            "cover_var":  cover_var,
            "cover_path": cover_path,
            "frame":      row,
        }
        self._cat_rows.append(info)

        tk.Entry(row, textvariable=name_var, bg=C["ACCENT"], fg=C["FG"],
                 insertbackground=C["FG"], relief="flat", font=self.FONT,
                 width=18).pack(side="left", padx=(0, 8))

        tk.Label(row, textvariable=cover_var, bg=C["CARD"], fg=C["FG"],
                 font=self.FONT, anchor="w", width=24).pack(side="left", fill="x", expand=True)

        def pick_cover(d=info):
            path = filedialog.askopenfilename(
                title=f"'{d['name_var'].get()}' 커버 이미지 선택",
                filetypes=[("이미지 파일", "*.png *.jpg *.jpeg"), ("모든 파일", "*.*")],
            )
            if path:
                d["cover_path"] = path
                d["cover_var"].set(Path(path).name)

        def del_row(d=info):
            d["frame"].destroy()
            self._cat_rows[:] = [x for x in self._cat_rows if x is not d]

        tk.Button(row, text="🖼 커버", bg=C["ACCENT"], fg=C["FG"],
                  font=self.FONT, relief="flat", padx=6, cursor="hand2",
                  command=pick_cover).pack(side="right", padx=(4, 0))
        tk.Button(row, text="✕", bg=C["CARD"], fg=C["MUTED"],
                  font=self.FONT, relief="flat", padx=4, cursor="hand2",
                  command=del_row).pack(side="right")

    def _add_category(self):
        name = simpledialog.askstring("카테고리 추가", "새 카테고리 이름:", parent=self)
        if name and name.strip():
            self._add_cat_row(name.strip(), "")

    # ── 저장 ───────────────────────────────────────────────────
    def _close(self):
        self._cfg["last_output"] = self._output_path
        self._cfg["audio"] = self._audio

        new_cats:   list[str] = []
        new_covers: dict      = {}
        for d in self._cat_rows:
            name = d["name_var"].get().strip()
            if not name:
                continue
            new_cats.append(name)
            if d["cover_path"]:
                new_covers[name] = d["cover_path"]

        self._cfg["categories"] = new_cats
        self._cfg["covers"]     = new_covers
        save_config(self._cfg)
        self._on_save()
        self.destroy()


# ─── 단일 작업 카드 ────────────────────────────────────────────
class TaskCard(tk.Frame):
    COLORS = {
        "BG":    "#1a1a2e",
        "CARD":  "#16213e",
        "ACCENT":"#0f3460",
        "HL":    "#e94560",
        "FG":    "#eaeaea",
        "MUTED": "#8892b0",
    }
    FONT   = ("Malgun Gothic", 9)
    FONT_B = ("Malgun Gothic", 9, "bold")

    def __init__(self, parent, index: int, get_output_dir, on_remove,
                 get_date=None, get_audio=None, get_covers=None, get_categories=None, **kw):
        C = self.COLORS
        super().__init__(parent, bg=C["CARD"], padx=10, pady=8,
                         highlightbackground=C["ACCENT"], highlightthickness=1, **kw)
        self._index           = index
        self._get_output      = get_output_dir
        self._on_remove       = on_remove
        self._get_date        = get_date       or (lambda: "")
        self._get_audio       = get_audio      or (lambda: None)
        self._get_covers      = get_covers     or (lambda: {})
        self._get_categories  = get_categories or (lambda: list(_DEFAULT_CATEGORIES))
        self._podcast_path    = ""
        self._task_id         = uuid.uuid4().hex[:8]
        self._running         = False
        self._build()

    def _build(self):
        C = self.COLORS

        top = tk.Frame(self, bg=C["CARD"])
        top.pack(fill="x", pady=(0, 6))

        tk.Label(top, text=f"작업 {self._index}", bg=C["CARD"], fg=C["HL"],
                 font=self.FONT_B, width=6, anchor="w").pack(side="left")

        cats = self._get_categories()
        self.category_var = tk.StringVar(value=cats[0] if cats else "")
        self._cat_menu = tk.OptionMenu(top, self.category_var, *cats)
        self._cat_menu.config(
            bg=C["ACCENT"], fg=C["FG"], activebackground=C["HL"],
            activeforeground="white", highlightthickness=0,
            relief="flat", font=self.FONT, width=22, bd=0,
        )
        self._cat_menu["menu"].config(
            bg=C["CARD"], fg=C["FG"],
            activebackground=C["HL"], activeforeground="white",
            font=self.FONT, bd=0, tearoff=False,
        )
        self._cat_menu.pack(side="left", padx=(0, 6))

        self._del_btn = tk.Button(top, text="✕", bg=C["ACCENT"], fg=C["MUTED"],
                                  font=self.FONT, relief="flat", padx=6,
                                  cursor="hand2", command=self._on_remove)
        self._del_btn.pack(side="right")

        mid = tk.Frame(self, bg=C["CARD"])
        mid.pack(fill="x", pady=(0, 6))

        self.file_var = tk.StringVar(value="파일을 선택해 주세요")
        tk.Label(mid, textvariable=self.file_var, bg=C["CARD"], fg=C["FG"],
                 font=self.FONT, anchor="w", wraplength=340,
                 justify="left").pack(side="left", fill="x", expand=True)
        tk.Button(mid, text="📂", bg=C["ACCENT"], fg=C["FG"],
                  font=self.FONT_B, relief="flat", padx=8, cursor="hand2",
                  command=self._browse).pack(side="right")

        bot = tk.Frame(self, bg=C["CARD"])
        bot.pack(fill="x")

        prog_frame = tk.Frame(bot, bg=C["CARD"])
        prog_frame.pack(side="left", fill="x", expand=True, padx=(0, 8))

        style = ttk.Style()
        style.configure(f"Task{self._index}.Horizontal.TProgressbar",
                        troughcolor=C["ACCENT"], background=C["HL"], thickness=5)
        self.progress = ttk.Progressbar(prog_frame,
                                        style=f"Task{self._index}.Horizontal.TProgressbar",
                                        length=300, mode="determinate")
        self.progress.pack(fill="x")

        self.status_var = tk.StringVar(value="대기 중")
        tk.Label(prog_frame, textvariable=self.status_var, bg=C["CARD"],
                 fg=C["MUTED"], font=("Malgun Gothic", 8), anchor="w").pack(fill="x")

        self.gen_btn = tk.Button(bot, text="▶ 생성",
                                 bg=C["HL"], fg="white", font=self.FONT_B,
                                 relief="flat", padx=10, pady=4, cursor="hand2",
                                 command=self.start)
        self.gen_btn.pack(side="right")

    def _browse(self):
        path = filedialog.askopenfilename(
            title="팟캐스트 음성 파일 선택",
            filetypes=[("오디오 파일", "*.mp3 *.wav *.m4a *.aac *.ogg"), ("모든 파일", "*.*")],
        )
        if path:
            self._podcast_path = path
            self.file_var.set(Path(path).name)

    def set_index(self, idx: int):
        self._index = idx

    def is_ready(self) -> bool:
        return bool(self._podcast_path) and os.path.exists(self._podcast_path)

    def is_running(self) -> bool:
        return self._running

    def start(self):
        if self._running:
            return
        if not self.is_ready():
            messagebox.showwarning("파일 없음", f"작업 {self._index}: 팟캐스트 파일을 먼저 선택해 주세요.")
            return

        ffmpeg, _ = find_ffmpeg()
        if not ffmpeg:
            messagebox.showerror("FFmpeg 없음",
                                 "FFmpeg 가 설치되어 있지 않습니다.\n"
                                 "'팟캐스트 생성기 실행.bat' 파일을 통해 실행해 주세요.")
            return

        category   = self.category_var.get()
        covers     = self._get_covers()
        cover_path = covers.get(category, "")
        out_dir    = Path(self._get_output())
        stem       = Path(self._podcast_path).stem
        out_file   = out_dir / f"[AI Prism] {category} - {stem}.mp4"

        if out_file.exists():
            if not messagebox.askyesno("파일 덮어쓰기",
                                       f"이미 존재합니다:\n{out_file.name}\n\n덮어쓰겠습니까?"):
                return

        date_str = self._get_date()
        audio    = self._get_audio()

        self._running = True
        self.gen_btn.config(state="disabled")
        self._del_btn.config(state="disabled")
        self.progress["value"] = 0

        def run():
            try:
                build_video(
                    category, self._podcast_path, out_file,
                    progress_cb=lambda v: self.after(0, lambda: self.progress.configure(value=v)),
                    log_cb=lambda m: self.after(0, lambda msg=m: self.status_var.set(msg)),
                    task_id=self._task_id,
                    date_str=date_str,
                    audio=audio,
                    cover_path=cover_path,
                )
            except Exception as e:
                self.after(0, lambda err=str(e): messagebox.showerror(
                    f"작업 {self._index} 오류", err))
                self.after(0, lambda: self.status_var.set("❌ 오류 발생"))
                self.after(0, lambda: self.progress.configure(value=0))
            finally:
                self._running = False
                self.after(0, lambda: self.gen_btn.config(state="normal"))
                self.after(0, lambda: self._del_btn.config(state="normal"))

        threading.Thread(target=run, daemon=True).start()


# ─── 메인 앱 ───────────────────────────────────────────────────
class App(tk.Tk):
    C = {
        "BG":    "#1a1a2e",
        "CARD":  "#16213e",
        "ACCENT":"#0f3460",
        "HL":    "#e94560",
        "FG":    "#eaeaea",
        "MUTED": "#8892b0",
    }
    FONT   = ("Malgun Gothic", 10)
    FONT_B = ("Malgun Gothic", 10, "bold")

    def __init__(self):
        super().__init__()
        self.title("AI Prism 팟캐스트 생성기")
        self.resizable(False, True)
        self.configure(bg=self.C["BG"])
        self._cfg   = load_config()
        self._tasks: list[TaskCard] = []
        self._build_ui()
        self._center()
        self._add_task()

    def _center(self):
        self.update_idletasks()
        w, h = 640, 740
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _on_frame_configure(self, _event=None):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self._canvas.itemconfig(self._canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ── UI 구성 ────────────────────────────────────────────────
    def _build_ui(self):
        C = self.C

        # 헤더
        hdr = tk.Frame(self, bg=C["HL"])
        hdr.pack(fill="x")

        # 설정 버튼 (우상단)
        btn_bar = tk.Frame(hdr, bg=C["HL"])
        btn_bar.pack(fill="x", padx=10, pady=(8, 0))
        tk.Button(btn_bar, text="🎛  인트로·아웃트로 사운드, 커버, 카테고리 바꾸기", bg=C["ACCENT"], fg="white",
                  font=("Malgun Gothic", 11, "bold"), relief="flat", padx=16, pady=7,
                  cursor="hand2", command=self._open_settings).pack(side="right")

        tk.Label(hdr, text="🎙 AI Prism 팟캐스트 생성기",
                 font=("Malgun Gothic", 15, "bold"), bg=C["HL"], fg="white").pack(pady=(2, 2))
        tk.Label(hdr, text="Seoul Economic Daily",
                 font=("Malgun Gothic", 9), bg=C["HL"], fg="#ffd6d6").pack(pady=(0, 10))

        body = tk.Frame(self, bg=C["BG"], padx=20, pady=12)
        body.pack(fill="both", expand=True)

        # 저장 위치
        tk.Label(body, text="저장 위치", bg=C["BG"], fg=C["MUTED"],
                 font=("Malgun Gothic", 9, "bold"), anchor="w").pack(fill="x", pady=(0, 3))
        out_card = tk.Frame(body, bg=C["CARD"], pady=6, padx=10)
        out_card.pack(fill="x", pady=(0, 10))
        self.output_var = tk.StringVar(
            value=self._cfg.get("last_output", str(default_desktop()))
        )
        tk.Label(out_card, textvariable=self.output_var, bg=C["CARD"], fg=C["FG"],
                 font=self.FONT, anchor="w", wraplength=450,
                 justify="left").pack(side="left", fill="x", expand=True)
        tk.Button(out_card, text="📁 폴더 선택", bg=C["ACCENT"], fg=C["FG"],
                  font=self.FONT_B, relief="flat", padx=10, cursor="hand2",
                  command=self._browse_output).pack(side="right")

        # 날짜 입력
        tk.Label(body, text="날짜 (커버 상단 표시)", bg=C["BG"], fg=C["MUTED"],
                 font=("Malgun Gothic", 9, "bold"), anchor="w").pack(fill="x", pady=(0, 3))
        date_card = tk.Frame(body, bg=C["CARD"], pady=6, padx=10)
        date_card.pack(fill="x", pady=(0, 10))
        tk.Label(date_card, text="날짜 입력:", bg=C["CARD"], fg=C["MUTED"],
                 font=self.FONT).pack(side="left")
        self.date_var = tk.StringVar(value=self._cfg.get("last_date", ""))
        date_entry = tk.Entry(
            date_card, textvariable=self.date_var,
            bg=C["ACCENT"], fg=C["FG"], insertbackground=C["FG"],
            font=("Malgun Gothic", 12, "bold"),
            relief="flat", width=16,
        )
        date_entry.pack(side="left", padx=(8, 8))
        date_entry.bind("<FocusOut>", lambda _: self._save_date())
        date_entry.bind("<Return>",   lambda _: self._save_date())
        tk.Label(date_card, text="예) 2026/06/11  (년/월/일)", bg=C["CARD"], fg=C["MUTED"],
                 font=("Malgun Gothic", 9)).pack(side="left")

        # 작업 목록
        tk.Label(body, text=f"작업 목록 (최대 {MAX_TASKS}개)", bg=C["BG"], fg=C["MUTED"],
                 font=("Malgun Gothic", 9, "bold"), anchor="w").pack(fill="x", pady=(0, 4))

        scroll_wrap = tk.Frame(body, bg=C["BG"])
        scroll_wrap.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(scroll_wrap, bg=C["BG"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(scroll_wrap, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._task_frame = tk.Frame(self._canvas, bg=C["BG"])
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self._task_frame, anchor="nw")
        self._task_frame.bind("<Configure>", self._on_frame_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind("<Enter>",
            lambda _: self._canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self._canvas.bind("<Leave>",
            lambda _: self._canvas.unbind_all("<MouseWheel>"))

        # 하단 버튼
        btn_row = tk.Frame(body, bg=C["BG"])
        btn_row.pack(fill="x", pady=(10, 0))
        self._add_btn = tk.Button(btn_row, text="＋ 작업 추가",
                                  bg=C["ACCENT"], fg=C["FG"],
                                  font=self.FONT_B, relief="flat", padx=14, pady=6,
                                  cursor="hand2", command=self._add_task)
        self._add_btn.pack(side="left")
        tk.Button(btn_row, text="🎬  모두 생성",
                  bg=C["HL"], fg="white",
                  font=("Malgun Gothic", 11, "bold"),
                  relief="flat", padx=20, pady=6,
                  cursor="hand2", command=self._start_all).pack(side="right")

    # ── 공통 콜백 ──────────────────────────────────────────────
    def _browse_output(self):
        folder = filedialog.askdirectory(title="저장 폴더 선택")
        if folder:
            self.output_var.set(folder)
            self._cfg["last_output"] = folder
            save_config(self._cfg)

    def _get_output_dir(self) -> str:
        return self.output_var.get()

    def _save_date(self):
        self._cfg["last_date"] = self.date_var.get()
        save_config(self._cfg)

    def _get_date(self) -> str:
        return self.date_var.get()

    def _get_audio(self) -> dict:
        return cfg_audio(self._cfg)

    def _get_covers(self) -> dict:
        return cfg_covers(self._cfg)

    def _get_categories(self) -> list:
        return cfg_categories(self._cfg)

    # ── 설정 창 ────────────────────────────────────────────────
    def _open_settings(self):
        SettingsWindow(self, self._cfg, on_save=self._on_settings_saved)

    def _on_settings_saved(self):
        self.output_var.set(self._cfg.get("last_output", self.output_var.get()))

    # ── 작업 관리 ──────────────────────────────────────────────
    def _add_task(self):
        if len(self._tasks) >= MAX_TASKS:
            return
        idx  = len(self._tasks) + 1
        card = TaskCard(
            self._task_frame, idx,
            get_output_dir=self._get_output_dir,
            on_remove=None,
            get_date=self._get_date,
            get_audio=self._get_audio,
            get_covers=self._get_covers,
            get_categories=self._get_categories,
        )
        card._on_remove = lambda: self._remove_task(self._tasks.index(card))
        card._del_btn.config(command=card._on_remove)
        card.pack(fill="x", pady=(0, 6))
        self._tasks.append(card)
        self._refresh_add_btn()

    def _remove_task(self, idx: int):
        if idx < 0 or idx >= len(self._tasks):
            return
        card = self._tasks[idx]
        if card.is_running():
            messagebox.showwarning("진행 중", "처리 중인 작업은 삭제할 수 없습니다.")
            return
        card.destroy()
        self._tasks.pop(idx)
        for i, t in enumerate(self._tasks):
            t.set_index(i + 1)
        self._refresh_add_btn()

    def _refresh_add_btn(self):
        if len(self._tasks) >= MAX_TASKS:
            self._add_btn.config(state="disabled", fg=self.C["MUTED"])
        else:
            self._add_btn.config(state="normal", fg=self.C["FG"])

    def _start_all(self):
        ready = [t for t in self._tasks if t.is_ready() and not t.is_running()]
        if not ready:
            messagebox.showwarning("파일 없음", "생성할 파일이 선택된 작업이 없습니다.")
            return
        for task in ready:
            task.start()


if __name__ == "__main__":
    app = App()
    app.mainloop()
