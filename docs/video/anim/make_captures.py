"""Collect the captured demo output (../demo/captured/*.txt) into src/captures.json for the terminal replays.   python3 make_captures.py"""
import json, pathlib
HERE = pathlib.Path(__file__).resolve().parent
cap = {p.stem.split("_")[0]: p.read_text() for p in sorted((HERE.parent / "demo" / "captured").glob("seg*.txt"))}
(HERE / "src" / "captures.json").write_text(json.dumps(cap, indent=1)); print({k: len(v.splitlines()) for k, v in cap.items()}, "lines")
