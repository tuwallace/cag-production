import React from "react";
import { Slide, Appear, Narration, beat, C } from "./ui";

// Segment 12: five takeaways, then the caveat.
const S = "seg12";
const ANCHORS = ["One:", "Two:", "Three:", "Four:", "Five:"];
const POINTS = [
  "CAG fits a small, stable knowledge base that is asked about a lot.",
  "The cache is the product: budget for the cold start.",
  "Model size mattered more than any trick I tried.",
  "Measure what happens on questions the knowledge base can’t answer.",
  "Keep questions you didn’t tune on.",
];
export const Takeaways: React.FC = () => (
  <Slide title="Five takeaways">
    <Narration seg={S} />
    <div style={{ marginTop: 10 }}>
      {POINTS.map((p, i) => (
        <Appear key={p} at={beat(S, ANCHORS[i])} style={{ display: "flex", alignItems: "center", gap: 30, fontSize: 46, margin: "22px 0" }}>
          <span style={{ width: 70, height: 70, borderRadius: 35, background: C.teal, color: C.bg, fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 40 }}>{i + 1}</span>
          {p}
        </Appear>
      ))}
    </div>
    <Appear at={beat(S, "Everything here is local")} style={{ position: "absolute", left: 90, right: 90, bottom: 70, fontSize: 32, color: C.muted, lineHeight: 1.35 }}>
      All local and open. Caveats: one machine {"·"} 90 questions written by an AI assistant {"·"} no human review {"·"} one run per setting.
    </Appear>
  </Slide>
);
