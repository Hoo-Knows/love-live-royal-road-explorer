import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";
import { catalogStore } from "../src/catalog";
import type { CatalogSong } from "../src/types";

const originalCatalog = catalogStore.getSnapshot();
const snowSong = originalCatalog.songs.find((song) => song.titles.en === "Snow halation");
if (!snowSong || !snowSong.occurrences.length) {
  throw new Error("The committed catalog must include an analyzed Snow halation fixture.");
}
const unavailableSong = originalCatalog.songs.find((song) => song.status === "unavailable");
const failedSong = originalCatalog.songs.find((song) => song.status === "failed");
if (!unavailableSong || !failedSong) {
  throw new Error("The committed catalog must include unavailable and failed fixtures.");
}
const fixtureSongs = [snowSong, unavailableSong, failedSong];
const fixtureCatalog = {
  ...originalCatalog,
  isFixture: true,
  metrics: {
    matchingSongCount: 1,
    totalOccurrenceCount: snowSong.occurrenceCount,
    analyzedSongCount: 1,
    catalogSongCount: fixtureSongs.length,
    unavailableSongCount: 1,
    failedSongCount: 1,
  },
  songs: fixtureSongs,
};
const snowOccurrence = snowSong.occurrences[0];
function buttonAt(selector: string, index: number, description: string): HTMLButtonElement {
  const button = document.querySelectorAll<HTMLButtonElement>(selector)[index];
  if (!button) {
    throw new Error(`Expected ${description} to match ${selector} at index ${index}.`);
  }
  return button;
}

function songButton(song?: CatalogSong): HTMLButtonElement {
  const selectedSong = song ?? snowSong;
  if (!selectedSong) {
    throw new Error("Expected the fixture song.");
  }
  return buttonAt(
    `button.song-summary[aria-controls="song-detail-${selectedSong.id}"]`,
    0,
    `song ${selectedSong.id}`,
  );
}

function occurrenceButton(index = 0): HTMLButtonElement {
  return buttonAt(".occurrence-button", index, `occurrence ${index}`);
}

function controlButton(selector: string, index: number): HTMLButtonElement {
  return buttonAt(`${selector} button`, index, `control ${selector}`);
}

function statisticsChart(index: number): HTMLElement {
  const chart = document.querySelectorAll<HTMLElement>(".statistics-scroll")[index];
  if (!chart) {
    throw new Error(`Expected statistics chart at index ${index}.`);
  }
  return chart;
}

