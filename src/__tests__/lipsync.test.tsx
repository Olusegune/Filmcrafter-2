import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { LipSyncNote, SingChoice, TimingLine } from "../LipSyncNote";

const note = (over: Partial<Parameters<typeof LipSyncNote>[0]> = {}) =>
  renderToStaticMarkup(<LipSyncNote performer="Queen Bee" lyrics={["Children!", "Come downstairs!"]} lipSync={false} audioFirst={false} keyframeBlocksAudio={false} model="Seedance 2 Fast" onMode={() => {}} {...over} />);

describe("what the Video tab says about a sung shot's mouth", () => {
  it("when the song's vocal is sent, says so and names the line", () => {
    const html = note({ lipSync: true });
    expect(html).toContain("Queen Bee sings “Children! / Come downstairs!”");
    expect(html).toContain("the song&#x27;s vocal under this shot to follow");
    expect(html).not.toContain("reference picture");
    expect(html).not.toContain("<button");
  });

  it("in 'follow the song's audio' mode, says the keyframe is only a reference picture and offers the way back", () => {
    const html = note({ lipSync: true, audioFirst: true, mode: "audio_first" });
    expect(html).toContain("reference picture");
    expect(html).toContain("the opening of the take may differ from it");
    expect(html).toContain("Use the keyframe as the first frame instead");
  });

  it("when the keyframe is why the music is not followed, says exactly that, and offers the other mode with its price of use", () => {
    const html = note({ keyframeBlocksAudio: true });
    expect(html).toContain("Seedance 2 Fast can follow the song&#x27;s audio, but not together with a first frame");
    expect(html).toContain("words in the prompt only");
    expect(html).toContain("close, but not in time with the music");
    expect(html).toContain("Follow the song&#x27;s audio instead");
    expect(html).toContain("the opening may differ from the keyframe");
    expect(html).toContain("every sung shot in the project");
    expect(html).toContain("Lip-sync this take…");                                       // and the paid alternative is named
    expect(html).not.toContain("can&#x27;t take reference audio");                        // it can: the old message was wrong for this model
  });

  it("for a model with no audio input, says that plainly (and not that it is the keyframe's fault)", () => {
    const html = note();
    expect(html).toContain("can&#x27;t take reference audio");
    expect(html).toContain("words in the prompt only");
    expect(html).not.toContain("<button");
  });

  it("the mode a button asks for is the one it names", () => {
    const asked: string[] = [];
    const el = LipSyncNote({ performer: "Q", lyrics: ["x"], lipSync: false, audioFirst: false, keyframeBlocksAudio: true, model: "M", onMode: (m) => asked.push(m) }) as { props: { children: unknown[] } };
    const text = JSON.stringify(el, (_k, v) => (typeof v === "function" ? "fn" : v));
    expect(text).toContain("Follow the song's audio instead");
    expect(asked).toEqual([]);                                                              // nothing is changed just by showing the note
  });
});

describe("choosing shot by shot, and the free sound check", () => {
  it("in Auto, a shot that shows a mouth says it was chosen and offers to always use the keyframe", () => {
    const html = note({ lipSync: true, audioFirst: true, mode: "auto" });
    expect(html).toContain("Chosen automatically: this shot shows a mouth");
    expect(html).toContain("Always use the keyframe as the first frame instead");
  });
  it("in Auto, a wide shot says why it keeps its keyframe and still offers the audio for every sung shot", () => {
    const html = note({ keyframeBlocksAudio: true, mode: "auto" });
    expect(html).toContain("too wide for a mouth to be watched");
    expect(html).toContain("Follow the song&#x27;s audio instead");
    expect(html).not.toContain("Or let PULSEFRAME choose shot by shot");               // already on
  });
  it("outside Auto, offers Auto as the gentler choice", () => {
    expect(note({ keyframeBlocksAudio: true })).toContain("Or let PULSEFRAME choose shot by shot (close-ups follow the audio)");
  });
  it("offers the free check, says it is free and local, and shows the result", () => {
    const html = note({ lipSync: true, onTiming: () => {}, timing: { verdict: "late", detail: "The take's sound follows the vocal but comes 240 ms late.", lag_ms: 240 } });
    expect(html).toContain("Check this take&#x27;s sound against the song (free)");
    expect(html).toContain("No AI, nothing is sent anywhere");
    expect(html).toContain("comes 240 ms late");
    expect(html).toContain("ls-warn");
    expect(note({ lipSync: true })).not.toContain("Check this take");                   // no handler, no button
  });
  it("tells the person what to do when the model made its own sound, and when there is no take", () => {
    expect(renderToStaticMarkup(<TimingLine timing={{ verdict: "own_audio", detail: "The take's sound does not follow the song's vocal." }} />)).toContain("Switch to following the song&#x27;s audio, then render again.");
    expect(renderToStaticMarkup(<TimingLine timing="none" />)).toContain("no take of this shot to check yet");
    expect(renderToStaticMarkup(<TimingLine timing={{ verdict: "in_time", detail: "In time." }} />)).toContain("ls-ok");
  });
  it("disables the check while it runs", () => {
    expect(note({ lipSync: true, onTiming: () => {}, timingBusy: true })).toMatch(/<button[^>]*disabled[^>]*>Checking…/);
  });
});

describe("does someone on screen sing this", () => {
  const choice = (value: "auto" | "on" | "off", performer: string | null = "Young Sege") => renderToStaticMarkup(<SingChoice performer={performer} value={value} onChange={() => {}} />);

  it("offers the three answers, marks the one in force, and names who is asked about", () => {
    const html = choice("off");
    expect(html).toContain("Does Young Sege sing this on screen?");
    expect(html).toContain("Let PULSEFRAME decide");
    expect(html).toContain("Yes, sync the mouth");
    expect(html).toContain("No: a narrator or voice-over");
    expect(html).toMatch(/aria-pressed="true"[^>]*>No: a narrator/);
    expect(html).toMatch(/aria-pressed="false"[^>]*>Yes, sync/);
    expect(choice("auto", null)).toContain("Does Someone on screen sing this on screen?");
  });

  it("shows up under the lip-sync note of a shot that is being synced, so a wrong guess can be corrected", () => {
    expect(note({ lipSync: true, onSing: () => {} })).toContain("No: a narrator or voice-over");
    expect(note({ keyframeBlocksAudio: true, onSing: () => {} })).toContain("Yes, sync the mouth");
    expect(note({ onSing: () => {} })).toContain("Let PULSEFRAME decide");
    expect(note({ lipSync: true })).not.toContain("narrator or voice-over");                      // no handler, no control
  });

  it("says when a vocal is heard but nobody on screen is treated as singing it, with the way to change that", () => {
    const html = note({ performer: null, vocalHeard: 2.5, onSing: () => {} });
    expect(html).toContain("A vocal is heard under this shot (2.5 s), but nobody on screen is treated as singing it, so no mouth is synced.");
    expect(html).toContain("If it is a narrator, a voice-over or a memory, that is right.");
    expect(html).toContain("Yes, sync the mouth");
    expect(html).not.toContain("Follow the song");                                                // none of the lip-sync mode talk when there is no mouth
  });

  it("remembers that the person said no, in words", () => {
    const html = note({ performer: null, vocalHeard: 2.5, sing: "off", onSing: () => {} });
    expect(html).toContain("You marked this shot as not sung on screen, so no mouth is synced.");
    expect(html).toMatch(/aria-pressed="true"[^>]*>No: a narrator/);
  });
});

