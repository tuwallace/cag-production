#!/usr/bin/env python3
"""(Adapted from the helpdesk-rag video pipeline.) Builds the draft upload folder: docs/video/upload/{cag-video-draft.mp4, captions.srt, thumbnail.png, description.txt, tags.txt, README.txt}.
Joins the 12 rendered clips (anim/out/*.mp4) in script order, trims the idle tail of each clip, fades in/out, and writes captions and chapters
from the real clip durations and the narration timings.   Run:  python3 docs/video/finalize.py"""
import json, pathlib, shutil, subprocess, textwrap

HERE = pathlib.Path(__file__).resolve().parent
OUT, UP = HERE / "anim/out", HERE / "upload"
N = json.loads((HERE / "anim/src/narration.json").read_text())
ORDER = [("Hook", "seg1", "Hook"), ("WhatIsCag", "seg2", "What CAG is"), ("TheTest", "seg3", "The test"), ("Seg4", "seg4", "Does the cache work?"),
         ("Evicted", "seg5", "Surprise 1: the cache got evicted"), ("Seg6", "seg6", "The result"), ("Seg7", "seg7", "Surprise 2: asking for quotes backfired"),
         ("BenchFlip", "seg8", "Surprise 3: my own benchmark fooled me"), ("Seg9", "seg9", "When Ollama dies"), ("Attacks", "seg10", "Attacks and load"),
         ("Seg11", "seg11", "The regression gate"), ("Takeaways", "seg12", "Takeaways")]
TRIM = 2.4          # the 2 s hold Remotion adds + the 0.4 s of silence the narration builder appends; removed from every clip except the last
HEAD = 0.25         # of the 0.5 s lead-in silence at the start of each narration, removed from every clip except the first
FADE_IN, FADE_OUT = 0.6, 0.9

def run(cmd): return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
def probe(f, entry): return run(["ffprobe", "-v", "error", "-show_entries", entry, "-of", "csv=p=0", str(f)]).strip()
ts = lambda t, sep=",": f"{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{int(t % 60):02d}{sep}{int(round((t % 1) * 1000)):03d}"

UP.mkdir(exist_ok=True)
clips = []
for cid, seg, title in ORDER:
    f = OUT / f"{cid}.mp4"
    assert f.exists(), f"missing {f}: render it first (see README.md)"
    d = float(probe(f, "format=duration")); clips.append(dict(cid=cid, seg=seg, title=title, file=f, dur=d))
for i, c in enumerate(clips):
    c["head"] = HEAD if i > 0 else 0.0
    c["keep"] = c["dur"] - c["head"] - (TRIM if i < len(clips) - 1 else 0)
    c["offset"] = sum(x["keep"] for x in clips[:i])
total = sum(c["keep"] for c in clips)

# ---- video: trim tails, normalise format, concatenate, fade in/out ----
parts, ins = [], []
for i, c in enumerate(clips):
    ins += ["-i", str(c["file"])]
    parts.append(f"[{i}:v]trim=start={c['head']:.3f}:duration={c['keep']:.3f},setpts=PTS-STARTPTS,fps=30,format=yuv420p[v{i}];"
                 f"[{i}:a]atrim=start={c['head']:.3f}:duration={c['keep']:.3f},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo[a{i}]")
cat = "".join(f"[v{i}][a{i}]" for i in range(len(clips))) + f"concat=n={len(clips)}:v=1:a=1[v][a]"
fade = (f"[v]fade=t=in:st=0:d={FADE_IN},fade=t=out:st={total - FADE_OUT:.3f}:d={FADE_OUT}[vf];"
        f"[a]afade=t=in:st=0:d={FADE_IN},afade=t=out:st={total - FADE_OUT:.3f}:d={FADE_OUT}[af]")
final = UP / "cag-video-draft.mp4"
run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(parts) + ";" + cat + ";" + fade, "-map", "[vf]", "-map", "[af]",
     "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
     "-movflags", "+faststart", str(final)])