describe("catalog browser", () => {
  beforeEach(() => {
    catalogStore.replace(fixtureCatalog);
  });

  it("renders every status and does not fetch audio until a row expands", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    expect(document.querySelector("header")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(document.querySelector("#catalog-heading")).toBeInTheDocument();
    expect(document.querySelector(".hero-diagram")).not.toBeInTheDocument();
    expect(songButton()).toBeInTheDocument();
    expect(document.querySelectorAll(".status-unavailable").length).toBeGreaterThan(0);
    expect(document.querySelectorAll(".status-failed").length).toBeGreaterThan(0);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows direct totals without key-confidence controls", () => {
    render(<App />);
    expect(document.querySelectorAll("fieldset")).toHaveLength(4);
    const metrics = document.querySelector(".metrics");
    expect(metrics).toBeInTheDocument();
    expect(metrics?.querySelectorAll(".metric")).toHaveLength(6);
    expect(metrics?.querySelectorAll(".metric strong")[1]).toHaveTextContent(String(snowSong.occurrenceCount));
    expect(songButton().querySelector(".song-count strong")).toHaveTextContent(String(snowSong.occurrenceCount));
  });

  it("ranks matching songs and occurrences with a shared grouping toggle", () => {
    render(<App />);

    expect(document.querySelector("#statistics-heading")).toBeInTheDocument();
    const artistToggle = controlButton(".statistics-toggle", 0);
    const seriesToggle = controlButton(".statistics-toggle", 1);
    expect(artistToggle).toHaveAttribute("aria-pressed", "true");

    const artistSongChart = statisticsChart(0);
    const artistOccurrenceChart = statisticsChart(1);
    expect(within(artistSongChart).getByText(snowSong.artistNames[0])).toBeInTheDocument();
    expect(within(artistOccurrenceChart).getByText(snowSong.artistNames[0])).toBeInTheDocument();

    fireEvent.click(seriesToggle);
    expect(seriesToggle).toHaveAttribute("aria-pressed", "true");
    expect(artistToggle).toHaveAttribute("aria-pressed", "false");
    const seriesSongChart = statisticsChart(0);
    expect(within(seriesSongChart).getByText("Love Live!")).toBeInTheDocument();
  });

  it("keeps the selected grouping and refreshes chart data after a catalog update", () => {
    render(<App />);
    fireEvent.click(controlButton(".statistics-toggle", 1));

    act(() => {
      catalogStore.replace({
        ...fixtureCatalog,
        songs: fixtureCatalog.songs.map((song) => song.id === snowSong.id
          ? { ...song, seriesNames: ["Fresh Series"] }
          : song),
      });
    });

    expect(controlButton(".statistics-toggle", 1)).toHaveAttribute("aria-pressed", "true");
    const seriesChart = statisticsChart(0);
    expect(within(seriesChart).getByText("Fresh Series")).toBeInTheDocument();
    expect(within(seriesChart).queryByText(snowSong.seriesNames[0])).not.toBeInTheDocument();
  });

  it("filters the catalog with artist and series facet toggles", () => {
    render(<App />);

    const filterGroup = document.querySelector<HTMLElement>("fieldset.filter-control");
    if (!filterGroup) throw new Error("Expected the catalog filter controls.");
    const artistsToggle = controlButton(".filter-control", 1);
    const allSongsToggle = controlButton(".filter-control", 0);
    expect(allSongsToggle).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(artistsToggle);
    expect(artistsToggle).toHaveAttribute("aria-pressed", "true");
    expect(document.querySelector("fieldset.filter-options")).toBeInTheDocument();

    const artistOption = screen.getByRole("button", { name: snowSong.artistNames[0] });
    fireEvent.click(artistOption);
    expect(artistOption).toHaveAttribute("aria-pressed", "true");
    expect(songButton()).toBeInTheDocument();

    const seriesToggle = controlButton(".filter-control", 2);
    fireEvent.click(seriesToggle);
    expect(document.querySelector("fieldset.filter-options")).toBeInTheDocument();
    const seriesOption = screen.getByRole("button", { name: "Love Live!" });
    fireEvent.click(seriesOption);
    expect(seriesOption).toHaveAttribute("aria-pressed", "true");

    expect(filterGroup.querySelectorAll("button")).toHaveLength(3);
  });

  it("shows only the result count after a search", () => {
    render(<App />);

    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "Snow" },
    });

    const resultsLine = document.querySelector<HTMLElement>(".results-line");
    if (!resultsLine) throw new Error("Expected the catalog results summary.");
    expect(resultsLine.querySelector("strong")).toHaveTextContent("1");
  });

  it("switches the interface between English and Japanese", () => {
    render(<App />);

    expect(document.documentElement).toHaveAttribute("lang", "en");
    const japaneseToggle = controlButton(".language-toggle", 1);
    fireEvent.click(japaneseToggle);

    expect(japaneseToggle).toHaveAttribute("aria-pressed", "true");
    expect(document.documentElement).toHaveAttribute("lang", "ja");
    const pageTitle = screen.getByRole("heading", { level: 1 });
    expect(pageTitle.querySelector("br")).toBeInTheDocument();
    expect(document.title).toBe(
      Array.from(pageTitle.childNodes).map((node) => node.textContent ?? "").join(" ").replace(/\s+/g, " ").trim(),
    );
    expect(document.querySelector("#catalog-heading")).toBeInTheDocument();
    expect(screen.getByText(failedSong.artistNames[0])).toBeInTheDocument();

    fireEvent.click(controlButton(".language-toggle", 0));
    expect(document.documentElement).toHaveAttribute("lang", "en");
    expect(document.querySelector("#catalog-heading")).toBeInTheDocument();
    expect(screen.getByText(failedSong.artistAliases[0])).toBeInTheDocument();
  });

  it("shows Japanese song subtitles only in English mode", () => {
    render(<App />);

    const japaneseTitle = failedSong.titles.ja;
    if (!japaneseTitle) throw new Error("Expected the fixture song to have a Japanese title.");
    expect(songButton(failedSong).querySelector(".song-subtitle")).toHaveTextContent(japaneseTitle);

    fireEvent.click(controlButton(".language-toggle", 1));

    expect(songButton(failedSong).querySelector(".song-title")).toHaveTextContent(japaneseTitle);
    expect(document.querySelector(".song-subtitle")).not.toBeInTheDocument();
  });

  it("makes long rankings keyboard-scrollable without hiding later entries", () => {
    const rankedSongs = Array.from({ length: 11 }, (_, index) => ({
      ...snowSong,
      id: `ranked-${index}`,
      titles: { en: `Ranked song ${index + 1}` },
      artistNames: [`Unit ${index + 1}`],
    }));
    catalogStore.replace({ ...fixtureCatalog, songs: rankedSongs });

    render(<App />);

    const chart = statisticsChart(0);
    expect(chart).toHaveAttribute("tabindex", "0");
    expect(within(chart).getByText("Unit 11")).toBeInTheDocument();
  });

  it("loads an expanded song with a no-referrer blob request and enables moments after metadata", async () => {
    const blob = new Blob(["fixture audio"], { type: "audio/ogg" });
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, blob: async () => blob });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:fixture");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
    render(<App />);

    fireEvent.click(songButton());
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("Snow_halation.ogg"),
      expect.objectContaining({ referrerPolicy: "no-referrer", credentials: "omit" }),
    ));
    const audio = document.querySelector("audio");
    expect(audio).toBeInTheDocument();
    const moment = occurrenceButton();
    expect(moment).toBeDisabled();
    fireEvent.loadedMetadata(audio!);
    expect(moment).toBeEnabled();
    const romanAnalysis = snowOccurrence.romanNumeralAnalyses?.[0];
    if (!romanAnalysis) throw new Error("Expected the fixture occurrence to include a Roman-numeral analysis.");
    expect(moment).toHaveTextContent(romanAnalysis);
    expect(moment.querySelector(".occurrence-analysis")).not.toBeInTheDocument();
    fireEvent.click(moment);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
  });

  it("highlights the chord whose detector segment contains the playback position", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, blob: async () => new Blob(["audio"]) });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:fixture");
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    let playbackFrame: FrameRequestCallback | undefined;
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      playbackFrame = callback;
      return 1;
    });
    render(<App />);

    fireEvent.click(songButton());
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const audio = document.querySelector("audio");
    if (!audio) throw new Error("Expected the expanded song to contain an audio element.");
    fireEvent.loadedMetadata(audio);
    const moment = occurrenceButton();
    fireEvent.click(moment);
    await act(async () => {
      await Promise.resolve();
    });

    const chordElements = Array.from(moment.querySelectorAll(".occurrence-chord"));
    expect(chordElements).toHaveLength(snowOccurrence.chordLabels.length);
    audio.currentTime = snowOccurrence.chordBounds[1].startSeconds + 0.01;
    act(() => playbackFrame?.(0));

    expect(chordElements[0]).not.toHaveClass("occurrence-chord-active");
    expect(chordElements[1]).toHaveClass("occurrence-chord-active");
  });

  it("highlights the current occurrence and chord during ordinary song playback", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, blob: async () => new Blob(["audio"]) });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:fixture");
    render(<App />);

    fireEvent.click(songButton());
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const audio = document.querySelector("audio");
    if (!audio) throw new Error("Expected the expanded song to contain an audio element.");
    fireEvent.loadedMetadata(audio);

    const firstMoment = occurrenceButton();
    const secondMoment = occurrenceButton(1);
    audio.currentTime = snowOccurrence.chordBounds[0].startSeconds + 0.01;
    fireEvent.play(audio);

    expect(firstMoment).toHaveClass("occurrence-selected");
    expect(firstMoment.querySelectorAll(".occurrence-chord-active")).toHaveLength(1);
    expect(secondMoment).not.toHaveClass("occurrence-selected");

    audio.currentTime = snowOccurrence.chordBounds[1].startSeconds + 0.01;
    fireEvent.timeUpdate(audio);
    const firstChords = Array.from(firstMoment.querySelectorAll(".occurrence-chord"));
    expect(firstChords[0]).not.toHaveClass("occurrence-chord-active");
    expect(firstChords[1]).toHaveClass("occurrence-chord-active");

    audio.currentTime = snowSong.occurrences[1].chordBounds[0].startSeconds + 0.01;
    fireEvent.timeUpdate(audio);
    expect(firstMoment).not.toHaveClass("occurrence-selected");
    expect(secondMoment).toHaveClass("occurrence-selected");
    expect(secondMoment.querySelectorAll(".occurrence-chord-active")).toHaveLength(1);

    fireEvent.pause(audio);
    expect(secondMoment).not.toHaveClass("occurrence-selected");
    expect(secondMoment.querySelectorAll(".occurrence-chord-active")).toHaveLength(0);
  });

  it("only highlights chords in the selected occurrence and clears the selection when playback ends", async () => {
    const precedingOccurrence = {
      ...snowOccurrence,
      id: "overlapping-fixture",
      exactStartSeconds: snowOccurrence.exactStartSeconds - 2,
      exactEndSeconds: snowOccurrence.exactEndSeconds + 2,
      playbackStartSeconds: snowOccurrence.exactStartSeconds - 2.5,
      playbackEndSeconds: snowOccurrence.exactEndSeconds + 2.5,
      chordBounds: [
        { startSeconds: snowOccurrence.exactStartSeconds - 2, endSeconds: snowOccurrence.chordBounds[0].startSeconds },
        { startSeconds: snowOccurrence.chordBounds[0].startSeconds, endSeconds: snowOccurrence.chordBounds[1].startSeconds },
        { startSeconds: snowOccurrence.chordBounds[1].startSeconds, endSeconds: snowOccurrence.chordBounds[2].startSeconds },
        { startSeconds: snowOccurrence.chordBounds[2].startSeconds, endSeconds: snowOccurrence.exactEndSeconds + 2 },
      ],
    };
    const overlappingSong = {
      ...snowSong,
      occurrenceCount: snowSong.occurrenceCount + 1,
      occurrences: [precedingOccurrence, ...snowSong.occurrences],
    };
    catalogStore.replace({
      ...fixtureCatalog,
      metrics: { ...fixtureCatalog.metrics, totalOccurrenceCount: overlappingSong.occurrenceCount },
      songs: [overlappingSong, unavailableSong, failedSong],
    });
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, blob: async () => new Blob(["audio"]) });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:fixture");
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    render(<App />);

    fireEvent.click(songButton());
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const audio = document.querySelector("audio");
    if (!audio) throw new Error("Expected the expanded song to contain an audio element.");
    fireEvent.loadedMetadata(audio);
    const overlappingButton = occurrenceButton();
    const selectedButton = occurrenceButton(1);
    fireEvent.click(selectedButton);
    audio.currentTime = snowOccurrence.chordBounds[1].startSeconds + 0.01;
    act(() => fireEvent.timeUpdate(audio));

    expect(selectedButton).toHaveClass("occurrence-selected");
    expect(selectedButton.querySelectorAll(".occurrence-chord-active")).toHaveLength(1);
    expect(overlappingButton.querySelectorAll(".occurrence-chord-active")).toHaveLength(0);

    act(() => fireEvent.ended(audio));
    expect(selectedButton).not.toHaveClass("occurrence-selected");
    expect(selectedButton.querySelectorAll(".occurrence-chord-active")).toHaveLength(0);
  });

  it("clears a selected moment when focus leaves its control", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, blob: async () => new Blob(["audio"]) });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:fixture");
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    render(<App />);

    fireEvent.click(songButton());
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const audio = document.querySelector("audio");
    if (!audio) throw new Error("Expected the expanded song to contain an audio element.");
    fireEvent.loadedMetadata(audio);
    const moment = occurrenceButton();
    fireEvent.click(moment);
    expect(moment).toHaveClass("occurrence-selected");

    fireEvent.blur(moment);

    expect(moment).not.toHaveClass("occurrence-selected");

    audio.currentTime = snowOccurrence.chordBounds[0].startSeconds + 0.01;
    fireEvent.timeUpdate(audio);
    expect(moment).toHaveClass("occurrence-selected");
    expect(moment.querySelectorAll(".occurrence-chord-active")).toHaveLength(1);
    expect(document.querySelector(".pulse-dot")).toHaveClass("pulse-live");
  });

  it("ignores a rejected play promise from a previous moment", async () => {
    let rejectFirst: (() => void) | undefined;
    const firstPlay = new Promise<void>((_resolve, reject) => {
      rejectFirst = reject;
    });
    const secondPlay = new Promise<void>(() => undefined);
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, blob: async () => new Blob(["audio"]) });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:fixture");
    vi.spyOn(HTMLMediaElement.prototype, "play")
      .mockImplementationOnce(() => firstPlay)
      .mockImplementationOnce(() => secondPlay);
    render(<App />);

    fireEvent.click(songButton());
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const audio = document.querySelector("audio");
    if (!audio) throw new Error("Expected the expanded song to contain an audio element.");
    fireEvent.loadedMetadata(audio);
    const moments = Array.from(document.querySelectorAll<HTMLButtonElement>(".occurrence-button"));
    expect(moments.length).toBeGreaterThan(1);
    fireEvent.click(moments[0]);
    fireEvent.click(moments[1]);

    await act(async () => {
      rejectFirst?.();
      await Promise.resolve();
    });

    expect(moments[1]).toHaveClass("occurrence-selected");
    expect(document.querySelector(".audio-message")).not.toBeInTheDocument();
  });

  it("renders all five chord labels and identifies the passing chord", () => {
    const passingOccurrence = {
      ...snowOccurrence,
      id: "passing-fixture",
      chordLabels: ["C:maj", "D:7", "F#:dim", "B:min", "E:min"],
      patternIds: ["iv-v-iii-vi"],
      passingChordIndex: 2,
    };
    const passingSong = {
      ...snowSong,
      occurrenceCount: snowSong.occurrenceCount + 1,
      occurrences: [...snowSong.occurrences, passingOccurrence],
    };
    catalogStore.replace({
      ...fixtureCatalog,
      metrics: { ...fixtureCatalog.metrics, totalOccurrenceCount: passingSong.occurrenceCount },
      songs: [passingSong, unavailableSong, failedSong],
    });
    render(<App />);

    fireEvent.click(songButton());
    const passingButton = occurrenceButton(snowSong.occurrences.length);
    const chordLabels = Array.from(passingButton.querySelectorAll(".occurrence-chord")).map((chord) => chord.textContent);
    expect(chordLabels).toEqual(["C:maj", "D:7", "F#:dim", "B:min", "E:min"]);
  });

  it("stops the moment listener when native controls take over", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, blob: async () => new Blob(["audio"]) });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:fixture");
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    const pauseMock = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
    let monitoredFrame: FrameRequestCallback | undefined;
    const requestFrameMock = vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      monitoredFrame = callback;
      return 1;
    });
    const cancelFrameMock = vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => undefined);
    render(<App />);

    fireEvent.click(songButton());
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const audio = document.querySelector("audio");
    expect(audio).toBeInTheDocument();
    fireEvent.loadedMetadata(audio!);
    fireEvent.click(occurrenceButton());
    await act(async () => {
      await Promise.resolve();
    });

    expect(requestFrameMock).toHaveBeenCalledOnce();
    pauseMock.mockClear();
    fireEvent.pause(audio!);
    expect(cancelFrameMock).toHaveBeenCalledOnce();

    fireEvent.play(audio!);
    expect(requestFrameMock).toHaveBeenCalledTimes(2);
    audio!.currentTime = snowOccurrence.playbackEndSeconds + 1;
    monitoredFrame?.(0);
    expect(pauseMock).not.toHaveBeenCalled();
  });

  it("keeps the moment boundary active when the browser rounds a programmatic seek", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, blob: async () => new Blob(["audio"]) });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:fixture");
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    const pauseMock = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
    let monitoredFrame: FrameRequestCallback | undefined;
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      monitoredFrame = callback;
      return 1;
    });
    render(<App />);

    fireEvent.click(songButton());
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const audio = document.querySelector("audio");
    if (!audio) throw new Error("Expected the expanded song to contain an audio element.");
    fireEvent.loadedMetadata(audio);
    fireEvent.click(occurrenceButton());

    audio.currentTime = snowOccurrence.playbackStartSeconds + 0.01;
    fireEvent.seeking(audio);
    fireEvent.play(audio);
    pauseMock.mockClear();

    audio.currentTime = snowOccurrence.playbackEndSeconds + 0.01;
    act(() => monitoredFrame?.(0));

    expect(pauseMock).toHaveBeenCalledOnce();
    expect(audio.currentTime).toBe(snowOccurrence.playbackEndSeconds);
  });

  it("falls back to the direct wiki URL with a clear message when blob fetch fails", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error("CORS blocked"));
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    fireEvent.click(songButton());
    const audioStatus = await screen.findByRole("status");
    expect(audioStatus).toBeInTheDocument();
    expect(within(audioStatus).getByRole("link")).toHaveAttribute("href", expect.stringContaining("Snow_halation.ogg"));
  });

  it("keeps only one song expanded at a time and revokes a blob URL on collapse", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, blob: async () => new Blob(["audio"]) });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:fixture");
    const revokeMock = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    render(<App />);
    const snow = songButton();
    fireEvent.click(snow);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    fireEvent.click(snow);
    expect(document.querySelector("audio")).not.toBeInTheDocument();
    expect(revokeMock).toHaveBeenCalledWith("blob:fixture");
  });

  it("applies live catalog updates without resetting the current view", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, blob: async () => new Blob(["audio"]) });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:fixture");
    const pauseMock = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    render(<App />);

    const search = screen.getByRole("searchbox");
    fireEvent.change(search, { target: { value: "Snow" } });
    fireEvent.click(controlButton(".sort-control", 1));
    const snow = songButton();
    fireEvent.click(snow);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const audio = document.querySelector("audio");
    fireEvent.loadedMetadata(audio!);
    fireEvent.click(occurrenceButton());
    const pauseCallsBeforeUpdate = pauseMock.mock.calls.length;

    const updatedSongs = fixtureCatalog.songs.map((song) => song.id === snowSong.id
      ? {
          ...song,
          occurrenceCount: 0,
          occurrences: [],
        }
      : song);
    act(() => {
      catalogStore.replace({
        ...fixtureCatalog,
        metrics: { ...fixtureCatalog.metrics, matchingSongCount: 0, totalOccurrenceCount: 99 },
        songs: updatedSongs,
      });
    });

    expect(search).toHaveValue("Snow");
    expect(controlButton(".sort-control", 1)).toHaveClass("sort-active");
    expect(songButton()).toHaveAttribute("aria-expanded", "true");
    expect(document.querySelectorAll(".metrics .metric strong")[1]).toHaveTextContent("99");
    expect(document.querySelector(".occurrence-list")).not.toBeInTheDocument();
    expect(pauseMock.mock.calls.length).toBeGreaterThan(pauseCallsBeforeUpdate);
  });
});
