import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

describe("depth of field and J and L cuts on a shot", () => {
  const lab = readFileSync("src/ShotLab.tsx", "utf8");
  const cut = readFileSync("src/SoundCut.tsx", "utf8");
  it("the Camera tab has a depth-of-field choice named by its aperture, with an automatic default", () => {
    expect(lab).toMatch(/aria-label="Depth of field"/);
    expect(lab).toMatch(/Automatic \(soft behind people, left alone in wide shots\)/);
    expect(lab).toMatch(/about f\/1\.4/);
    expect(lab).toMatch(/about f\/11/);
    expect(lab).toMatch(/save\(\{ camera: \{ dof: e\.target\.value \} \}\)/);
  });
  it("the Voice tab has the lead and tail for a shot that has dialogue, saved on release", () => {
    expect(lab).toMatch(/c\.dialogue\.length > 0 && <SoundCut/);
    expect(lab).toMatch(/save\(\{ sound_cut: x \}\)/);
    expect(cut).toMatch(/a J cut/);
    expect(cut).toMatch(/an L cut/);
    expect(cut).toMatch(/onPointerUp/);
    expect(cut).toMatch(/not changed/);
  });
  it("only changes settings of the shot: nothing paid, nothing sent", () => {
    expect(cut).not.toMatch(/queueRender|\.generate\(|castVoice|audioGen|confirmed:\s*true|fetch\(/);
  });
});
