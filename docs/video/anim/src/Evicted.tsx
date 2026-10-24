import React from "react";
import { Slide, Appear, Footnote, Narration, beat, useProgress, C } from "./ui";

// Segment 5: one Ollama server has one cache slot; a second model pushes the cache out; two servers fix it.
const S = "seg5";
const Server: React.FC<{ label: string; children: React.ReactNode; w?: number }> = ({ label, children, w = 520 }) => (
  <div style={{ width: w, background: C.panel, border: `2px solid ${C.panelLine}`, borderRadius: 22, padding: "22px 28px" }}>
    <div style={{ fontSize: 30, color: C.muted, marginBottom: 16 }}>{label}</div>{children}
  </div>
);
const Slot: React.FC<{ color: string; text: string }> = ({ color, text }) => (
  <div style={{ height: 110, borderRadius: 16, border: `3px solid ${color}`, color, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 34, fontWeight: 700 }}>{text}</div>
);
export const Evicted: React.FC = () => {
  const evict = useProgress(beat(S, "When I loaded a second model"), 0.8);
  const fixed = useProgress(beat(S, "The fix was"), 0.8);
  return (
    <Slide title="Surprise 1: the cache got evicted">
      <Narration seg={S} />
      <div style={{ display: "flex", gap: 60, alignItems: "flex-start", marginTop: 20 }}>
        <div style={{ opacity: 1 - fixed * 0.85 }}>
          <Appear at={beat(S, "The cache lives inside")}>
            <Server label="One Ollama server = one cache slot">
              <div style={{ position: "relative", height: 110 }}>
                <div style={{ position: "absolute", inset: 0, opacity: 1 - evict }}><Slot color={C.teal} text="docs cache (warm)" /></div>
                <div style={{ position: "absolute", inset: 0, opacity: evict }}><Slot color={C.red} text="cache evicted" /></div>
              </div>
            </Server>
          </Appear>
          <Appear at={beat(S, "When I loaded a second model")} style={{ marginTop: 22, fontSize: 36 }}>
            <span style={{ background: C.panel, border: `2px solid ${C.amber}`, borderRadius: 16, padding: "10px 22px", color: C.amber, fontWeight: 700 }}>+ a chat model</span>
          </Appear>
          <Appear at={beat(S, "sixty-five seconds")} style={{ marginTop: 30, fontSize: 130, fontWeight: 800, color: C.red, lineHeight: 1 }}>65 s <span style={{ fontSize: 36, color: C.muted, fontWeight: 400 }}>cold start again</span></Appear>
        </div>
        <Appear at={beat(S, "The fix was")} style={{ flex: 1 }}>
          <div style={{ fontSize: 30, color: C.teal, marginBottom: 16 }}>Dedicated server for the cached model</div>
          <div style={{ display: "flex", gap: 30 }}>
            <Server label="Ollama server A" w={430}><Slot color={C.teal} text="docs cache (warm)" /></Server>
            <Server label="Ollama server B" w={430}><Slot color={C.blue} text="chat model" /></Server>
          </div>
        </Appear>
      </div>
      <Footnote>Measured: 65.7 s to read about 14,900 tokens again after another model was loaded (8B model)</Footnote>
    </Slide>
  );
};
