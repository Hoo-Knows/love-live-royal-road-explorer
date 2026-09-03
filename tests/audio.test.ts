import { describe, expect, it, vi } from "vitest";
import { clampPlaybackEnd, monitorPlayback, stopAudio } from "../src/audio";
import type { CatalogOccurrence } from "../src/types";

const occurrence: CatalogOccurrence = {
  id: "o1",
  exactStartSeconds: 0.2,
  exactEndSeconds: 9.8,
  playbackStartSeconds: 0,
  playbackEndSeconds: 10.3,
  chordLabels: ["C:maj", "D:7", "B:min", "E:min"],
  chordBounds: [
    { startSeconds: 0.2, endSeconds: 2.6 },
    { startSeconds: 2.6, endSeconds: 5.1 },
    { startSeconds: 5.1, endSeconds: 7.4 },
    { startSeconds: 7.4, endSeconds: 9.8 },
  ],
  patternIds: ["iv-v-iii-vi"],
  passingChordIndex: null,
  provenance: "automatic",
};

describe("moment audio helpers", () => {
  it("clamps playback to a known recording duration", () => {
    expect(clampPlaybackEnd(occurrence, 10)).toBe(10);
    expect(clampPlaybackEnd(occurrence, null)).toBe(10.3);
  });

  it("stops and rewinds an existing audio element when switching selections", () => {
    const audio = { pause: vi.fn(), currentTime: 12 } as unknown as HTMLAudioElement;
    stopAudio(audio);
    expect(audio.pause).toHaveBeenCalledOnce();
    expect(audio.currentTime).toBe(0);
  });

  it("formats rounded moment boundaries without rolling 59.96 seconds into 60", async () => {
    const { formatSeconds } = await import("../src/format");
    expect(formatSeconds(59.96)).toBe("1:00.0");
    expect(formatSeconds(0)).toBe("0:00.0");
  });

  it("pauses at the padded end through the animation-frame monitor", () => {
    let frame: FrameRequestCallback | undefined;
    const audio = { currentTime: 4, pause: vi.fn() } as unknown as HTMLAudioElement;
    const scheduler = {
      request: vi.fn((callback: FrameRequestCallback) => {
        frame = callback;
        return 1;
      }),
      cancel: vi.fn(),
    };
    const finished = vi.fn();
    monitorPlayback(audio, 4, finished, scheduler);
    frame?.(0);
    expect(audio.pause).toHaveBeenCalledOnce();
    expect(finished).toHaveBeenCalledOnce();
  });

  it("also stops from a media timeupdate when animation frames are unavailable", () => {
    let timeUpdate: (() => void) | undefined;
    const audio = {
      currentTime: 1,
      pause: vi.fn(),
      addEventListener: vi.fn((_type: string, callback: () => void) => {
        timeUpdate = callback;
      }),
      removeEventListener: vi.fn(),
    } as unknown as HTMLAudioElement;
    const finished = vi.fn();
    const scheduler = {
      request: vi.fn(() => 1),
      cancel: vi.fn(),
    };
    monitorPlayback(audio, 2, finished, scheduler);

    audio.currentTime = 2;
    timeUpdate?.();

    expect(audio.pause).toHaveBeenCalledOnce();
    expect(finished).toHaveBeenCalledOnce();
  });

  it("reports frame-level playback positions for synchronized highlighting", () => {
    let frame: FrameRequestCallback | undefined;
    const audio = { currentTime: 1, pause: vi.fn() } as unknown as HTMLAudioElement;
    const scheduler = {
      request: vi.fn((callback: FrameRequestCallback) => {
        frame = callback;
        return 1;
      }),
      cancel: vi.fn(),
    };
    const positionChanged = vi.fn();
    const cleanup = monitorPlayback(audio, 3, vi.fn(), scheduler, positionChanged);

    expect(positionChanged).toHaveBeenLastCalledWith(1);
    audio.currentTime = 1.25;
    frame?.(0);
    expect(positionChanged).toHaveBeenLastCalledWith(1.25);

    cleanup();
  });
});
