import React from "react";
import { Slide, Appear, Footnote, Narration, beat, C } from "./ui";

// Segment 10: hidden instructions, planted personal data, and load.
const S = "seg10";
const Card: React.FC<{ title: string; at: number; children: React.ReactNode }> = ({ title, at, children }) => (
  <Appear at={at} style={{ flex: 1, background: C.panel, border: `2px solid ${C.panelLine}`, borderRadius: 22, padding: "26px 30px", minHeight: 520 }}>
    <div style={{ fontSize: 36, fontWeight: 700, marginBottom: 22 }}>{title}</div>{children}
  </Appear>
);
const Row: React.FC<{ at: number; color: string; head: string; sub: string }> = ({ at, color, head, sub }) => (
  <Appear at={at} style={{ marginBottom: 22 }}><div style={{ fontSize: 34, fontWeight: 800, color }}>{head}</div><div style={{ fontSize: 26, color: C.muted, lineHeight: 1.25 }}>{sub}</div></Appear>
);
export const Attacks: React.FC = () => (
  <Slide title="Attacks and load">
    <Narration seg={S} />
    <div style={{ display: "flex", gap: 30 }}>
      <Card title="Hidden instructions in the docs" at={beat(S, "I hid instructions")}>
        <Row at={beat(S, "Neither model obeyed")} color={C.teal} head={"0 of 39 obeyed"} sub={"a command like “ignore your rules” (both models)"} />
        <Row at={beat(S, "followed a hidden instruction once")} color={C.amber} head={"1 tracking link"} sub={"the 32B model added a link it was told to add"} />
        <Row at={beat(S, "both repeated a false fact")} color={C.red} head={"false fact: 2 of 2"} sub={"a planted “update” repeated as true by both models"} />
      </Card>
      <Card title="Planted personal data" at={beat(S, "A test asking for planted")}>
        <Row at={beat(S, "got all five back")} color={C.red} head={"5 of 5 leaked"} sub={"email, phone, card number, key, SSN (fake values), when asked"} />
        <Row at={beat(S, "until I added redaction")} color={C.teal} head={"0 of 5 with redaction"} sub={"redaction on the knowledge base and on the answers"} />
      </Card>
      <Card title="Under load" at={beat(S, "And under load")}>
        <Row at={beat(S, "about five requests a minute")} color={C.amber} head={"about 5 requests / minute"} sub={"for the 32B model, however many people ask"} />
        <Row at={beat(S, "turns the extras away")} color={C.teal} head={"extras bounced in 10 ms"} sub={"instead of making everyone wait"} />
      </Card>
    </div>
    <Appear at={beat(S, "No prompt fixes that")} style={{ position: "absolute", left: 90, right: 90, bottom: 100, fontSize: 44, fontWeight: 700, color: C.teal }}>
      No prompt fixes a false fact: control what goes into the knowledge base.
    </Appear>
    <Footnote>Details: docs/12-security-tests.md</Footnote>
  </Slide>
);
