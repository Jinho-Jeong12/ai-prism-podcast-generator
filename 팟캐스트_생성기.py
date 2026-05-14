import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import os
import json
import threading
import shutil
import uuid
from pathlib import Path

BASE_DIR    = Path(__file__).parent
CONFIG_FILE = BASE_DIR / ".podcast_config.json"

CUE_FILE   = BASE_DIR / "확정 cue 본 Intro 2.mp3"
INTRO_FILE = BASE_DIR / "You're listening to AI Prism, from Seoul Economic Daily..mp3"
OUTRO_FILE = BASE_DIR / "You've been listening to AI Prism, from Seoul Economic Daily..mp3"

CATEGORIES = [
    "CEO",
    "Early Career",
    "Finance Daily",
    "Founders",
    "Front Page Daily",
    "Global",
    "Industry Daily",
    "Real Estate",
    "Retail Investors",
    "Securities Daily",
    "Stock Investors",
    "Students & Grads",
]

MAX_TASKS = 6


# ─── 설정 저장/불러오기 ────────────────────────────────────
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


# ─── FFmpeg 탐색 ──────────────────────────────────────────
def default_desktop():
    for p in [
        Path.home() / "OneDrive" / "Desktop",
        Path.home() / "Desktop",
    ]:
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


# ─── 미디어 처리 ──────────────────────────────────────────
def get_audio_duration(ffprobe, path):
    r = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, encoding="utf-8", errors="replace",
    )
    return float(json.loads(r.stdout)["format"]["duration"])


