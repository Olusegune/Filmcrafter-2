import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { lineWords, limitWords } from "../spendWords";

const base = { unit: "kie_credits", unit_name: "Kie credits", reported: 0, estimated: 0, reported_operations: 0, estimated_operations: 0 };

describe("spending words", () => {
  it("calls a provider's own figure reported and ours an estimate, never blended", () => {
    expect(lineWords({ ...base, reported: 164, reported_operations: 1 })).toBe("164 Kie credits reported");
    expect(lineWords({ ...base, unit: "usd", unit_name: "dollars (estimated)", estimated: 1.25, estimated_operations: 1 })).toBe("about $1.25 (estimate)");
    expect(lineWords({ ...base, unit: "elevenlabs_credits", unit_name: "ElevenLabs credits", reported: 9, reported_operations: 3, estimated: 3, estimated_operations: 1 })).toContain("9 ElevenLabs credits reported + about 3 ElevenLabs credits (estimate, 1 not reported)");
    expect(lineWords(base)).toBe("no amount reported");
  });
  it("says limits in words", () => expect(limitWords({ elevenlabs_credits: 150 })).toBe("150 elevenlabs credits"));
  it("the sheet only reads: no way to start, repeat or pay", () => {
    const t = readFileSync("src/SpendingSheet.tsx", "utf8");
    expect(t).toMatch(/filmSpending/);
    expect(t).not.toMatch(/queueRender|\.generate\(|confirmed:\s*true|castVoice|audioGen|ledger_resolve/);
  });
});
