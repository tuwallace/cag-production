"""Generate recording-guide.md from the narration in script.md. Cue times are ESTIMATES (133 words a minute); once the narration audio exists, replace
estimate() with the real sentence timings. Re-run after changing the narration:   python docs/video/make_recording_guide.py"""
import pathlib, re
HERE = pathlib.Path(__file__).resolve().parent
script = (HERE / "script.md").read_text().split("## Appendix A")[0]
WPM = 133

def narration(n):
    body = re.search(rf"^## {n}\. .*?\n(.*?)(?=^## |\Z)", script, re.S | re.M).group(1)
    text = " ".join(re.findall(r"^> (.*)$", body.split("**Narration:**")[1].split("**On-screen")[0].split("**Honesty")[0], re.M))
    return [s.strip() for s in re.split(r"(?<=[.?!:])\s+(?=[A-Z])", text) if s.strip()]

def cue_table(n, cues):
    sents, t, out = narration(n), 0.5, []
    rows = ["| Time | Narration says | You do (on screen) |", "|---|---|---|"]
    for i, s in enumerate(sents):
        rows.append(f"| {int(t // 60)}:{t % 60:04.1f} | {s} | {cues[i] if i < len(cues) else 'Hold.'} |")
        t += len(s.split()) / WPM * 60
    return "\n".join(rows), t

SEGS = {
 4: ("Does the cache work? (live, about 3 minutes)", "Viewer should see: a table with one slow first row (about 26,000 prompt tokens, none from the cache, minutes to read) and three fast rows (almost everything from the cache, 0.4 s to read).",
     "CAG_OLLAMA_HOST=http://127.0.0.1:11435 PYTHONPATH=src python docs/video/demo/seg4_cache.py",
     ["Terminal open at the project root, command typed but not run. Press **Enter** as the first words start.",
      "The header line and column titles print. The model is being unloaded for a few seconds (nothing moves).",
      "Wait for the first row: about 25,900 prompt tokens, 0 from cache, minutes to read. **In the edit, speed up this wait** (about 20x) or cut it and hold the last frame.",
      "The three question rows appear. Hold on the \"from cache\" column and the 0.4 s \"read prompt\" values, then on the closing percentage line.",
      "Hold. Optional overlay text: \"32B model: about 8.5 minutes (508 s)\".",
      "Hold on the whole table."]),
 6: ("The result (offline, instant)", "Viewer should see: a four-row table (8B and 32B, CAG and RAG) with the 8B CAG row at 28% and 4 of 40, and the 32B CAG row at 98%, 40 of 40, 3.0 s.",
     "python docs/video/demo/seg6_results.py",
     ["Command typed, not run. Press **Enter**; the table prints at once.",
      "Hold on the first row (qwen3 8B CAG: 28%, 4 of 40, 6.7 s).",
      "Hold on \"4 of 40\" (it refused only 4 of the 40 unanswerable questions, so it answered 36).",
      "Hold on the 8B RAG row (84%, 32 of 40).",
      "Hold on the 32B rows: CAG 98%, 40 of 40, 3.0 s, then RAG 96%, 38 of 40, 18.6 s.",
      "Hold.",
      "Hold, end of clip."]),
 7: ("Asking for quotes backfired (offline, instant)", "Viewer should see: three unanswerable questions, each with a quoted \"evidence\" sentence, the section it was pinned on, and a red \"is in that section: NO\".",
     "python docs/video/demo/seg7_quotes.py",
     ["Command typed, not run. Press **Enter**.",
      "Optional overlay: \"citations 5% → 65%\". Hold on the heading line.",
      "Scroll slowly down the first block.",
      "Hold on the mutual-TLS quote, the section it names (`cloud-00`) and \"sentence is in that section: NO\".",
      "Hold on the other two questions (pull timeout, speech-to-text). Each quoted sentence is NO.",
      "Optional: cut to a one-line animation of the fix (match the answer against the documents).",
      "Overlay: \"right section found 93-100% of the time\"."]),
 9: ("When Ollama dies (offline replay of captured data)", "Viewer should see: a REPLAY label, then the 502 in 0.08 s, the healthz 200 / readyz 503 line, and the recovery line.",
     "python docs/video/demo/seg9_outage.py",
     ["Command typed, not run. Press **Enter**. Make sure the word REPLAY in the first line is readable.",
      "Hold on the heading (\"Ollama is killed (SIGKILL) while the service is answering\").",
      "Hold on \"HTTP 502 after 0.08 s (not a hang)\".",
      "Hold on the healthz 200 / readyz 503 / ask 503 line, and on the \"1 running + 2 queued\" line.",
      "Hold on \"ready after 147 s\" and \"first answer afterwards\".",
      "Overlay: \"32B model: 8.5 minutes just to re-read\"."]),
 11: ("The regression gate (offline, about 15 seconds)", "Viewer should see: the 32B answers passing the thresholds, the 8B answers failing the same thresholds, the lock passing, then failing after one changed fact.",
     "python docs/video/demo/seg11_gate.py",
     ["Command typed, not run. Press **Enter**; the first block prints in a few seconds.",
      "Hold on the first block (`make gate-baseline`: 32B passes, the bounds column is visible).",
      "Hold on the second block (the 8B answers: two FAIL lines).",
      "Hold on the `make gate-fast` block (lock: all ok), then the line \"change ONE fact in the docs: port 11434 -> 11435\" and the second `make gate-fast`: **FAIL** on `lock:corpus_sha`.",
      "Hold on the FAIL, then end the clip.",
      "Optional cut: the GitHub Actions tab with the gitleaks workflow green (blur the repository name if you want).",
      ]),
}

