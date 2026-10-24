import React from "react";
import { Slide, Appear, Bar, Footnote, Narration, beat, C } from "./ui";
import { DATA } from "./data";

// Segment 8: the winner changed when 50 new questions arrived.
const S = "seg8";
export const BenchFlip: React.FC = () => (
  <Slide title="Surprise 3: my benchmark fooled me">
    <Narration seg={S} />
    <div style={{ display: "flex", gap: 120, marginTop: 0 }}>
      <div>
        <Appear at={beat(S, "On the first forty questions")}><div style={{ fontSize: 34, marginBottom: 14 }}>First 40 questions</div></Appear>
        <div style={{ display: "flex", gap: 24 }}>
          <Bar label={"Semantic check"} value={DATA.flip.first40.semantic} color={C.blue} at={beat(S, "a semantic similarity check")} height={380} width={170} />
          <Bar label={"Word-overlap check"} value={DATA.flip.first40.overlap} color={C.muted} at={beat(S, "a semantic similarity check") + 0.4} height={380} width={170} />
        </div>
      </div>
      <div>
        <Appear at={beat(S, "Then I wrote fifty new")}><div style={{ fontSize: 34, marginBottom: 14 }}>50 new questions</div></Appear>
        <div style={{ display: "flex", gap: 24 }}>
          <Bar label={"Semantic check"} value={DATA.flip.new50.semantic} color={C.muted} at={beat(S, "Then I wrote fifty new") + 0.6} height={380} width={170} />
          <Bar label={"Word-overlap check"} value={DATA.flip.new50.overlap} color={C.teal} at={beat(S, "the simple word-overlap check won")} height={380} width={170} />
        </div>
      </div>
      <div style={{ width: 430 }}>
        <Appear at={beat(S, "Forty questions had been")} style={{ fontSize: 40, fontWeight: 700, color: C.amber }}>40 questions were too few to choose a method.</Appear>
        <Appear at={beat(S, "The small model's refusal rate")} style={{ marginTop: 30, background: C.panel, border: `2px solid ${C.panelLine}`, borderRadius: 18, padding: "18px 24px" }}>
          <div style={{ fontSize: 26, color: C.muted }}>Small model refuses unanswerable questions</div>
          <div style={{ fontSize: 64, fontWeight: 800 }}><span style={{ color: C.amber }}>{DATA.refusal.first}</span> {"→"} <span style={{ color: C.red }}>{DATA.refusal.second}</span></div>
        </Appear>
      </div>
    </div>
    <Appear at={beat(S, "Always keep questions")} style={{ position: "absolute", left: 90, right: 90, bottom: 100, fontSize: 46, fontWeight: 700, color: C.teal }}>
      Always keep questions you haven{"’"}t tuned on.
    </Appear>
    <Footnote>AUROC: how well each check separates good answers from invented ones (1.0 = perfectly)</Footnote>
  </Slide>
);
