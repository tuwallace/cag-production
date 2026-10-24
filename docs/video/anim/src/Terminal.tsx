import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { C, FONT, Narration } from "./ui";

// A terminal REPLAY: types commands and reveals REAL captured output, timed to the narration. It is not a screen recording and says so on screen.
export type Ev =
  | { kind: "clear"; at: number }
  | { kind: "type"; at: number; text: string; cps?: number; prompt?: string }
  | { kind: "print"; at: number; text: string; reveal?: number; color?: string }
  | { kind: "hl"; at: number; until: number; match: string[] };
type Line = { text: string; color?: string; cmd?: boolean; typing?: boolean; hl?: boolean };

const MONO = 'Menlo, "SF Mono", Monaco, Consolas, monospace';
export const FS = 22, LH = 29, COLS = 124;

const wrap = (text: string): string[] =>
  text.split("\n").flatMap((l) => {
    if (l.length <= COLS) return [l];
    const indent = l.match(/^\s*/)![0], out: string[] = []; let cur = "";
    for (const w of l.trim().split(" ")) { if ((indent + cur + " " + w).length > COLS && cur) { out.push(indent + cur); cur = w; } else cur = cur ? cur + " " + w : w; }
    out.push(indent + cur); return out;
  });

export const buildLines = (events: Ev[], t: number): Line[] => {
  let lines: Line[] = [];
  for (const e of [...events].sort((a, b) => a.at - b.at)) {
    if (e.at > t) break;
    if (e.kind === "clear") lines = [];
    else if (e.kind === "type") {
      const n = Math.min(e.text.length, Math.floor((t - e.at) * (e.cps ?? 30)));
      lines.push({ text: (e.prompt ?? "$ ") + e.text.slice(0, n), cmd: true, typing: n < e.text.length });
    } else if (e.kind === "print") {
      const all = wrap(e.text);
      const k = e.reveal ? Math.min(all.length, Math.ceil(((t - e.at) / e.reveal) * all.length)) : all.length;
      lines.push(...all.slice(0, k).map((text) => ({ text, color: e.color })));
    }
  }
  for (const e of events) if (e.kind === "hl" && t >= e.at && t <= e.until) for (const l of lines) if (e.match.some((m) => l.text.includes(m))) l.hl = true;
  return lines;
};

export const Window: React.FC<{ title?: string; children: React.ReactNode }> = ({ title = "cag-production", children }) => (
  <div style={{ position: "absolute", left: 80, right: 80, top: 50, bottom: 80, background: "#0b0f19", border: `2px solid ${C.panelLine}`, borderRadius: 18, overflow: "hidden", boxShadow: "0 20px 60px rgba(0,0,0,.5)" }}>
    <div style={{ height: 44, background: "#161d2e", display: "flex", alignItems: "center", padding: "0 18px", gap: 10 }}>
      {["#ff5f57", "#febc2e", "#28c840"].map((c) => <span key={c} style={{ width: 14, height: 14, borderRadius: 7, background: c }} />)}
      <span style={{ marginLeft: 16, fontFamily: FONT, fontSize: 20, color: C.muted }}>{title}</span>
    </div>
    <div style={{ position: "absolute", top: 44, left: 0, right: 0, bottom: 0, overflow: "hidden" }}>{children}</div>
  </div>
);

export const Replay: React.FC<{ events: Ev[]; areaHeight?: number }> = ({ events, areaHeight = 890 }) => {
  const f = useCurrentFrame(); const { fps } = useVideoConfig(); const t = f / fps;
  const lines = buildLines(events, t); const rows = Math.floor(areaHeight / LH);
  const shift = Math.max(0, lines.length - rows) * LH;
  const last = lines[lines.length - 1]; const blink = Math.floor(t * 2) % 2 === 0;
  return (
    <div style={{ position: "absolute", top: 16, left: 24, right: 24, bottom: 0, overflow: "hidden" }}>
    <div style={{ fontFamily: MONO, fontSize: FS, lineHeight: `${LH}px`, color: "#d8dee9", whiteSpace: "pre", transform: `translateY(${-shift}px)` }}>
      {lines.map((l, i) => (
        <div key={i} style={{ height: LH, background: l.hl ? "rgba(56,211,194,.22)" : "transparent", borderRadius: 4, color: l.cmd ? C.teal : l.color ?? "#d8dee9", marginLeft: -8, paddingLeft: 8 }}>
          {l.text || " "}{i === lines.length - 1 && (l.typing || (l.cmd && blink)) ? <span style={{ background: C.teal, color: C.teal }}>{"█"}</span> : null}
        </div>
      ))}
    </div>
    </div>
  );
};

export const ReplayLabel: React.FC<{ text?: string }> = ({ text = "Terminal replay of real captured output (not a live screen recording)" }) => (
  <div style={{ position: "absolute", left: 90, bottom: 26, fontFamily: FONT, fontSize: 22, color: C.muted }}>{text}</div>
);

export const TerminalScene: React.FC<{ seg: string; events: Ev[]; title?: string; label?: string }> = ({ seg, events, title, label }) => (
  <AbsoluteFill style={{ background: C.bg }}>
    <Narration seg={seg} />
    <Window title={title}><Replay events={events} /></Window>
    <ReplayLabel text={label} />
  </AbsoluteFill>
);