out = ["# Recording guide: segments 4, 6, 7, 9 and 11", "",
       "Generated by `docs/video/make_recording_guide.py` from the narration in `script.md`. **Cue times are estimates** (133 words a minute) until the",
       "narration audio exists. Re-run the generator after changing the narration. The numbers on screen come from the scripts in `demo/` and are checked by `check_numbers.py`.", "",
       "> **Status:** the animated segments (1, 2, 3, 5, 8, 10, 12) and the narration audio are **not built yet**; see `README.md`. This guide covers only the five terminal segments.", "",
       "## 1. How the finished video fits together", "",
       "Seven animated clips (narration inside them) and five terminal clips. For each terminal clip you record the **screen only, silent**, and lay the narration audio under it in your video editor.", "",
       "| # | Segment | Type | Picture from | Length (est.) |", "|---|---|---|---|---|"]
tot = 0
plan = re.findall(r"^\| (\d+) \| (\d+:\d\d) \| (.*?) \| (ANIM|TERM) \|(.*?)\|", script, re.M)
for n, start, name, typ, demo in plan:
    n = int(n); sents = narration(n); secs = len(" ".join(sents).split()) / WPM * 60
    out.append(f"| {n} | {name} | {typ} | {'`' + demo.strip().split(' (')[0].strip('`') + '`' if typ == 'TERM' else 'animation (to be built)'} | {secs:.0f} s |")
out += ["", "## 2. One-time setup before you record anything", "", "```bash",
        "cd path/to/cag-production && source .venv/bin/activate",
        "OLLAMA_HOST=127.0.0.1:11435 OLLAMA_NUM_PARALLEL=1 OLLAMA_FLASH_ATTENTION=1 ollama serve   # a separate terminal: the dedicated Ollama for the cached model",
        "ollama list | grep qwen3:8b            # the model must be present",
        "PYTHONPATH=src python docs/video/check_numbers.py   # every number in the script must say ALL NUMBERS MATCH",
        "caffeinate -dis &                      # keeps the Mac awake while you record", "```", "",
        "1. **Notifications off** (Do Not Disturb). Close chat, mail and anything showing private content.",
        "2. **Terminal**: font size 20 pt or larger, a window of about 1280 x 720, dark background, a short prompt (`PROMPT='$ '`, then `clear`) so your user name and folders are not shown.",
        "3. **Recording**: `Cmd+Shift+5`, *Record Selected Portion*, a 16:9 area around the terminal, Microphone **None**. Save each take as `segN.mov` in a `recordings/` folder.",
        "4. Segments 6, 7, 9 and 11 use only committed data and take seconds; segment 4 needs the model and about 3 minutes.", "",
        "**Record in short takes**, one segment per file."]
for n, (title, see, cmd, cues) in SEGS.items():
    table, end = cue_table(n, cues)
    out += ["", f"## {n}. Segment {n}: {title} (about {end:.0f} s)", "", f"**{see}**", "", "Type this before pressing record (so you only press Enter on camera):", "", "```bash", cmd, "```", "", table]
out += ["", "## Honesty checks", "",
        "- **Segment 4 timings differ per run.** The cold row took 175 s in the final capture, 171 s in the one before and 147 s in an earlier outage run; the narration says \"between two and three minutes\". Read what is on screen.",
        "- **Segment 7's second mutual-TLS quote** is a near-copy of a real sentence with a few words added; the check is word-for-word, so it prints NO. Do not call it \"made up\"; the first quote is.",
        "- **Segment 9 is a replay** of a real captured run (`demo/data/chaos-8b.json`). Keep the word REPLAY on screen. To refresh it, run `scripts/chaos_test.py` against a running service (see `docs/12-security-tests.md`).",
        "- **Segment 11 runs on a throw-away copy** of the last commit plus `eval/baselines/`; it never edits your files.",
        "- **Say the caveats out loud** (segment 3 and 12 do): the 90 questions were written by an AI assistant and not reviewed by a human; one machine; one run per setting.", "",
        "## Putting it together", "",
        "1. Create a 16:9, 1080p, 30 fps project. Import the seven animated clips, your five recordings and the narration audio, once they exist.",
        "2. Place everything in the order of the table in section 1. For each terminal segment: drop the recording on the timeline, **mute its audio**, put the narration underneath and align the starts.",
        "3. Use the cue tables to line up the pictures. If a recording is shorter than the audio, hold the last frame; if it is longer (waiting for the model), speed up that part.",
        "4. Export 1080p, high quality, and watch the whole thing once with headphones before uploading.", "",
        "## Things that can go wrong", "",
        "- **Segment 4 hangs or fails to connect.** Check the dedicated Ollama is running on port 11435 (`curl 127.0.0.1:11435/api/version`). If another model is loaded it may be evicted; run `ollama ps`.",
        "- **A number differs from the narration.** Run `check_numbers.py` first. If the demo output changed, either re-record or fix the narration, then re-run both this generator and the checker.",
        "- **Privacy.** Recordings show your terminal. Hide user name and folders, and do not show `.env` or anything under `~/.config`.",
        "- **Disclosure.** The narration is synthetic if you use a synthetic voice, and the test questions were written by an AI assistant. YouTube may require its altered/synthetic content label.", ""]
(HERE / "recording-guide.md").write_text("\n".join(out)); print("wrote recording-guide.md,", len(out), "lines")
