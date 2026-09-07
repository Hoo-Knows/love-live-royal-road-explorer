import { act, cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";
import { isPlaybackCue } from "../src/audio";
import { catalogStore } from "../src/catalog";
import type { CatalogOccurrence, CatalogSong } from "../src/types";

const originalCatalog = catalogStore.getSnapshot();
// Playback behavior must remain testable when a refreshed source snapshot
// cannot independently verify this recording.
function cueOccurrence(start: number, id: string): CatalogOccurrence {
  return {
    id,
    exactStartSeconds: start,
    exactEndSeconds: start + 4,
    playbackStartSeconds: start - 0.5,
    playbackEndSeconds: start + 4.5,
    chordLabels: ["F:maj", "G:maj", "E:min", "A:min"],
    chordBounds: Array.from({ length: 4 }, (_, index) => ({
      startSeconds: start + index,
      endSeconds: start + index + 1,
    })),
    patternIds: [originalCatalog.patterns[0].id],
    romanNumeralAnalyses: ["IV → V → iii → vi"],
    passingChordIndex: null,
    provenance: "automatic",
  };
}
const targetOccurrence = cueOccurrence(196.4, "fixture-marked-moment");
const targetSong: CatalogSong = {
  id: "579",
  titles: { ja: "眩耀夜行", en: "Genyou Yakou" },
  artistNames: ["スリーズブーケ"],
  artistAliases: ["Cerise Bouquet"],
  seriesNames: ["蓮ノ空女学院スクールアイドルクラブ"],
  seriesAliases: ["Hasunosora"],
  audioUrl: "https://example.invalid/fixture.ogg",
  status: "analyzed",
  durationSeconds: 240,
  error: null,
  occurrenceCount: 2,
  occurrences: [cueOccurrence(10, "fixture-earlier-moment"), targetOccurrence],
};
const targetSongFixture = targetSong;
const targetOccurrenceFixture = targetOccurrence;

const fixtureCatalog = {
  ...originalCatalog,
  isFixture: true,
  metrics: {
    ...originalCatalog.metrics,
    matchingSongCount: 1,
    totalOccurrenceCount: targetSong.occurrenceCount,
    analyzedSongCount: 1,
    catalogSongCount: 1,
    unavailableSongCount: 0,
    failedSongCount: 0,
  },
  songs: [targetSong],
};

function songButton(): HTMLButtonElement {
  const button = document.querySelector<HTMLButtonElement>(
    `button.song-summary[aria-controls="song-detail-${targetSongFixture.id}"]`,
  );
  if (!button) {
    throw new Error("Expected the playback fixture song button.");
  }
  return button;
}

function momentButton(): HTMLButtonElement {
  const occurrenceIndex = targetSongFixture.occurrences.indexOf(targetOccurrenceFixture);
  const button = document.querySelectorAll<HTMLButtonElement>(".occurrence-button")[occurrenceIndex];
  if (!button) {
    throw new Error("Expected the marked occurrence button.");
  }
  return button;
}

describe("playback accent", () => {
  beforeEach(() => {
    catalogStore.replace(fixtureCatalog);
  });

  afterEach(() => {
    cleanup();
    catalogStore.replace(originalCatalog);
  });

  it("recognizes only the marked song's 3:16.4 moment", () => {
    expect(isPlaybackCue(targetSong, targetOccurrence)).toBe(true);
    expect(isPlaybackCue(targetSong, targetSong.occurrences[0])).toBe(false);
  });

  it("starts the orange transition when the target chord plays and clears the moment on playback handoff", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, blob: async () => new Blob(["audio"]) });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:genyou");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
    render(<App />);

    fireEvent.click(songButton());
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const audio = document.querySelector("audio");
    expect(audio).toBeInTheDocument();
    fireEvent.loadedMetadata(audio!);
    const target = momentButton();
    expect(target).toBeEnabled();

    fireEvent.click(target);
    await act(async () => {
      await Promise.resolve();
    });
    const shell = document.querySelector(".app-shell");
    expect(shell).not.toHaveClass("app-shell-orange-highlights");
    expect(target).toHaveClass("occurrence-selected");

    audio!.currentTime = targetOccurrence.chordBounds[0].startSeconds - 0.01;
    act(() => fireEvent.timeUpdate(audio!));
    expect(shell).not.toHaveClass("app-shell-orange-highlights");

    audio!.currentTime = targetOccurrence.chordBounds[0].startSeconds + 0.01;
    act(() => fireEvent.timeUpdate(audio!));
    expect(shell).toHaveClass("app-shell-orange-highlights");

    act(() => fireEvent.pause(audio!));
    expect(shell).not.toHaveClass("app-shell-orange-highlights");
    expect(target).not.toHaveClass("occurrence-selected");

    fireEvent.click(target);
    await act(async () => {
      await Promise.resolve();
    });
    expect(shell).not.toHaveClass("app-shell-orange-highlights");
    act(() => fireEvent.play(audio!));
    expect(shell).not.toHaveClass("app-shell-orange-highlights");
    expect(target).not.toHaveClass("occurrence-selected");

    fireEvent.click(target);
    await act(async () => {
      await Promise.resolve();
    });
    expect(shell).not.toHaveClass("app-shell-orange-highlights");
    audio!.currentTime = targetOccurrence.playbackStartSeconds + 1;
    act(() => fireEvent.seeking(audio!));
    expect(shell).not.toHaveClass("app-shell-orange-highlights");
    expect(target).not.toHaveClass("occurrence-selected");

    fireEvent.click(target);
    await act(async () => {
      await Promise.resolve();
    });
    expect(shell).not.toHaveClass("app-shell-orange-highlights");
    act(() => fireEvent.click(songButton()));
    expect(shell).not.toHaveClass("app-shell-orange-highlights");
    expect(document.querySelector("audio")).not.toBeInTheDocument();
  });
});
