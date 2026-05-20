import subprocess, os, re, whisper, yt_dlp

OUTPUTS = "outputs"
os.makedirs(OUTPUTS, exist_ok=True)

# Install ffmpeg at runtime if not found
try:
    subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
except (subprocess.CalledProcessError, FileNotFoundError):
    os.system("apt-get install -y ffmpeg")

HYPE_WORDS = [
    "insane", "crazy", "bro", "no way", "what", "holy", "clip it",
    "let's go", "omg", "oh my god", "wait", "actually", "literally",
    "impossible", "unbelievable", "pog", "watch this", "are you serious",
    "you're kidding", "shut up", "no no no", "yes yes yes", "come on",
    "scream", "yell", "laugh", "chat", "poggers"
]


# ── Download ──────────────────────────────────────────────────────────────────

def download_audio(url, job_id):
    out = os.path.join(OUTPUTS, f"{job_id}_audio.%(ext)s")
    with yt_dlp.YoutubeDL({
        "format": "bestaudio/best",
        "outtmpl": out,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "128"}],
        "quiet": True,
    }) as ydl:
        ydl.download([url])
    return os.path.join(OUTPUTS, f"{job_id}_audio.mp3")


def download_video(url, job_id):
    out = os.path.join(OUTPUTS, f"{job_id}_video.%(ext)s")
    with yt_dlp.YoutubeDL({
        "format": "best[height<=720]",
        "outtmpl": out,
        "quiet": True,
    }) as ydl:
        info = ydl.extract_info(url, download=True)
        ext = info.get("ext", "mp4")
    return os.path.join(OUTPUTS, f"{job_id}_video.{ext}")


# ── Transcribe ────────────────────────────────────────────────────────────────

def transcribe(audio_path):
    model = whisper.load_model("base")
    result = model.transcribe(audio_path, word_timestamps=True)
    segments = []
    for s in result["segments"]:
        segments.append({
            "start": s["start"],
            "end": s["end"],
            "text": s["text"].strip(),
            "words": [
                {"word": w["word"], "start": w["start"], "end": w["end"]}
                for w in s.get("words", [])
            ]
        })
    return segments


# ── Analyze ───────────────────────────────────────────────────────────────────

def score_text(text):
    score = 1
    tl = text.lower()
    for w in HYPE_WORDS:
        if w in tl:
            score += 1
    score += min(len(re.findall(r'\b[A-Z]{2,}\b', text)), 3)
    score += min(text.count("!"), 2)
    score += min(text.count("?"), 1)
    return min(score, 10)


