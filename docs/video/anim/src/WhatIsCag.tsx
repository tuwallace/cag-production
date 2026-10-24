import React from "react";
import { Slide, Appear, Narration, beat, C } from "./ui";

// Segment 2: two lanes, RAG on top, CAG below; three red tags for the catches.
const S = "seg2";
const Box: React.FC<{ children: React.ReactNode; color?: string; w?: number }> = ({ children, color = C.panelLine, w = 330 }) => (
  <div style={{ width: w, minHeight: 96, background: C.panel, border: `2px solid ${color}`, borderRadius: 18, display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center", fontSize: 30, fontWeight: 700, padding: "10px 14px" }}>{children}</div>
);
const Arrow = () => <div style={{ fontSize: 44, color: C.muted, width: 50, textAlign: "center" }}>{"→"}</div>;
const TAGS: [string, string][] = [["must fit in the context window", "everything must fit"], ["same text for everyone", "everyone gets the same text"], ["slow first request", "the first request is slow"]];
export const WhatIsCag: React.FC = () => (
  <Slide title="RAG searches. CAG remembers.">
    <Narration seg={S} />
    <Appear at={beat(S, "RAG looks up")} style={{ marginTop: 6 }}>
      <div style={{ fontSize: 30, color: C.muted, marginBottom: 12 }}>RAG: look up a few passages for every question</div>
      <div style={{ display: "flex", alignItems: "center" }}><Box>Question</Box><Arrow /><Box color={C.amber}>Search the knowledge base</Box><Arrow /><Box>A few passages</Box><Arrow /><Box>Model</Box></div>
    </Appear>
    <Appear at={beat(S, "CAG skips")} style={{ marginTop: 34 }}>
      <div style={{ fontSize: 30, color: C.teal, marginBottom: 12 }}>CAG: read everything once, reuse the memory</div>
      <div style={{ display: "flex", alignItems: "center", gap: 0 }}>
        <Appear at={beat(S, "You put the entire")}><Box color={C.teal} w={380}>Whole knowledge base (read once)</Box></Appear>
        <Appear at={beat(S, "the KV cache")}><div style={{ display: "flex", alignItems: "center" }}><Arrow /><Box color={C.teal} w={330}>KV cache = the model{"’"}s memory of it</Box></div></Appear>
        <Appear at={beat(S, "Every later question")}><div style={{ display: "flex", alignItems: "center" }}><Arrow /><Box w={330}>Each question reuses it</Box></div></Appear>
      </div>
    </Appear>
    <div style={{ display: "flex", gap: 22, marginTop: 44 }}>
      {TAGS.map(([t, phrase]) => <Appear key={t} at={beat(S, phrase)}><span style={{ display: "inline-block", border: `3px solid ${C.red}`, color: C.red, borderRadius: 14, padding: "10px 22px", fontSize: 32, fontWeight: 700 }}>{t}</span></Appear>)}
    </div>
    <Appear at={beat(S, "It suits a small")} style={{ position: "absolute", left: 90, right: 90, bottom: 90, fontSize: 46, fontWeight: 700, color: C.teal }}>
      Best for a small, stable knowledge base that people ask about a lot.
    </Appear>
  </Slide>
);
