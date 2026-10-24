#!/usr/bin/env python3
"""(Adapted from the helpdesk-rag video pipeline.) Turn the narration blocks in ../script.md into audio plus sentence-level timings.

For each "## N. Title" segment we take the text after "**Narration:**" (the "> " lines), split it into sentences,
speak each sentence separately with macOS `say`, and join them with short pauses. Because every sentence is its own
audio clip we know exactly when each one starts; the animation looks beats up by phrase (see anim/src/ui.tsx `beat`).

Output (read by the Remotion project):
  ../anim/public/narration/seg<N>.wav     one audio file per segment
  ../anim/src/narration.json              {"seg<N>": {"audio", "duration", "sentences": [{"text","start","end"}]}}

Usage:  python3 build_narration.py                                   # macOS voice (Daniel)
        .venv/bin/python build_narration.py --engine kokoro --voice af_heart   # Kokoro neural voice (needs ./.venv)
Audition voices with:  say -v '?' | grep en_   then   say -v Daniel "test sentence"
Stock macOS voices only. This does not clone anyone's voice.
"""
import argparse, json, os, pathlib, re, subprocess, tempfile, wave

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE.parent / "script.md"
OUT_AUDIO = HERE.parent / "anim" / "public" / "narration"
OUT_JSON = HERE.parent / "anim" / "src" / "narration.json"

# Spoken forms for words a TTS voice would mispronounce. Applied to the spoken text only, never to the timings text.
PRONOUNCE = [
    (r"\bCAG\b", "C A G"), (r"\bRAG\b", "rag"), (r"\bKV\b", "K V"), (r"\bOllama's\b", "Oh-lama's"), (r"\bOllama\b", "Oh-lama"),
    (r"\bQwen\b", "Kwen"), (r"\bTLS\b", "T L S"), (r"\bAI\b", "A I"), (r"\bMacBook\b", "Mac book"),
]
LEAD_IN, GAP, GAP_Q, TAIL = 0.5, 0.35, 0.55, 0.4   # seconds of silence


def parse_segments(md: str):
    segs, cur_n, grab = {}, None, False
    for line in md.splitlines():
        m = re.match(r"## (\d+)\. ", line)
        if m:
            cur_n, grab = int(m.group(1)), False
            continue
        if cur_n is None:
            continue
        if line.startswith("**Narration:**"):
            grab = True; segs[cur_n] = []
        elif grab and line.startswith(">"):
            segs[cur_n].append(line[1:].strip())
        elif grab and not line.startswith(">"):
            grab = False
    return {n: " ".join(v) for n, v in segs.items() if v}


def split_sentences(text: str):
    return [s.strip() for s in re.split(r'(?<=[.?!])\s+(?=[A-Z"“])', text) if s.strip()]


_KOKORO = {}

def speak(text, voice, rate, path, engine="say", speed=1.0):
    """Write `text` as a mono 16-bit WAV. engine "say" = macOS voices (22.05 kHz); "kokoro" = Kokoro-82M neural TTS (24 kHz)."""
    for pat, rep in PRONOUNCE:
        text = re.sub(pat, rep, text)
    if engine == "say":
        subprocess.run(["say", "-v", voice, "-r", str(rate), "--file-format=WAVE", "--data-format=LEI16@22050", "-o", str(path), text], check=True)
        return
    import numpy as np, soundfile as sf
    from kokoro import KPipeline
    lang = voice[0]                                  # kokoro voice ids start with the language code: a=American, b=British
    pipe = _KOKORO.setdefault(lang, KPipeline(lang_code=lang))
    chunks = [np.asarray(audio, dtype="float32") for _, _, audio in pipe(text, voice=voice, speed=speed)]
    sf.write(str(path), np.concatenate(chunks), 24000, subtype="PCM_16")


ENGINE_RATE = {"say": 22050, "kokoro": 24000}


def normalize(path: pathlib.Path, lufs: float):
    """Loudness-normalize in place with ffmpeg's loudnorm (EBU R128), keeping 22.05 kHz mono 16-bit and the same length.
    True peak is capped at -1.5 dB so the later AAC encode doesn't clip."""
    tmp = path.with_suffix(".norm.wav")
    with wave.open(str(path)) as w: sr = w.getframerate()          # loudnorm would otherwise output 192 kHz
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-af", f"loudnorm=I={lufs}:TP=-1.5:LRA=11",
                    "-ar", str(sr), "-ac", "1", "-c:a", "pcm_s16le", str(tmp)], check=True)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--engine", choices=["say", "kokoro"], default="say"); ap.add_argument("--voice", default=None)
    ap.add_argument("--rate", type=int, default=175, help="say only (words per minute)"); ap.add_argument("--speed", type=float, default=1.0, help="kokoro only")
    ap.add_argument("--lufs", type=float, default=-16.0, help="target integrated loudness")
    ap.add_argument("--only", help="comma-separated segment numbers to regenerate (e.g. 3,8); other segments and their timings are kept")
    ap.add_argument("--loudness-only", action="store_true", help="only re-normalize the existing wav files; no new speech, timings untouched")
    a = ap.parse_args()
    a.voice = a.voice or ({"say": "Daniel", "kokoro": "af_heart"}[a.engine])
    OUT_AUDIO.mkdir(parents=True, exist_ok=True)
    if a.loudness_only:
        for f in sorted(OUT_AUDIO.glob("seg*.wav")): normalize(f, a.lufs); print("normalized", f.name)
        return
    segs = parse_segments(SCRIPT.read_text())
    result = json.loads(OUT_JSON.read_text()) if (a.only and OUT_JSON.exists()) else {}
    if a.only: segs = {n: v for n, v in segs.items() if str(n) in a.only.split(",")}
    for n, text in sorted(segs.items()):
        sentences = split_sentences(text)
        frames, rate_hz, width, t, timings = [], ENGINE_RATE[a.engine], 2, 0.0, []
        silence = lambda sec: b"\x00" * (int(sec * rate_hz) * width)
        frames.append(silence(LEAD_IN)); t += LEAD_IN
        with tempfile.TemporaryDirectory() as tmp:
            for i, sent in enumerate(sentences):
                p = pathlib.Path(tmp) / f"{i}.wav"; speak(sent, a.voice, a.rate, p, a.engine, a.speed)
                with wave.open(str(p)) as w:
                    data, dur = w.readframes(w.getnframes()), w.getnframes() / w.getframerate()
                    rate_hz, width = w.getframerate(), w.getsampwidth()
                frames.append(data); timings.append({"text": sent, "start": round(t, 3), "end": round(t + dur, 3)}); t += dur
                gap = GAP_Q if sent.endswith("?") else GAP
                frames.append(silence(gap)); t += gap
        frames.append(silence(TAIL)); t += TAIL
        out = OUT_AUDIO / f"seg{n}.wav"
        with wave.open(str(out), "wb") as w:
            w.setnchannels(1); w.setsampwidth(width); w.setframerate(rate_hz); w.writeframes(b"".join(frames))
        normalize(out, a.lufs)
        result[f"seg{n}"] = {"audio": f"narration/seg{n}.wav", "duration": round(t, 3), "sentences": timings}
        print(f"seg{n}: {len(sentences):2d} sentences  {t:6.1f}s  {len(text.split()):4d} words")
    OUT_JSON.write_text(json.dumps(dict(sorted(result.items(), key=lambda kv: int(kv[0][3:]))), indent=1))
    print(f"engine={a.engine} voice={a.voice}  total {sum(v['duration'] for v in result.values()) / 60:.1f} min (all segments in json) -> {OUT_JSON}")


if __name__ == "__main__":
    main()
