import React from "react";
import { AbsoluteFill, Audio, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import narration from "./narration.json";

export const C = {
  bg: "#0e1320", panel: "#171e30", panelLine: "#2a3450", text: "#eef2f8", muted: "#9aa6bd",
  teal: "#38d3c2", red: "#ff6b6b", amber: "#ffc857", blue: "#6ea8ff",
};
export const FONT = '"Helvetica Neue", Helvetica, Arial, sans-serif';
export const W = 1920, H = 1080, FPS = 30;

/** 0 -> 1 progress starting at `at` seconds, lasting `dur` seconds. */
export const useProgress = (at: number, dur = 0.6) => {
  const f = useCurrentFrame(); const { fps } = useVideoConfig();
  return interpolate(f, [at * fps, (at + dur) * fps], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
};

export const Appear: React.FC<{ at: number; dur?: number; style?: React.CSSProperties; children: React.ReactNode }> = ({ at, dur = 0.6, style, children }) => {
  const p = useProgress(at, dur);
  return <div style={{ opacity: p, transform: `translateY(${(1 - p) * 28}px)`, ...style }}>{children}</div>;
};

export const Slide: React.FC<{ title?: string; children: React.ReactNode }> = ({ title, children }) => (
  <AbsoluteFill style={{ background: C.bg, fontFamily: FONT, color: C.text, padding: "70px 90px" }}>
    {title && <div style={{ fontSize: 56, fontWeight: 700, letterSpacing: -1, marginBottom: 34 }}>{title}</div>}
    {children}
  </AbsoluteFill>
);

export const Pill: React.FC<{ color: string; children: React.ReactNode }> = ({ color, children }) => (
  <span style={{ border: `3px solid ${color}`, color, borderRadius: 14, padding: "6px 20px", fontSize: 30, fontWeight: 700, letterSpacing: 1 }}>{children}</span>
);

export const Footnote: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{ position: "absolute", left: 90, right: 90, bottom: 40, fontSize: 24, color: C.muted }}>{children}</div>
);

/** Vertical bar that grows from `at` seconds. */
export const Bar: React.FC<{ label: string; value: number; color: string; at: number; height?: number; width?: number }> = ({ label, value, color, at, height = 480, width = 190 }) => {
  const p = useProgress(at, 1.2);
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: width + 50 }}>
      <div style={{ height, display: "flex", flexDirection: "column", justifyContent: "flex-end", alignItems: "center" }}>
        <div style={{ fontSize: 46, fontWeight: 700, marginBottom: 10, opacity: p }}>{(value * p).toFixed(2)}</div>
        <div style={{ width, height: value * height * p, background: color, borderRadius: "14px 14px 0 0" }} />
      </div>
      <div style={{ height: 3, width: width + 40, background: C.panelLine }} />
      <div style={{ fontSize: 26, color: C.muted, marginTop: 14, textAlign: "center", lineHeight: 1.25 }}>{label}</div>
    </div>
  );
};

// ---- narration sync -------------------------------------------------------------------------------------------
// narration.json is produced by ../narration/build_narration.py. A "beat" is the second at which a phrase is spoken:
// sentence start + (where the phrase sits in the sentence) x (sentence duration). Re-run the builder after changing the
// voice or the wording and every animation step moves with it. A missing phrase throws, so a script edit can't silently
// leave a step unsynced.
type Sentence = { text: string; start: number; end: number };
export const NARR = narration as Record<string, { audio: string; duration: number; sentences: Sentence[] }>;
export const beat = (seg: string, phrase: string, lead = 0.2): number => {
  for (const s of NARR[seg].sentences) {
    const i = s.text.indexOf(phrase);
    if (i >= 0) return Math.max(0, s.start + (i / s.text.length) * (s.end - s.start) - lead);
  }
  throw new Error(`phrase not found in ${seg}: "${phrase}"`);
};
export const clipSeconds = (seg: string) => NARR[seg].duration + 2;
export const Narration: React.FC<{ seg: string }> = ({ seg }) => <Audio src={staticFile(NARR[seg].audio)} />;
