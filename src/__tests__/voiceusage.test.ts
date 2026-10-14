import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { attemptWords, COST_UNKNOWN, confirmWords, STATUS_WORDS, usageWords } from "../voiceUsage";

const unit = (o: Partial<{ operations: number; estimated: number; reported: number; unreported_operations: number; estimated_unreported: number }>) =>
  ({ operations: 0, estimated: 0, reported: 0, unreported_operations: 0, estimated_unreported: 0, ...o });

describe("what the person is told before anything is charged", () => {
  it("says what will happen, with whom, what it costs and whether a voice slot is taken", () => {
    const t = confirmWords({ action: "Speak S01-03 as Lila?", provider: "ElevenLabs", cost: "29 characters, about 29 credits of your plan" });
    expect(t).toContain("Speak S01-03 as Lila?");
    expect(t).toContain("Provider: ElevenLabs");
    expect(t).toContain("Cost: 29 characters, about 29 credits of your plan");
    expect(t).toContain("Voice slot: none is taken");
    const slot = confirmWords({ action: "Keep it", provider: "ElevenLabs", cost: "none", slot: "one of your 10 (you use 3 now)" });
    expect(slot).toContain("Voice slot: one of your 10 (you use 3 now)");
  });
  it("never invents a number when the cost is not published, and asks to accept that", () => {
    expect(COST_UNKNOWN).toMatch(/does not publish/);
    expect(COST_UNKNOWN).toMatch(/unknown/);
    expect(COST_UNKNOWN).toMatch(/accept/);
    expect(COST_UNKNOWN).not.toMatch(/\d/);
  });
});

describe("the voice usage line", () => {
  it("shows a number as 'reported' only when ElevenLabs reported it", () => {
    expect(usageWords({ elevenlabs_credits: unit({ operations: 3, reported: 320, estimated: 330 }) })).toBe("Voice generation: 320 ElevenLabs credits reported");
  });
  it("keeps estimates apart: reported amounts first, the rest labelled as estimated", () => {
    expect(usageWords({ elevenlabs_credits: unit({ operations: 3, reported: 100, estimated: 140, unreported_operations: 1, estimated_unreported: 40 }) }))
      .toBe("Voice generation: 100 ElevenLabs credits reported, plus 1 operation with no amount reported (about 40 credits, estimated)");
  });
  it("with nothing reported, never offers an estimate as a total", () => {
    const t = usageWords({ elevenlabs_credits: unit({ operations: 2, estimated: 58, unreported_operations: 2, estimated_unreported: 58 }) });
    expect(t).toContain("2 operations so far");
    expect(t).toContain("has not reported amounts");
    expect(t).toContain("estimated at about 58 credits");
    expect(t).not.toMatch(/credits reported/);
  });
  it("counts voice slots exactly (each keep or clone takes one) and says nothing before anything was done", () => {
    expect(usageWords({ voice_slot: unit({ operations: 1 }) })).toBe("1 voice slot taken through FilmCrafter");
    expect(usageWords({ voice_slot: unit({ operations: 2 }) })).toBe("2 voice slots taken through FilmCrafter");
    expect(usageWords({})).toBe("");
    expect(usageWords(undefined)).toBe("");
    expect(usageWords({ elevenlabs_credits: unit({}) })).toBe("");
  });
  it("describes an unresolved operation in plain words and every status in the record", () => {
    const w = attemptWords({ action: "speak", person: "Lila", shot: "S01-03", at: 1790000000 });
    expect(w).toContain("Speak a line S01-03 (Lila)");
    expect(Object.keys(STATUS_WORDS).sort()).toEqual(["completed", "confirmed", "failed_before_submission", "prepared", "refused", "submitted", "uncertain"]);
    expect(STATUS_WORDS.refused).toContain("not charged");
    expect(STATUS_WORDS.uncertain).toBe("outcome unknown");
  });
});

describe("the screens ask first, and send the engine its flags only after a yes (wiring guard; the engine refuses anyway)", () => {
  const src = readFileSync("src/CastVoices.tsx", "utf8");
  const between = (a: string, b: string) => src.slice(src.indexOf(a), src.indexOf(b, src.indexOf(a)));
  it("designing asks, and sends confirmed and unknown_cost_accepted after the question", () => {
    const f = between("const hearOptions", "const keep");
    expect(f.indexOf("await ask(")).toBeLessThan(f.indexOf('castVoice<{ previews'));
    expect(f).toContain("confirmed: true, unknown_cost_accepted: true");
    expect(f).toContain("COST_UNKNOWN");
  });
  it("keeping a designed voice asks and tells how many voice slots are in use", () => {
    const f = between("const keep", "const pickFiles");
    expect(f.indexOf("await ask(")).toBeLessThan(f.indexOf('castVoice("design_save"'));
    expect(f).toContain("confirmed: true");
    expect(src).toContain("you use ${plan.slots_used} now");
  });
  it("cloning sends consent and confirmed as two separate things, after asking", () => {
    const f = between("const makeClone", "return (\n    <div className=\"overlay\"");
    expect(f.indexOf("await ask(")).toBeLessThan(f.indexOf('castVoice("clone"'));
    expect(f).toContain("consent, confirmed: true");
    expect(src).toMatch(/disabled=\{[^}]*!consent/);                              // the button stays off until the consent box is ticked
  });
  it("every confirmation names the provider", () => {
    expect((src.match(/confirmWords\(/g) ?? []).length).toBeGreaterThanOrEqual(6);
    expect((src.match(/provider: "ElevenLabs"/g) ?? []).length).toBeGreaterThanOrEqual(6);
  });
});