# ---- captions (SRT) from the narration sentences ----
cues = []
for c in clips:
    for s in N[c["seg"]]["sentences"]:
        a, b = c["offset"] + s["start"] - c["head"], c["offset"] + s["end"] - c["head"]
        if s["start"] - c["head"] > c["keep"]: continue
        words = s["text"].split(); chunks, cur = [], ""
        for w in words:                                   # split long sentences into cues of <= 76 characters (two caption lines)
            if len(cur) + len(w) + 1 > 76 and cur: chunks.append(cur); cur = w
            else: cur = (cur + " " + w).strip()
        chunks.append(cur); L = sum(len(x) for x in chunks); t = a
        for x in chunks:
            seg_len = (b - a) * len(x) / L; cues.append((t, t + seg_len, x)); t += seg_len
srt = [f"{i}\n{ts(a)} --> {ts(b)}\n" + "\n".join(textwrap.wrap(x, 44)) + "\n" for i, (a, b, x) in enumerate(cues, 1)]
(UP / "captions.srt").write_text("\n".join(srt))

# ---- chapters + description ----
chapters = "\n".join(f"{int(c['offset'] // 60)}:{int(c['offset'] % 60):02d} {c['title']}" for c in clips)
(UP / "description.txt").write_text(f"""Cache-augmented generation (CAG) loads a whole knowledge base into the model once and reuses the model's memory of it, instead of searching for every question.
I tested it against RAG on a MacBook with local models (Ollama; Qwen 3 8B and Qwen 2.5 32B): what the cache costs, what surprised me, how it failed, and how I checked it.

{chapters}

CAVEATS
One machine, one run per setting, 90 test questions about a 26k-token slice of Ollama's documentation. The questions were written by an AI coding assistant and were
not reviewed by a human. Treat the numbers as a comparison of setups on the same questions, not as a benchmark.

ABOUT THIS VIDEO
- The narration is a synthetic (AI-generated) voice, made with Kokoro-82M.
- The terminal segments are replays of real captured output, not live screen recordings, and say so on screen. The outage segment replays data from a real run.
- Animations were built with Remotion.

CREDITS
Knowledge base: Ollama's documentation (MIT licence), github.com/ollama/ollama. Models: Qwen (Alibaba Cloud), run with Ollama; check their licences before reuse.
Tools: Ollama, FastAPI, rank-bm25, Remotion, Kokoro.

CODE AND NOTES
Repository: <link when the repository is public>
""")
(UP / "tags.txt").write_text("CAG, cache-augmented generation, RAG, Ollama, local LLM, Qwen, KV cache, prompt caching, AI engineering, evaluation\n")
shutil.copy(OUT / "thumbnail.png", UP / "thumbnail.png")
(UP / "README.txt").write_text("""DRAFT: nothing here has been uploaded; that is up to you.
1. Watch cag-video-draft.mp4 fully, with headphones, before anything else. Listen for mispronounced names (Ollama, Qwen, KV, TLS, CAG). If any are wrong:
   edit PRONOUNCE in narration/build_narration.py, re-run it, re-render the clips (anim/), then re-run this script.
2. description.txt has a placeholder for the repository link; the repository is private today, so fill it in only if you make it public.
3. Upload as PRIVATE or UNLISTED first. Thumbnail: thumbnail.png (1280x720). Captions: captions.srt (English). Tags: tags.txt.
4. Under "Altered content" answer YES: the narration is a synthetic voice.
5. Check the licences you rely on: Remotion (terms depend on company size), Kokoro, the Qwen models, and Ollama's documentation (MIT).
6. If you replace a terminal replay with a real screen recording, follow ../recording-guide.md and swap that clip in anim/out before re-running this script.
""")
print(f"wrote {final} ({total / 60:.2f} min), {len(cues)} caption cues, {len(clips)} chapters")
