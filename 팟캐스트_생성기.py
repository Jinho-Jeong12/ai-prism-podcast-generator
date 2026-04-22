import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import os
import sys
import json
import threading
import tempfile
import shutil
from pathlib import Path

# ─── 경로 설정 ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent

CUE_FILE     = BASE_DIR / "확정 cue 본 Intro 2.mp3"
INTRO_FILE   = BASE_DIR / "You're listening to AI Prism, from Seoul Economic Daily..mp3"
OUTRO_FILE   = BASE_DIR / "You've been listening to AI Prism, from Seoul Economic Daily..mp3"

CATEGORIES = [
    "CEOs",
    "Early Career",
    "Finance Daily",
    "Founders",
    "Front Page Daily",
    "Global Investors",
    "Industry Daily",
    "Real Estate",
    "Retail Investors",
    "Securities Daily",
    "Stock Investors",
    "Students and Grads",
]

FFMPEG_PATH  = BASE_DIR / "ffmpeg" / "bin" / "ffmpeg.exe"
FFPROBE_PATH = BASE_DIR / "ffmpeg" / "bin" / "ffprobe.exe"


def get_ffmpeg():
    if FFMPEG_PATH.exists():
        return str(FFMPEG_PATH), str(FFPROBE_PATH)
    # fallback: system PATH
    return "ffmpeg", "ffprobe"


