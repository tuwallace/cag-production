import React from "react";
import { AbsoluteFill } from "remotion";
import { C, FONT, Appear, Narration, beat, useProgress } from "./ui";
import { Ev, Replay, ReplayLabel, Window } from "./Terminal";
import cap from "./captures.json";

// Terminal segments: REPLAYS of the real output captured from docs/video/demo/*.py (docs/video/demo/captured/*.txt), timed to the narration with beat().
type Banner = { at: number; text: string; color?: string; pos?: "top" | "bottom" };
const BannerView: React.FC<{ b: Banner; next?: number }> = ({ b, next }) => {
  const out = useProgress(next ?? 1e6, 0.4);               // the next banner replaces this one, so two never overlap
  const c = b.color ?? C.teal, edge = b.pos === "top" ? { top: 118 } : { bottom: 66 };
  return (
    <div style={{ opacity: 1 - out }}>
      <Appear at={b.at} style={{ position: "absolute", left: 130, right: 130, ...edge, background: "rgba(14,19,32,.94)", border: `3px solid ${c}`, borderRadius: 16, padding: "14px 26px", fontFamily: FONT, fontSize: 38, fontWeight: 700, color: c, textAlign: "center" }}>{b.text}</Appear>
    </div>
  );
};
const Scene: React.FC<{ seg: string; events: Ev[]; label: string; banners?: Banner[] }> = ({ seg, events, label, banners = [] }) => (
  <AbsoluteFill style={{ background: C.bg }}>
    <Narration seg={seg} />
    <Window><Replay events={events} /></Window>
    {banners.map((b, i) => <BannerView key={b.text} b={b} next={banners[i + 1]?.at} />)}
    <ReplayLabel text={label} />
  </AbsoluteFill>
);
const GRAY = "#8b95a8";

export const Seg4: React.FC = () => {
  const S = "seg4", L = cap.seg4.split("\n"), iCold = L.findIndex((l) => l.includes("first call"));
  const header = L.slice(0, iCold).join("\n"), cold = L[iCold], qs = L.filter((l) => /^\s+question \d/.test(l)).join("\n"), fin = L.find((l) => l.includes("after the first call"))!;
  const tCold = beat(S, "which took me between"), tQ = beat(S, "After that, reading"), tFin = beat(S, "because more than");
  const ev: Ev[] = [
    { kind: "type", at: 0.2, text: "python docs/video/demo/seg4_cache.py", cps: 40 },
    { kind: "print", at: beat(S, "Here is the eight-billion"), text: header },
    { kind: "print", at: beat(S, "The first call has to read"), text: "(the real first call took 175 s; the wait is trimmed here)", color: GRAY },
    { kind: "print", at: tCold, text: cold }, { kind: "hl", at: tCold, until: tQ, match: ["first call"] },
    { kind: "print", at: tQ, text: qs, reveal: 1.4 }, { kind: "hl", at: tQ, until: tFin, match: ["question "] },
    { kind: "print", at: tFin, text: fin }, { kind: "hl", at: tFin, until: tFin + 30, match: ["after the first call"] },
  ];
  return <Scene seg={S} events={ev} label="Terminal replay of a real captured run (qwen3:8b; the long first wait is trimmed)"
    banners={[{ at: beat(S, "With the thirty-two-billion"), text: "32B model: first call about 8.5 minutes (508 s, measured)", color: C.amber }]} />;
};

export const Seg6: React.FC = () => {
  const S = "seg6", go = beat(S, "Now the result");
  const ev: Ev[] = [
    { kind: "type", at: 0.2, text: "python docs/video/demo/seg6_results.py", cps: 40 },
    { kind: "print", at: go, text: cap.seg6 },
    { kind: "hl", at: beat(S, "The eight-billion model with CAG"), until: beat(S, "RAG with the same small model"), match: ["qwen3 8B    CAG"] },
    { kind: "hl", at: beat(S, "It answered thirty-six"), until: beat(S, "RAG with the same small model"), match: ["4 of 40"] },
    { kind: "hl", at: beat(S, "RAG with the same small model"), until: beat(S, "The thirty-two-billion model with CAG"), match: ["qwen3 8B    RAG"] },
    { kind: "hl", at: beat(S, "The thirty-two-billion model with CAG"), until: beat(S, "where RAG on the same model"), match: ["qwen2.5 32B CAG"] },
    { kind: "hl", at: beat(S, "where RAG on the same model"), until: beat(S, "Same trick"), match: ["qwen2.5 32B RAG"] },
  ];
  return <Scene seg={S} events={ev} label="Terminal replay of real output (committed answers in eval/baselines/; not a live screen recording)" />;
};

