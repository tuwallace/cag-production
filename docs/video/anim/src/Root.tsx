import React from "react";
import { Composition } from "remotion";
import { W, H, FPS, clipSeconds } from "./ui";
import { Hook } from "./Hook";
import { WhatIsCag } from "./WhatIsCag";
import { TheTest } from "./TheTest";
import { Evicted } from "./Evicted";
import { BenchFlip } from "./BenchFlip";
import { Attacks } from "./Attacks";
import { Takeaways } from "./Takeaways";
import { Thumbnail } from "./Thumbnail";
import { Seg4, Seg6, Seg7, Seg9, Seg11 } from "./TermSegs";

// Each clip is as long as its narration audio (+2 s); see ../narration/build_narration.py and ../../script.md.
const CLIPS = [
  { id: "Hook", c: Hook, seg: "seg1" }, { id: "WhatIsCag", c: WhatIsCag, seg: "seg2" }, { id: "TheTest", c: TheTest, seg: "seg3" },
  { id: "Seg4", c: Seg4, seg: "seg4" }, { id: "Evicted", c: Evicted, seg: "seg5" }, { id: "Seg6", c: Seg6, seg: "seg6" },
  { id: "Seg7", c: Seg7, seg: "seg7" }, { id: "BenchFlip", c: BenchFlip, seg: "seg8" }, { id: "Seg9", c: Seg9, seg: "seg9" },
  { id: "Attacks", c: Attacks, seg: "seg10" }, { id: "Seg11", c: Seg11, seg: "seg11" }, { id: "Takeaways", c: Takeaways, seg: "seg12" },
];
export const Root: React.FC = () => (
  <>
    {CLIPS.map((k) => <Composition key={k.id} id={k.id} component={k.c} durationInFrames={Math.ceil(clipSeconds(k.seg) * FPS)} fps={FPS} width={W} height={H} />)}
    <Composition id="Thumbnail" component={Thumbnail} durationInFrames={1} fps={FPS} width={1280} height={720} />
  </>
);