def get_audio_duration(ffprobe, path):
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def build_video(category, podcast_path, output_path, progress_cb, log_cb):
    ffmpeg, ffprobe = get_ffmpeg()
    bg_image = BASE_DIR / f"{category}.png"

    if not bg_image.exists():
        raise FileNotFoundError(f"배경 이미지를 찾을 수 없습니다: {bg_image}")
    if not CUE_FILE.exists():
        raise FileNotFoundError(f"시그니처 사운드 파일 없음: {CUE_FILE}")
    if not INTRO_FILE.exists():
        raise FileNotFoundError(f"인트로 파일 없음: {INTRO_FILE}")
    if not OUTRO_FILE.exists():
        raise FileNotFoundError(f"아웃트로 파일 없음: {OUTRO_FILE}")

    log_cb("🎵 오디오 길이 분석 중...")
    progress_cb(10)
    cue_dur = get_audio_duration(ffprobe, CUE_FILE)
    fade_start = max(0, cue_dur - 1.5)

    log_cb("🎚️  오디오 합치는 중 (인트로 → 팟캐스트 → 아웃트로)...")
    progress_cb(25)

    tmp_dir = Path(tempfile.mkdtemp())
    tmp_audio = tmp_dir / "combined.aac"
    tmp_video = output_path

    try:
        # filter_complex: 5개 입력 → concat
        # [0] = cue(intro용)  [1] = intro  [2] = podcast  [3] = outro  [4] = cue(outro용)
        filter_graph = (
            f"[0]afade=t=out:st={fade_start:.3f}:d=1.5[cue1];"
            f"[4]afade=t=out:st={fade_start:.3f}:d=1.5[cue2];"
            f"[cue1][1:a][2:a][3:a][cue2]concat=n=5:v=0:a=1[out]"
        )

        audio_cmd = [
            ffmpeg, "-y",
            "-i", str(CUE_FILE),
            "-i", str(INTRO_FILE),
            "-i", str(podcast_path),
            "-i", str(OUTRO_FILE),
            "-i", str(CUE_FILE),
            "-filter_complex", filter_graph,
            "-map", "[out]",
            "-c:a", "aac", "-b:a", "192k",
            str(tmp_audio)
        ]
        result = subprocess.run(audio_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"오디오 처리 오류:\n{result.stderr[-2000:]}")

        log_cb("🎬 영상 렌더링 중 (배경 + 오디오 합치는 중)...")
        progress_cb(60)

        video_cmd = [
            ffmpeg, "-y",
            "-loop", "1",
            "-i", str(bg_image),
            "-i", str(tmp_audio),
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-c:a", "copy",
            "-pix_fmt", "yuv420p",
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
            "-shortest",
            str(tmp_video)
        ]
        result = subprocess.run(video_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"영상 렌더링 오류:\n{result.stderr[-2000:]}")

        progress_cb(100)
        log_cb(f"✅ 완료! 저장 위치: {output_path}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ─── GUI ──────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AI Prism 팟캐스트 생성기")
        self.resizable(False, False)
        self.configure(bg="#1a1a2e")
        self._build_ui()
        self._center()

    def _center(self):
        self.update_idletasks()
        w, h = 600, 520
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        BG      = "#1a1a2e"
        CARD    = "#16213e"
        ACCENT  = "#0f3460"
        HL      = "#e94560"
        FG      = "#eaeaea"
        MUTED   = "#8892b0"
        FONT    = ("Malgun Gothic", 10)
        FONT_B  = ("Malgun Gothic", 10, "bold")
        FONT_H  = ("Malgun Gothic", 16, "bold")

        # 헤더
        header = tk.Frame(self, bg=HL, pady=18)
        header.pack(fill="x")
        tk.Label(header, text="🎙 AI Prism 팟캐스트 생성기",
                 font=("Malgun Gothic", 16, "bold"),
                 bg=HL, fg="white").pack()
        tk.Label(header, text="Seoul Economic Daily",
                 font=("Malgun Gothic", 9), bg=HL, fg="#ffd6d6").pack()

        body = tk.Frame(self, bg=BG, padx=30, pady=20)
        body.pack(fill="both", expand=True)

        # ── 카테고리 선택
        self._section(body, BG, MUTED, FONT, "① 카테고리 선택")
        self.category_var = tk.StringVar(value=CATEGORIES[0])
        cat_frame = tk.Frame(body, bg=CARD, bd=0, relief="flat", pady=8, padx=10)
        cat_frame.pack(fill="x", pady=(0, 14))
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Dark.TCombobox",
                         fieldbackground=CARD, background=CARD,
                         foreground=FG, selectbackground=ACCENT,
                         selectforeground=FG)
        cb = ttk.Combobox(cat_frame, textvariable=self.category_var,
                          values=CATEGORIES, state="readonly",
                          style="Dark.TCombobox", font=FONT, width=40)
        cb.pack(fill="x")

        # ── 팟캐스트 파일 선택
        self._section(body, BG, MUTED, FONT, "② 팟캐스트 음성 파일 선택 (.mp3 / .wav / .m4a)")
        file_frame = tk.Frame(body, bg=CARD, pady=8, padx=10)
        file_frame.pack(fill="x", pady=(0, 14))
        self.podcast_var = tk.StringVar(value="파일을 선택해 주세요")
        tk.Label(file_frame, textvariable=self.podcast_var,
                 bg=CARD, fg=FG, font=FONT,
                 anchor="w", wraplength=420, justify="left").pack(side="left", fill="x", expand=True)
        tk.Button(file_frame, text="📂 찾아보기",
                  bg=ACCENT, fg=FG, font=FONT_B, relief="flat",
                  padx=10, cursor="hand2",
                  command=self._browse_podcast).pack(side="right")

        # ── 저장 위치 선택
        self._section(body, BG, MUTED, FONT, "③ 저장 위치 선택")
        out_frame = tk.Frame(body, bg=CARD, pady=8, padx=10)
        out_frame.pack(fill="x", pady=(0, 18))
        self.output_var = tk.StringVar(value=str(Path.home() / "Desktop"))
        tk.Label(out_frame, textvariable=self.output_var,
                 bg=CARD, fg=FG, font=FONT,
                 anchor="w", wraplength=420, justify="left").pack(side="left", fill="x", expand=True)
        tk.Button(out_frame, text="📁 폴더 선택",
                  bg=ACCENT, fg=FG, font=FONT_B, relief="flat",
                  padx=10, cursor="hand2",
                  command=self._browse_output).pack(side="right")

        # ── 생성 버튼
        self.gen_btn = tk.Button(body, text="🎬  영상 생성하기",
                                 bg=HL, fg="white",
                                 font=("Malgun Gothic", 12, "bold"),
                                 relief="flat", pady=10,
                                 cursor="hand2",
                                 command=self._start_generate)
        self.gen_btn.pack(fill="x", pady=(0, 12))

        # ── 진행바
        pb_frame = tk.Frame(body, bg=BG)
        pb_frame.pack(fill="x")
        style.configure("Red.Horizontal.TProgressbar",
                         troughcolor=CARD, background=HL, thickness=6)
        self.progress = ttk.Progressbar(pb_frame, style="Red.Horizontal.TProgressbar",
                                        length=540, mode="determinate")
        self.progress.pack(fill="x")

        # ── 상태 로그
        self.status_var = tk.StringVar(value="준비됨")
        tk.Label(body, textvariable=self.status_var,
                 bg=BG, fg=MUTED, font=("Malgun Gothic", 9),
                 anchor="w").pack(fill="x", pady=(6, 0))

    def _section(self, parent, bg, fg, font, text):
        tk.Label(parent, text=text, bg=bg, fg=fg,
                 font=("Malgun Gothic", 9, "bold"),
                 anchor="w").pack(fill="x", pady=(0, 4))

    def _browse_podcast(self):
        path = filedialog.askopenfilename(
            title="팟캐스트 음성 파일 선택",
            filetypes=[("오디오 파일", "*.mp3 *.wav *.m4a *.aac *.ogg"), ("모든 파일", "*.*")]
        )
        if path:
            self.podcast_var.set(path)

    def _browse_output(self):
        folder = filedialog.askdirectory(title="저장 폴더 선택")
        if folder:
            self.output_var.set(folder)

    def _start_generate(self):
        podcast = self.podcast_var.get()
        if podcast == "파일을 선택해 주세요" or not os.path.exists(podcast):
            messagebox.showwarning("파일 없음", "팟캐스트 음성 파일을 먼저 선택해 주세요.")
            return

        ffmpeg, _ = get_ffmpeg()
        if not (shutil.which(ffmpeg) or Path(ffmpeg).exists()):
            messagebox.showerror(
                "FFmpeg 없음",
                "FFmpeg가 설치되어 있지 않습니다.\n\n"
                "'ffmpeg 설치하기.bat' 파일을 먼저 실행해 주세요."
            )
            return

        category  = self.category_var.get()
        out_dir   = Path(self.output_var.get())
        stem      = Path(podcast).stem
        out_file  = out_dir / f"[AI Prism] {category} - {stem}.mp4"

        self.gen_btn.config(state="disabled")
        self.progress["value"] = 0

        def run():
            try:
                build_video(
                    category, podcast, out_file,
                    progress_cb=lambda v: self.after(0, lambda: self.progress.configure(value=v)),
                    log_cb=lambda m: self.after(0, lambda msg=m: self.status_var.set(msg))
                )
                self.after(0, lambda: messagebox.showinfo(
                    "완료 🎉",
                    f"영상이 생성되었습니다!\n\n📁 {out_file}"
                ))
            except Exception as e:
                self.after(0, lambda err=str(e): messagebox.showerror("오류", err))
                self.after(0, lambda: self.status_var.set("❌ 오류 발생"))
            finally:
                self.after(0, lambda: self.gen_btn.config(state="normal"))

        threading.Thread(target=run, daemon=True).start()


if __name__ == "__main__":
    app = App()
    app.mainloop()