export const Seg7: React.FC = () => {
  const S = "seg7", go = beat(S, "I tried to make") + 1.4;
  const ev: Ev[] = [
    { kind: "type", at: 0.2, text: "python docs/video/demo/seg7_quotes.py", cps: 40 },
    { kind: "print", at: go, text: cap.seg7, reveal: 1.8 },
    { kind: "hl", at: beat(S, "Asked about mutual TLS"), until: beat(S, "So I stopped asking"), match: ["mutual TLS", "cloud-00", "Ollama does not support"] },
    { kind: "hl", at: beat(S, "So I stopped asking"), until: beat(S, "After it answers"), match: ["sentence is in that section: NO"] },
  ];
  return <Scene seg={S} events={ev} label="Terminal replay of real output (8B model answers committed in eval/baselines/)"
    banners={[{ at: beat(S, "Citations went from"), text: "citations 5% → 65%, but refusals 82% → 27% (small model, first 40 questions)", color: C.amber },
              { at: beat(S, "That found the right section"), text: "matching the answer to the docs found the right section 93–100% of the time" }]} />;
};

export const Seg9: React.FC = () => {
  const S = "seg9", go = beat(S, "So I killed Ollama") - 0.2;
  const ev: Ev[] = [
    { kind: "type", at: 0.2, text: "python docs/video/demo/seg9_outage.py", cps: 40 },
    { kind: "print", at: go, text: cap.seg9, reveal: 1.4 },
    { kind: "hl", at: beat(S, "The caller got an error"), until: beat(S, "The health check stayed up"), match: ["HTTP 502"] },
    { kind: "hl", at: beat(S, "The health check stayed up"), until: beat(S, "when I restarted Ollama"), match: ["/healthz 200", "1 running + 2 queued"] },
    { kind: "hl", at: beat(S, "when I restarted Ollama"), until: beat(S, "For the big one"), match: ["ready after 147 s", "first answer afterwards"] },
  ];
  return <Scene seg={S} events={ev} label="REPLAY of data captured from a real run (2026-10-23, qwen3:8b service); not a live recording"
    banners={[{ at: beat(S, "For the big one"), text: "32B model: re-reading the docs alone takes about 8.5 minutes", color: C.amber }]} />;
};

export const Seg11: React.FC = () => {
  const S = "seg11", L = cap.seg11.split("\n");
  const starts = L.map((l, i) => (/^\s+\$ /.test(l) ? i : -1)).filter((i) => i >= 0);
  const block = (k: number) => L.slice(starts[k], k + 1 < starts.length ? starts[k + 1] : L.length).join("\n").replace(/\s+$/, "");
  const tb = [beat(S, "A gate re-runs the questions"), beat(S, "fails if accuracy or abstention"), beat(S, "It also locks"), beat(S, "change one fact")];
  const ev: Ev[] = [
    { kind: "type", at: 0.2, text: "python docs/video/demo/seg11_gate.py", cps: 40 },
    ...[0, 1, 2, 3].map((k) => ({ kind: "print" as const, at: tb[k], text: block(k), reveal: 1.2 })),
    { kind: "hl", at: tb[0], until: tb[1], match: ["GATE: passed"] }, { kind: "hl", at: tb[1], until: tb[2], match: ["FAIL", "GATE: FAILED"] },
    { kind: "hl", at: tb[2], until: tb[3], match: ["GATE: passed"] }, { kind: "hl", at: tb[3], until: tb[3] + 40, match: ["FAIL", "GATE: FAILED", "change ONE fact"] },
  ];
  return <Scene seg={S} events={ev} label="Terminal replay of real output (runs on a throw-away copy of the repository; not a live screen recording)"
    banners={[{ at: beat(S, "It runs in seconds"), text: "runs in seconds · a secret scanner (gitleaks) checks every push", pos: "top" }]} />;
};