def find_highlights(segments, min_score=4):
    highlights = []
    window = 45
    i = 0
    while i < len(segments):
        win_start = segments[i]["start"]
        win_end = win_start + window
        text = ""
        j = i
        while j < len(segments) and segments[j]["start"] < win_end:
            text += " " + segments[j]["text"]
            j += 1
        score = score_text(text)
        if score >= min_score:
            highlights.append({
                "start": win_start,
                "end": min(win_end, segments[j-1]["end"] if j > i else win_end),
                "text": text.strip(),
                "score": score
            })
        i = max(i + 1, j - max(1, (j - i) // 2))
    highlights.sort(key=lambda x: x["score"], reverse=True)
    return highlights[:5]


# ── Subtitles ─────────────────────────────────────────────────────────────────

def make_ass(segments, ass_path):
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, Strikeout, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,88,&H00FFFFFF,&H000000FF,&H00000000,&HCC000000,-1,0,0,0,100,100,2,0,1,5,3,2,60,60,200,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def fmt(sec):
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = sec % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    def chunk_words(words):
        chunks, i = [], 0
        while i < len(words):
            avg = sum(len(words[j]["word"]) for j in range(i, min(i+4, len(words)))) / 4
            size = 2 if avg > 7 else (4 if avg < 4 else 3)
            chunks.append(words[i:i+size])
            i += size
        return chunks

    lines = [header]
    for seg in segments:
        words = seg.get("words", [])
        if not words:
            continue
        for chunk in chunk_words(words):
            if not chunk:
                continue
            start = fmt(chunk[0]["start"])
            end = fmt(chunk[-1]["end"])
            mid = len(chunk) // 2
            parts = []
            for j, w in enumerate(chunk):
                word = w["word"].strip().upper()
                if j == mid and len(chunk) > 2:
                    parts.append(f"{{\\c&H00FFFF&}}{word}{{\\c&HFFFFFF&}}")
                else:
                    parts.append(word)
            lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{' '.join(parts)}\n")

    with open(ass_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


# ── Hook card ─────────────────────────────────────────────────────────────────

def generate_hook(text):
    sentences = [s.strip() for s in text.replace("!", ".").replace("?", ".").split(".") if len(s.strip()) > 10]
    if not sentences:
        return "YOU WON'T BELIEVE THIS"
    best = sorted(sentences, key=len)[0]
    return (best[:57] + "...").upper() if len(best) > 60 else best.upper()


def make_hook_card(hook_text, out_path):
    safe = hook_text.replace("'", "\\'").replace(":", "\\:").replace(",", "\\,")
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "color=c=black:size=1080x1920:duration=1.5:rate=30",
        "-vf", (
            f"drawtext=text='{safe}':"
            f"fontsize=80:fontcolor=white:"
            f"borderw=4:bordercolor=black:"
            f"x=(w-text_w)/2:y=(h-text_h)/2:"
            f"line_spacing=12"
        ),
        "-c:v", "libx264", "-preset", "fast", out_path
    ], capture_output=True, check=True)


# ── Clip ──────────────────────────────────────────────────────────────────────

def process_clip(video_path, highlight, all_segments, job_id, index):
    raw    = os.path.join(OUTPUTS, f"{job_id}_{index}_raw.mp4")
    ass    = os.path.join(OUTPUTS, f"{job_id}_{index}.ass")
    subbed = os.path.join(OUTPUTS, f"{job_id}_{index}_subbed.mp4")
    hook   = os.path.join(OUTPUTS, f"{job_id}_{index}_hook.mp4")
    concat = os.path.join(OUTPUTS, f"{job_id}_{index}_concat.txt")
    final  = os.path.join(OUTPUTS, f"{job_id}_clip{index}.mp4")

    # Cut + vertical crop from left edge (keeps gameplay)
    subprocess.run([
        "ffmpeg", "-y",
        "-ss", str(highlight["start"]),
        "-i", video_path,
        "-t", str(highlight["end"] - highlight["start"]),
        "-vf", "scale=-2:1920,crop=1080:1920:0:0",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k",
        raw
    ], capture_output=True, check=True)

    # Shift segment timestamps to be relative to clip start
    clip_segs = []
    for s in all_segments:
        if s["end"] <= highlight["start"] or s["start"] >= highlight["end"]:
            continue
        offset = highlight["start"]
        clip_segs.append({
            "start": max(0, s["start"] - offset),
            "end": s["end"] - offset,
            "text": s["text"],
            "words": [
                {
                    "word": w["word"],
                    "start": max(0, w["start"] - offset),
                    "end": w["end"] - offset
                }
                for w in s.get("words", [])
            ]
        })

    make_ass(clip_segs, ass)

    subprocess.run([
        "ffmpeg", "-y", "-i", raw,
        "-vf", f"ass={ass}",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-c:a", "copy", subbed
    ], capture_output=True, check=True)

    hook_text = generate_hook(highlight["text"])
    make_hook_card(hook_text, hook)

    with open(concat, "w") as f:
        f.write(f"file '{os.path.abspath(hook)}'\n")
        f.write(f"file '{os.path.abspath(subbed)}'\n")

    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", concat,
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-c:a", "aac", final
    ], capture_output=True, check=True)

    for f in [raw, subbed, hook, concat, ass]:
        if os.path.exists(f):
            os.remove(f)

    return final, hook_text


# ── Full pipeline ─────────────────────────────────────────────────────────────

def run(job_id, url, job_store):
    try:
        job_store[job_id]["status"] = "Downloading audio..."
        audio = download_audio(url, job_id)

        job_store[job_id]["status"] = "Downloading video..."
        video = download_video(url, job_id)

        job_store[job_id]["status"] = "Transcribing with Whisper..."
        segments = transcribe(audio)

        job_store[job_id]["status"] = "Finding highlights..."
        highlights = find_highlights(segments)

        if not highlights:
            job_store[job_id]["status"] = "done"
            job_store[job_id]["clips"] = []
            job_store[job_id]["message"] = "No highlights found. Try a more energetic video."
            return

        clips = []
        for i, h in enumerate(highlights):
            job_store[job_id]["status"] = f"Creating clip {i+1} of {len(highlights)}..."
            path, hook = process_clip(video, h, segments, job_id, i+1)
            clips.append({
                "filename": os.path.basename(path),
                "score": h["score"],
                "hook": hook,
                "duration": round(h["end"] - h["start"], 1),
                "preview": h["text"][:100] + "..." if len(h["text"]) > 100 else h["text"]
            })

        for f in [audio, video]:
            if os.path.exists(f):
                os.remove(f)

        job_store[job_id]["status"] = "done"
        job_store[job_id]["clips"] = clips

    except Exception as e:
        job_store[job_id]["status"] = "error"
        job_store[job_id]["error"] = str(e)
