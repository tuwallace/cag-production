import React from "react";
import { Slide, Appear, Footnote, Narration, beat, C } from "./ui";
import { DATA } from "./data";

// Segment 3: the stack, the corpus, then the 90 questions split two ways.
const S = "seg3";
const Chip: React.FC<{ at: number; children: React.ReactNode }> = ({ at, children }) => (
  <Appear at={at}><span style={{ display: "inline-block", background: C.panel, border: `2px solid ${C.panelLine}`, borderRadius: 40, padding: "12px 26px", fontSize: 32 }}>{children}</span></Appear>
);
const Cells: React.FC<{ answerable: number; none: number }> = ({ answerable, none }) => (
  <div style={{ display: "flex", gap: 5 }}>
    {Array.from({ length: answerable + none }).map((_, i) => <div key={i} style={{ width: 29, height: 40, borderRadius: 7, background: i < answerable ? C.teal : C.amber, opacity: 0.85 }} />)}
  </div>
);
export const TheTest: React.FC = () => (
  <Slide title="The test: all local, 90 questions">
    <Narration seg={S} />
    <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
      <Chip at={beat(S, "Everything here is local")}>All local {"·"} no cloud API</Chip>
      <Chip at={beat(S, "Ollama, a Qwen")}>Ollama</Chip><Chip at={beat(S, "a Qwen eight-billion")}>Qwen 8B</Chip><Chip at={beat(S, "a Qwen thirty-two-billion")}>Qwen 32B</Chip><Chip at={beat(S, "on one MacBook")}>one MacBook</Chip>
    </div>
    <Appear at={beat(S, "The knowledge base is a slice")} style={{ marginTop: 30, background: C.panel, borderRadius: 20, border: `2px solid ${C.panelLine}`, padding: "20px 34px", fontSize: 38, width: 1000 }}>
      Ollama{"’"}s documentation: <b>118 sections</b>, about <b>26,000 tokens</b>
    </Appear>
    <Appear at={beat(S, "wrote the ninety test questions")} style={{ marginTop: 30 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
        <div><div style={{ fontSize: 30, color: C.muted, marginBottom: 10 }}>Development: {DATA.questions.dev}</div><Cells answerable={DATA.questions.devAnswerable} none={DATA.questions.devUnanswerable} /></div>
        <Appear at={beat(S, "Forty questions for development")} dur={0.8}><div><div style={{ fontSize: 30, color: C.muted, marginBottom: 10 }}>Held back: {DATA.questions.heldOut}</div><Cells answerable={DATA.questions.newAnswerable} none={DATA.questions.newUnanswerable} /></div></Appear>
      </div>
    </Appear>
    <Appear at={beat(S, "Fifty-one of them")} style={{ marginTop: 20, fontSize: 32 }}>
      <span style={{ color: C.teal }}>{"■"} answerable (39)</span>{"   "}<span style={{ color: C.amber }}>{"■"} not in the docs (51): the right answer is {"“"}not in the knowledge base{"”"}</span>
    </Appear>
    <Appear at={beat(S, "No human reviewed")} style={{ position: "absolute", left: 90, right: 90, bottom: 90, fontSize: 44, fontWeight: 700, color: C.red }}>
      Written by an AI assistant. No human review.
    </Appear>
    <Footnote>Models: qwen3:8b and qwen2.5:32b via Ollama</Footnote>
  </Slide>
);
