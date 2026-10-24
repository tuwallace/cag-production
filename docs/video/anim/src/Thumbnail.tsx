import React from "react";
import { AbsoluteFill } from "remotion";
import { C, FONT } from "./ui";
import { DATA } from "./data";

export const Thumbnail: React.FC = () => (
  <AbsoluteFill style={{ background: C.bg, fontFamily: FONT, color: C.text, padding: "60px 70px" }}>
    <div style={{ fontSize: 70, fontWeight: 800, letterSpacing: -2, color: C.muted }}>CAG vs RAG, run locally</div>
    <div style={{ display: "flex", alignItems: "center", gap: 36, marginTop: 40 }}>
      <div style={{ fontSize: 230, fontWeight: 900, color: C.red, lineHeight: 1 }}>{Math.round(DATA.heldOut.cag8 * 100)}%</div>
      <div style={{ fontSize: 120, color: C.muted }}>{"→"}</div>
      <div style={{ fontSize: 230, fontWeight: 900, color: C.teal, lineHeight: 1 }}>{Math.round(DATA.heldOut.cag32 * 100)}%</div>
    </div>
    <div style={{ fontSize: 54, fontWeight: 700, marginTop: 30 }}>same data {"·"} same trick {"·"} <span style={{ color: C.amber }}>bigger model</span></div>
  </AbsoluteFill>
);