def build_video(category, podcast_path, output_path, progress_cb, log_cb, task_id=""):
    ffmpeg, ffprobe = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError(
            "FFmpeg 를 찾을 수 없습니다.\n"
            "'팟캐스트 생성기 실행.bat' 를 통해 실행하면 자동으로 설치를 시도합니다."
        )

    bg_image = BASE_DIR / f"{category}.png"
    for f, name in [
        (bg_image,   "배경 이미지"),
        (CUE_FILE,   "시그니처 사운드"),
        (INTRO_FILE, "인트로"),
        (OUTRO_FILE, "아웃트로"),
        (Path(podcast_path), "팟캐스트 파일"),
    ]:
        if not Path(f).exists():
            raise FileNotFoundError(f"{name}를 찾을 수 없습니다:\n{f}")

    log_cb("🎵 오디오 분석 중...")
    progress_cb(10)
    cue_dur    = get_audio_duration(ffprobe, CUE_FILE)
    fade_start = max(0.0, cue_dur - 1.5)

    log_cb("🎚️  오디오 합치는 중...")
    progress_cb(25)

    # 동시 작업 시 임시 파일 충돌 방지를 위해 고유 ID 사용
    uid = task_id or uuid.uuid4().hex[:8]
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
            "-i", str(CUE_FILE),
            "-i", str(INTRO_FILE),
            "-i", str(podcast_path),
            "-i", str(OUTRO_FILE),
            "-i", str(CUE_FILE),
            "-filter_complex", filter_graph,
            "-map", "[out]",
            "-c:a", "aac", "-b:a", "192k",
            str(tmp_audio),
        )
        if r.returncode != 0:
            raise RuntimeError(f"오디오 처리 오류:\n{r.stderr[-2000:]}")

        log_cb("🎬 영상 렌더링 중...")
        progress_cb(60)

        r = run_ff(
            ffmpeg, "-y",
            "-loop", "1",
            "-i", str(bg_image),
            "-i", str(tmp_audio),
            "-c:v", "libx264", "-tune", "stillimage",
            "-c:a", "copy",
            "-pix_fmt", "yuv420p",
            "-vf", (
                "scale=1920:1080:force_original_aspect_ratio=decrease,"
                "pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
            ),
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


# ─── 단일 작업 카드 ───────────────────────────────────────
class TaskCard(tk.Frame):
    COLORS = {
        "BG":    "#1a1a2e",
        "CARD":  "#16213e",
        "ACCENT":"#0f3460",
        "HL":    "#e94560",
        "FG":    "#eaeaea",
        "MUTED": "#8892b0",
        "GREEN": "#4caf50",
    }
    FONT   = ("Malgun Gothic", 9)
    FONT_B = ("Malgun Gothic", 9, "bold")

    def __init__(self, parent, index: int, get_output_dir, on_remove, **kw):
        C = self.COLORS
        super().__init__(parent, bg=C["CARD"], padx=10, pady=8,
                         highlightbackground=C["ACCENT"], highlightthickness=1, **kw)
        self._index         = index
        self._get_output    = get_output_dir
        self._on_remove     = on_remove
        self._podcast_path  = ""
        self._task_id       = uuid.uuid4().hex[:8]
        self._running       = False
        self._build()

    def _build(self):
        C = self.COLORS

        # 상단 행: 번호 + 카테고리 + 삭제 버튼
        top = tk.Frame(self, bg=C["CARD"])
        top.pack(fill="x", pady=(0, 6))

        tk.Label(top, text=f"작업 {self._index}", bg=C["CARD"], fg=C["HL"],
                 font=self.FONT_B, width=6, anchor="w").pack(side="left")

        self.category_var = tk.StringVar(value=CATEGORIES[0])
        style = ttk.Style()
        style.configure("Card.TCombobox",
                        fieldbackground=C["CARD"], background=C["CARD"],
                        foreground=C["FG"], selectbackground=C["ACCENT"],
                        selectforeground=C["FG"])
        cb = ttk.Combobox(top, textvariable=self.category_var,
                          values=CATEGORIES, state="readonly",
                          style="Card.TCombobox", font=self.FONT, width=22)
        cb.pack(side="left", padx=(0, 6))

        self._del_btn = tk.Button(top, text="✕", bg=C["ACCENT"], fg=C["MUTED"],
                                  font=self.FONT, relief="flat", padx=6,
                                  cursor="hand2", command=self._on_remove)
        self._del_btn.pack(side="right")

        # 중단 행: 파일 경로 + 찾아보기
        mid = tk.Frame(self, bg=C["CARD"])
        mid.pack(fill="x", pady=(0, 6))

        self.file_var = tk.StringVar(value="파일을 선택해 주세요")
        tk.Label(mid, textvariable=self.file_var, bg=C["CARD"], fg=C["FG"],
                 font=self.FONT, anchor="w", wraplength=340,
                 justify="left").pack(side="left", fill="x", expand=True)
        tk.Button(mid, text="📂", bg=C["ACCENT"], fg=C["FG"],
                  font=self.FONT_B, relief="flat", padx=8, cursor="hand2",
                  command=self._browse).pack(side="right")

        # 하단 행: 진행바 + 생성 버튼
        bot = tk.Frame(self, bg=C["CARD"])
        bot.pack(fill="x")

        prog_frame = tk.Frame(bot, bg=C["CARD"])
        prog_frame.pack(side="left", fill="x", expand=True, padx=(0, 8))

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

        category = self.category_var.get()
        out_dir  = Path(self._get_output())
        stem     = Path(self._podcast_path).stem
        out_file = out_dir / f"[AI Prism] {category} - {stem}.mp4"

        if out_file.exists():
            if not messagebox.askyesno("파일 덮어쓰기",
                                       f"이미 존재합니다:\n{out_file.name}\n\n덮어쓰겠습니까?"):
                return

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


# ─── GUI ──────────────────────────────────────────────────
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
        self._add_task()   # 기본 1개

    def _center(self):
        self.update_idletasks()
        w, h = 640, 680
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _on_frame_configure(self, _event=None):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self._canvas.itemconfig(self._canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ── UI 구성 ─────────────────────────────────────────────
    def _build_ui(self):
        C = self.C

        # 헤더
        hdr = tk.Frame(self, bg=C["HL"], pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🎙 AI Prism 팟캐스트 생성기",
                 font=("Malgun Gothic", 15, "bold"), bg=C["HL"], fg="white").pack()
        tk.Label(hdr, text="Seoul Economic Daily",
                 font=("Malgun Gothic", 9), bg=C["HL"], fg="#ffd6d6").pack()

        body = tk.Frame(self, bg=C["BG"], padx=20, pady=12)
        body.pack(fill="both", expand=True)

        # 저장 위치 (공통)
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

        # 작업 목록 컨테이너 (스크롤 가능)
        tk.Label(body, text=f"작업 목록 (최대 {MAX_TASKS}개)", bg=C["BG"], fg=C["MUTED"],
                 font=("Malgun Gothic", 9, "bold"), anchor="w").pack(fill="x", pady=(0, 4))

        scroll_wrap = tk.Frame(body, bg=C["BG"])
        scroll_wrap.pack(fill="both", expand=True, pady=(0, 0))

        self._canvas = tk.Canvas(scroll_wrap, bg=C["BG"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(scroll_wrap, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._task_frame = tk.Frame(self._canvas, bg=C["BG"])
        self._canvas_window = self._canvas.create_window((0, 0), window=self._task_frame, anchor="nw")

        self._task_frame.bind("<Configure>", self._on_frame_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # 마우스 휠 스크롤
        self._canvas.bind("<Enter>", lambda _: self._canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self._canvas.bind("<Leave>", lambda _: self._canvas.unbind_all("<MouseWheel>"))

        # 하단 버튼 영역
        btn_row = tk.Frame(body, bg=C["BG"])
        btn_row.pack(fill="x", pady=(10, 0))

        self._add_btn = tk.Button(btn_row, text="＋ 작업 추가",
                                  bg=C["ACCENT"], fg=C["FG"],
                                  font=self.FONT_B, relief="flat", padx=14, pady=6,
                                  cursor="hand2", command=self._add_task)
        self._add_btn.pack(side="left")

        self._all_btn = tk.Button(btn_row, text="🎬  모두 생성",
                                  bg=C["HL"], fg="white",
                                  font=("Malgun Gothic", 11, "bold"),
                                  relief="flat", padx=20, pady=6,
                                  cursor="hand2", command=self._start_all)
        self._all_btn.pack(side="right")

    # ── 저장 위치 ────────────────────────────────────────────
    def _browse_output(self):
        folder = filedialog.askdirectory(title="저장 폴더 선택")
        if folder:
            self.output_var.set(folder)
            self._cfg["last_output"] = folder
            save_config(self._cfg)

    def _get_output_dir(self) -> str:
        return self.output_var.get()

    # ── 작업 관리 ────────────────────────────────────────────
    def _add_task(self):
        if len(self._tasks) >= MAX_TASKS:
            return
        idx  = len(self._tasks) + 1
        card = TaskCard(self._task_frame, idx,
                        get_output_dir=self._get_output_dir,
                        on_remove=lambda c=None: self._remove_task(len(self._tasks) - 1))
        # on_remove를 카드 생성 후 올바른 인덱스로 바인딩
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
        # 번호 재정렬
        for i, t in enumerate(self._tasks):
            t.set_index(i + 1)
        self._refresh_add_btn()

    def _refresh_add_btn(self):
        if len(self._tasks) >= MAX_TASKS:
            self._add_btn.config(state="disabled", fg=self.C["MUTED"])
        else:
            self._add_btn.config(state="normal", fg=self.C["FG"])

    # ── 모두 생성 ────────────────────────────────────────────
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
