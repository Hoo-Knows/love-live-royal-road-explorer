import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";
import { catalogStore } from "../src/catalog";
import { formatSeconds } from "../src/format";

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
const snowMomentLabel = formatSeconds(snowOccurrence.exactStartSeconds);

function buttonContaining(text: string | RegExp): HTMLButtonElement {
  const element = screen.getByText(text, { exact: typeof text === "string" });
  const button = element.closest("button");
  if (!(button instanceof HTMLButtonElement)) {
    throw new Error(`Expected ${String(text)} to be inside a button.`);
  }
  return button;
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
    expect(screen.queryByText("RR", { exact: true })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Love Live Royal Road Explorer" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Song catalog" })).toBeInTheDocument();
    expect(screen.getByText(/Have you ever wondered how many Love Live songs use Royal Road in them\?/)).toBeInTheDocument();
    expect(screen.getByText("Click on a song to listen to occurrences", { exact: true })).toBeInTheDocument();
    expect(document.querySelector(".hero-diagram")).not.toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Love Live Royal Road Explorer" })).queryByText("IV–V–iii–vi", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText("Love Live harmonic explorer", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText("Local-first analysis archive", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText("A small turn with a long history", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText("Every song stays in frame.", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText(/Zero-match, unavailable, and failed rows remain searchable/, { exact: false })).not.toBeInTheDocument();
    expect(screen.getByText("Snow halation")).toBeInTheDocument();
    expect(screen.getAllByText("No audio").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Needs review").length).toBeGreaterThan(0);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows direct totals without key-confidence controls", () => {
    render(<App />);
    expect(screen.queryByRole("group", { name: "Key confidence" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Catalog totals")).toHaveTextContent(String(snowSong.occurrenceCount));
    expect(buttonContaining("Snow halation")).toHaveTextContent(String(snowSong.occurrenceCount));
  });

  it("ranks matching songs and occurrences with a shared grouping toggle", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "Leaderboard" })).toBeInTheDocument();
    expect(screen.queryByText("Ranked by")).not.toBeInTheDocument();
    expect(screen.queryByText("Who leads the catalog?")).not.toBeInTheDocument();
    expect(screen.queryByText("Across every matching song")).not.toBeInTheDocument();
    expect(screen.queryByText("By artist")).not.toBeInTheDocument();
    expect(screen.queryByText(/\d+ artists?/)).not.toBeInTheDocument();
    expect(screen.queryByText("More categories below")).not.toBeInTheDocument();
    expect(screen.queryByText("Each matching song and all of its occurrences count toward every credited unit or artist.")).not.toBeInTheDocument();
    const statisticsToggle = screen.getByRole("group", { name: "Group statistics by" });
    const artistToggle = within(statisticsToggle).getByRole("button", { name: "Artists" });
    const seriesToggle = within(statisticsToggle).getByRole("button", { name: "Series" });
    expect(artistToggle).toHaveAttribute("aria-pressed", "true");

    const artistSongChart = screen.getByRole("region", {
      name: "Matching songs by artist",
    });
    const artistOccurrenceChart = screen.getByRole("region", {
      name: "Occurrences by artist",
    });
    expect(within(artistSongChart).getByText(snowSong.artistNames[0])).toBeInTheDocument();
    expect(within(artistOccurrenceChart).getByText(snowSong.artistNames[0])).toBeInTheDocument();

    fireEvent.click(seriesToggle);
    expect(seriesToggle).toHaveAttribute("aria-pressed", "true");
    expect(artistToggle).toHaveAttribute("aria-pressed", "false");
    const seriesSongChart = screen.getByRole("region", {
      name: "Matching songs by series",
    });
    expect(within(seriesSongChart).getByText("Love Live!")).toBeInTheDocument();
  });

  it("keeps the selected grouping and refreshes chart data after a catalog update", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Series" }));

    act(() => {
      catalogStore.replace({
        ...fixtureCatalog,
        songs: fixtureCatalog.songs.map((song) => song.id === snowSong.id
          ? { ...song, seriesNames: ["Fresh Series"] }
          : song),
      });
    });

    expect(screen.getByRole("button", { name: "Series" })).toHaveAttribute("aria-pressed", "true");
    const seriesChart = screen.getByRole("region", { name: "Matching songs by series" });
    expect(within(seriesChart).getByText("Fresh Series")).toBeInTheDocument();
    expect(within(seriesChart).queryByText(snowSong.seriesNames[0])).not.toBeInTheDocument();
  });

  it("filters the catalog with artist and series facet toggles", () => {
    render(<App />);

    const filterGroup = screen.getByRole("group", { name: "Filter by" });
    const artistsToggle = within(filterGroup).getByRole("button", { name: "Artists" });
    const allSongsToggle = within(filterGroup).getByRole("button", { name: "All songs" });
    expect(allSongsToggle).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(artistsToggle);
    expect(artistsToggle).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("group", { name: "Filter songs by artists" })).toBeInTheDocument();

    const artistOption = screen.getByRole("button", { name: snowSong.artistNames[0] });
    fireEvent.click(artistOption);
    expect(artistOption).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/filtered to artist:/i)).toBeInTheDocument();
    expect(screen.getByText("Snow halation")).toBeInTheDocument();

    const seriesToggle = within(filterGroup).getByRole("button", { name: "Filter catalog by series" });
    fireEvent.click(seriesToggle);
    expect(screen.getByRole("group", { name: "Filter songs by series" })).toBeInTheDocument();
    const seriesOption = screen.getByRole("button", { name: "Love Live!" });
    fireEvent.click(seriesOption);
    expect(seriesOption).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/filtered to series:/i)).toBeInTheDocument();

    expect(screen.queryByRole("button", { name: "Filter catalog by patterns" })).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Filter songs by patterns" })).not.toBeInTheDocument();
  });

  it("shows only the result count after a search", () => {
    render(<App />);

    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "Snow" },
    });

    const resultsLine = document.querySelector(".results-line");
    expect(resultsLine).toHaveTextContent("1 song");
    expect(resultsLine).not.toHaveTextContent(/matching/i);
  });

  it("switches the interface between English and Japanese", () => {
    render(<App />);

    expect(document.documentElement).toHaveAttribute("lang", "en");
    const japaneseToggle = screen.getByRole("button", { name: "日本語" });
    fireEvent.click(japaneseToggle);

    expect(japaneseToggle).toHaveAttribute("aria-pressed", "true");
    expect(document.documentElement).toHaveAttribute("lang", "ja");
    const pageTitle = screen.getByRole("heading", { name: "ラブライブ！王道進行 エクスプローラー" });
    expect(pageTitle.querySelector("br")).toBeInTheDocument();
    expect(document.title).toBe("ラブライブ！王道進行 エクスプローラー");
    expect(screen.queryByText("ロイヤルロード")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "楽曲カタログ" })).toBeInTheDocument();
    expect(screen.getByText("一致する楽曲")).toBeInTheDocument();
    expect(screen.getByText("スリーズブーケ")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "English" }));
    expect(document.documentElement).toHaveAttribute("lang", "en");
    expect(screen.getByRole("heading", { name: "Song catalog" })).toBeInTheDocument();
    expect(screen.getByText("Cerise Bouquet")).toBeInTheDocument();
  });

  it("shows Japanese song subtitles only in English mode", () => {
    render(<App />);

    expect(screen.getByText("金沢片恋慕", { exact: true })).toHaveClass("song-subtitle");

    fireEvent.click(screen.getByRole("button", { name: "日本語" }));

    expect(screen.getByText("金沢片恋慕", { exact: true })).toHaveClass("song-title");
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

    const chart = screen.getByRole("region", {
      name: "Matching songs by artist",
    });
    expect(chart).toHaveAttribute("tabindex", "0");
    expect(within(chart).getByText("Unit 11")).toBeInTheDocument();
    expect(screen.queryByText("More categories below")).not.toBeInTheDocument();
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

    fireEvent.click(buttonContaining("Snow halation"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("Snow_halation.ogg"),
      expect.objectContaining({ referrerPolicy: "no-referrer", credentials: "omit" }),
    ));
    const audio = document.querySelector("audio");
    expect(audio).toBeInTheDocument();
    const moment = buttonContaining(snowMomentLabel);
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

    fireEvent.click(buttonContaining("Snow halation"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const audio = document.querySelector("audio");
    if (!audio) throw new Error("Expected the expanded song to contain an audio element.");
    fireEvent.loadedMetadata(audio);
    const moment = buttonContaining(snowMomentLabel);
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

    fireEvent.click(buttonContaining("Snow halation"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const audio = document.querySelector("audio");
    if (!audio) throw new Error("Expected the expanded song to contain an audio element.");
    fireEvent.loadedMetadata(audio);

    const firstMoment = buttonContaining(snowMomentLabel);
    const secondMoment = buttonContaining(formatSeconds(snowSong.occurrences[1].exactStartSeconds));
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

    fireEvent.click(buttonContaining("Snow halation"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const audio = document.querySelector("audio");
    if (!audio) throw new Error("Expected the expanded song to contain an audio element.");
    fireEvent.loadedMetadata(audio);
    const selectedButton = buttonContaining(snowMomentLabel);
    const overlappingButton = buttonContaining(formatSeconds(precedingOccurrence.exactStartSeconds));
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

    fireEvent.click(buttonContaining("Snow halation"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const audio = document.querySelector("audio");
    if (!audio) throw new Error("Expected the expanded song to contain an audio element.");
    fireEvent.loadedMetadata(audio);
    const moment = buttonContaining(snowMomentLabel);
    fireEvent.click(moment);
    expect(moment).toHaveClass("occurrence-selected");

    fireEvent.blur(moment);

    expect(moment).not.toHaveClass("occurrence-selected");

    audio.currentTime = snowOccurrence.chordBounds[0].startSeconds + 0.01;
    fireEvent.timeUpdate(audio);
    expect(moment).toHaveClass("occurrence-selected");
    expect(moment.querySelectorAll(".occurrence-chord-active")).toHaveLength(1);
    expect(screen.getByText("Playing song")).toBeInTheDocument();
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

    fireEvent.click(buttonContaining("Snow halation"));
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
    expect(screen.queryByText(/Playback was blocked by the browser/i)).not.toBeInTheDocument();
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

    fireEvent.click(buttonContaining("Snow halation"));
    const passingButton = screen.getByText("passing", { exact: true }).closest("button");
    expect(passingButton).toHaveTextContent("C:maj");
    expect(passingButton).toHaveTextContent("D:7");
    expect(passingButton).toHaveTextContent("F#:dim");
    expect(passingButton).toHaveTextContent("B:min");
    expect(passingButton).toHaveTextContent("E:min");
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

    fireEvent.click(buttonContaining("Snow halation"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const audio = document.querySelector("audio");
    expect(audio).toBeInTheDocument();
    fireEvent.loadedMetadata(audio!);
    fireEvent.click(buttonContaining(snowMomentLabel));
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

    fireEvent.click(buttonContaining("Snow halation"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const audio = document.querySelector("audio");
    if (!audio) throw new Error("Expected the expanded song to contain an audio element.");
    fireEvent.loadedMetadata(audio);
    fireEvent.click(buttonContaining(snowMomentLabel));

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
    fireEvent.click(buttonContaining("Snow halation"));
    expect(await screen.findByText(/in-memory audio request failed/i)).toBeInTheDocument();
    expect(screen.getByText(/Open original wiki audio/i)).toHaveAttribute("href", expect.stringContaining("Snow_halation.ogg"));
  });

  it("keeps only one song expanded at a time and revokes a blob URL on collapse", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, blob: async () => new Blob(["audio"]) });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:fixture");
    const revokeMock = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    render(<App />);
    const snow = buttonContaining("Snow halation");
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

    const search = screen.getByPlaceholderText("Search in Japanese, English, or phonetics…");
    fireEvent.change(search, { target: { value: "Snow" } });
    fireEvent.click(buttonContaining("Title A-Z"));
    const snow = buttonContaining("Snow halation");
    fireEvent.click(snow);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const audio = document.querySelector("audio");
    fireEvent.loadedMetadata(audio!);
    fireEvent.click(buttonContaining(snowMomentLabel));
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
    expect(buttonContaining("Title A-Z")).toHaveClass("sort-active");
    expect(buttonContaining("Snow halation")).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("99")).toBeInTheDocument();
    expect(screen.queryByText(snowMomentLabel, { exact: true })).not.toBeInTheDocument();
    expect(pauseMock.mock.calls.length).toBeGreaterThan(pauseCallsBeforeUpdate);
  });
});
