import React from "react";
import { Slide, Appear, Footnote, Narration, beat, C } from "./ui";
import { DATA } from "./data";

// Segment 1 (hook): the two numbers appear as the voice reaches them.
const S = "seg1";
export const Hook: React.FC = () => (
  <Slide>
    <Narration seg={S} />
    <div style={{ marginTop: 40 }}>
      <Appear at={beat(S, "What if your AI")} dur={1}><div style={{ fontSize: 92, fontWeight: 800, letterSpacing: -2 }}>What if your AI never had to <span style={{ color: C.teal }}>search</span>?</div></Appear>
      <Appear at={beat(S, "Cache-augmented generation")} dur={1}><div style={{ fontSize: 50, color: C.muted, marginTop: 26 }}>Cache-augmented generation (CAG): read the knowledge base once, keep the memory, skip retrieval.</div></Appear>
    </div>
    <div style={{ display: "flex", alignItems: "center", gap: 50, marginTop: 70 }}>
      <Appear at={beat(S, "I tested it against RAG")} style={{ flex: 1, background: C.panel, borderRadius: 24, padding: 40, border: `2px solid ${C.red}` }}>
        <div style={{ fontSize: 32, color: C.muted }}>CAG with an 8B model</div>
        <div style={{ fontSize: 130, fontWeight: 800, color: C.red, lineHeight: 1.1 }}>{Math.round(DATA.heldOut.cag8 * 100)}%</div>
        <div style={{ fontSize: 30, color: C.muted }}>of the held-out questions answered right</div>
      </Appear>
      <Appear at={beat(S, "But what decided")} style={{ fontSize: 44, color: C.amber, width: 250, textAlign: "center", fontWeight: 700 }}>same data, same trick</Appear>
      <Appear at={beat(S, "It was the size of the model")} style={{ flex: 1, background: C.panel, borderRadius: 24, padding: 40, border: `2px solid ${C.teal}` }}>
        <div style={{ fontSize: 32, color: C.muted }}>CAG with a 32B model</div>
        <div style={{ fontSize: 130, fontWeight: 800, color: C.teal, lineHeight: 1.1 }}>{Math.round(DATA.heldOut.cag32 * 100)}%</div>
        <div style={{ fontSize: 30, color: C.muted }}>of the held-out questions answered right</div>
      </Appear>
    </div>
    <Footnote>50 held-out questions {"·"} local models {"·"} one MacBook</Footnote>
  </Slide>
);
