import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import os
import json
import threading
import shutil
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
    """OneDrive 동기화 데스크탑 → 일반 데스크탑 순으로 반환."""
    for p in [
        Path.home() / "OneDrive" / "Desktop",
        Path.home() / "Desktop",
    ]:
        if p.exists():
            return p
    return Path.home()


def _try_ffmpeg(ff: str) -> bool:
    """ffmpeg 실행 가능 여부를 실제로 확인 (보안 정책 차단 감지)."""
    try:
        r = subprocess.run([ff, "-version"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def find_ffmpeg():
    """실행 가능한 ffmpeg 를 탐색. 없으면 (None, None)."""
    candidates = []

    # 1) winget 설치 경로 (Gyan.FFmpeg) — 보안 서명 있어 우선
    winget_base = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    if winget_base.exists():
        for pkg in winget_base.glob("Gyan.FFmpeg_*"):
            for ff in sorted(pkg.rglob("bin/ffmpeg.exe"), reverse=True):
                candidates.append((str(ff), str(ff.parent / "ffprobe.exe")))

    # 2) 시스템 PATH
    if shutil.which("ffmpeg"):
        candidates.append(("ffmpeg", "ffprobe"))

    # 3) 로컬 폴더 (보안 정책에 따라 차단될 수 있음)
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


def build_video(category, podcast_path, output_path, progress_cb, log_cb):
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

    # 보안 정책상 systemp 폴더 접근이 막힐 수 있어 프로젝트 폴더 내 임시 파일 사용
    tmp_audio  = BASE_DIR / "_tmp_combined.aac"
    tmp_output = BASE_DIR / "_tmp_output.mp4"

    # ffmpeg stderr는 UTF-8로 출력되므로 명시적으로 지정
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

        # 출력 파일명에 [] 포함 시 ffmpeg가 특수문자로 오인 → 임시 파일로 먼저 저장 후 이동
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
        log_cb(f"✅ 완료! 저장 위치: {output_path}")

    finally:
        tmp_audio.unlink(missing_ok=True)
        tmp_output.unlink(missing_ok=True)


# ─── GUI ──────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AI Prism 팟캐스트 생성기")
        self.resizable(False, False)
        self.configure(bg="#1a1a2e")
        self._cfg   = load_config()
        self._thumb = None          # PhotoImage GC 방지용
        self._build_ui()
        self._center()
        self._refresh_thumb()       # 초기 썸네일 로드

    def _center(self):
        self.update_idletasks()
        w, h = 640, 640
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ── UI 구성 ─────────────────────────────────────────────
    def _build_ui(self):
        BG     = "#1a1a2e"
        CARD   = "#16213e"
        ACCENT = "#0f3460"
        HL     = "#e94560"
        FG     = "#eaeaea"
        MUTED  = "#8892b0"
        FONT   = ("Malgun Gothic", 10)
        FONT_B = ("Malgun Gothic", 10, "bold")

        # 헤더
        hdr = tk.Frame(self, bg=HL, pady=15)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🎙 AI Prism 팟캐스트 생성기",
                 font=("Malgun Gothic", 16, "bold"), bg=HL, fg="white").pack()
        tk.Label(hdr, text="Seoul Economic Daily",
                 font=("Malgun Gothic", 9), bg=HL, fg="#ffd6d6").pack()

        body = tk.Frame(self, bg=BG, padx=28, pady=16)
        body.pack(fill="both", expand=True)

        # ① 카테고리
        self._sec(body, BG, MUTED, "① 카테고리 선택")
        cat_card = tk.Frame(body, bg=CARD, pady=8, padx=10)
        cat_card.pack(fill="x", pady=(0, 6))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Dark.TCombobox",
                        fieldbackground=CARD, background=CARD,
                        foreground=FG, selectbackground=ACCENT, selectforeground=FG)

        self.category_var = tk.StringVar(
            value=self._cfg.get("last_category", CATEGORIES[0])
        )
        cb = ttk.Combobox(
            cat_card, textvariable=self.category_var,
            values=CATEGORIES, state="readonly",
            style="Dark.TCombobox", font=FONT, width=38,
        )
        cb.pack(fill="x")
        cb.bind("<<ComboboxSelected>>", lambda _: self._refresh_thumb())

        # 카테고리 썸네일
        self._thumb_lbl = tk.Label(body, bg=BG)
        self._thumb_lbl.pack(pady=(4, 10))

        # ② 팟캐스트 파일
        self._sec(body, BG, MUTED, "② 팟캐스트 음성 파일 선택 (.mp3 / .wav / .m4a)")
        file_card = tk.Frame(body, bg=CARD, pady=8, padx=10)
        file_card.pack(fill="x", pady=(0, 12))
        self.podcast_var = tk.StringVar(value="파일을 선택해 주세요")
        tk.Label(file_card, textvariable=self.podcast_var,
                 bg=CARD, fg=FG, font=FONT,
                 anchor="w", wraplength=430, justify="left").pack(side="left", fill="x", expand=True)
        tk.Button(file_card, text="📂 찾아보기",
                  bg=ACCENT, fg=FG, font=FONT_B, relief="flat", padx=10, cursor="hand2",
                  command=self._browse_podcast).pack(side="right")

        # ③ 저장 위치
        self._sec(body, BG, MUTED, "③ 저장 위치")
        out_card = tk.Frame(body, bg=CARD, pady=8, padx=10)
        out_card.pack(fill="x", pady=(0, 16))
        self.output_var = tk.StringVar(
            value=self._cfg.get("last_output", str(default_desktop()))
        )
        tk.Label(out_card, textvariable=self.output_var,
                 bg=CARD, fg=FG, font=FONT,
                 anchor="w", wraplength=430, justify="left").pack(side="left", fill="x", expand=True)
        tk.Button(out_card, text="📁 폴더 선택",
                  bg=ACCENT, fg=FG, font=FONT_B, relief="flat", padx=10, cursor="hand2",
                  command=self._browse_output).pack(side="right")

        # 생성 버튼
        self.gen_btn = tk.Button(
            body, text="🎬  영상 생성하기",
            bg=HL, fg="white", font=("Malgun Gothic", 12, "bold"),
            relief="flat", pady=10, cursor="hand2",
            command=self._start_generate,
        )
        self.gen_btn.pack(fill="x", pady=(0, 10))

        # 진행바
        style.configure("Red.Horizontal.TProgressbar",
                        troughcolor=CARD, background=HL, thickness=6)
        self.progress = ttk.Progressbar(
            body, style="Red.Horizontal.TProgressbar",
            length=580, mode="determinate",
        )
        self.progress.pack(fill="x")

        # 상태 라벨
        self.status_var = tk.StringVar(value="준비됨")
        tk.Label(body, textvariable=self.status_var,
                 bg=BG, fg=MUTED, font=("Malgun Gothic", 9), anchor="w").pack(fill="x", pady=(5, 0))

    def _sec(self, parent, bg, fg, text):
        tk.Label(parent, text=text, bg=bg, fg=fg,
                 font=("Malgun Gothic", 9, "bold"), anchor="w").pack(fill="x", pady=(0, 3))

    # ── 카테고리 썸네일 ─────────────────────────────────────
    def _refresh_thumb(self):
        cat  = self.category_var.get()
        path = BASE_DIR / f"{cat}.png"
        photo = None
        try:
            photo = tk.PhotoImage(file=str(path))
            w, h  = photo.width(), photo.height()
            # 최대 220×124 크기에 맞게 subsample
            s = max(1, max(w // 220, h // 124))
            photo = photo.subsample(s, s)
        except Exception:
            pass

        self._thumb = photo  # GC 방지
        if photo:
            self._thumb_lbl.config(image=photo, text="")
        else:
            self._thumb_lbl.config(image="", text=f"⚠ {cat}.png 미리보기 불가",
                                   fg="#667", font=("Malgun Gothic", 8))

    # ── 파일/폴더 선택 ──────────────────────────────────────
    def _browse_podcast(self):
        path = filedialog.askopenfilename(
            title="팟캐스트 음성 파일 선택",
            filetypes=[("오디오 파일", "*.mp3 *.wav *.m4a *.aac *.ogg"), ("모든 파일", "*.*")],
        )
        if path:
            self.podcast_var.set(path)

    def _browse_output(self):
        folder = filedialog.askdirectory(title="저장 폴더 선택")
        if folder:
            self.output_var.set(folder)
            self._cfg["last_output"] = folder
            save_config(self._cfg)

    # ── 영상 생성 ───────────────────────────────────────────
    def _start_generate(self):
        podcast = self.podcast_var.get()
        if podcast == "파일을 선택해 주세요" or not os.path.exists(podcast):
            messagebox.showwarning("파일 없음", "팟캐스트 음성 파일을 먼저 선택해 주세요.")
            return

        ffmpeg, _ = find_ffmpeg()
        if not ffmpeg:
            messagebox.showerror(
                "FFmpeg 없음",
                "FFmpeg 가 설치되어 있지 않습니다.\n\n"
                "'팟캐스트 생성기 실행.bat' 파일을 통해 실행해 주세요.\n"
                "(자동으로 설치를 시도합니다)",
            )
            return

        category = self.category_var.get()
        self._cfg["last_category"] = category
        save_config(self._cfg)

        out_dir  = Path(self.output_var.get())
        stem     = Path(podcast).stem
        out_file = out_dir / f"[AI Prism] {category} - {stem}.mp4"

        # 같은 이름 파일 존재 시 확인
        if out_file.exists():
            if not messagebox.askyesno(
                "파일 덮어쓰기",
                f"이미 존재하는 파일입니다:\n{out_file.name}\n\n덮어쓰겠습니까?",
            ):
                return

        self.gen_btn.config(state="disabled")
        self.progress["value"] = 0
        self.status_var.set("⏳ 처리 시작 중...")

        def run():
            try:
                build_video(
                    category, podcast, out_file,
                    progress_cb=lambda v: self.after(0, lambda: self.progress.configure(value=v)),
                    log_cb=lambda m: self.after(0, lambda msg=m: self.status_var.set(msg)),
                )
                self.after(0, lambda: messagebox.showinfo(
                    "완료 🎉", f"영상이 생성되었습니다!\n\n📁 {out_file}"
                ))
            except Exception as e:
                self.after(0, lambda err=str(e): messagebox.showerror("오류", err))
                self.after(0, lambda: self.status_var.set("❌ 오류 발생"))
                self.after(0, lambda: self.progress.configure(value=0))
            finally:
                self.after(0, lambda: self.gen_btn.config(state="normal"))

        threading.Thread(target=run, daemon=True).start()


if __name__ == "__main__":
    app = App()
    app.mainloop()
