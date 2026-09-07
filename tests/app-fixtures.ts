import type { Catalog, CatalogOccurrence, CatalogSong } from "../src/types";

const progressionPatternId = "iv-v-iii-vi";

function fixtureOccurrence(id: string, startSeconds: number): CatalogOccurrence {
  return {
    id,
    exactStartSeconds: startSeconds,
    exactEndSeconds: startSeconds + 4,
    playbackStartSeconds: startSeconds - 0.5,
    playbackEndSeconds: startSeconds + 4.5,
    chordLabels: ["C:maj", "D:maj", "B:min", "E:min"],
    chordBounds: Array.from({ length: 4 }, (_, index) => ({
      startSeconds: startSeconds + index,
      endSeconds: startSeconds + index + 1,
    })),
    patternIds: [progressionPatternId],
    romanNumeralAnalyses: ["IV -> V -> iii -> vi"],
    passingChordIndex: null,
    provenance: "automatic",
  };
}

export const snowSong: CatalogSong = {
  id: "snow-fixture",
  titles: { ja: "Snow halation JP", en: "Snow halation", phonetic: "snow halation phonetic" },
  artistNames: ["Muse"],
  artistAliases: ["Muse English"],
  seriesNames: ["Love Live! JP"],
  seriesAliases: ["Love Live!"],
  creators: [{ id: "creator-snow", name: "Snow Creator", aliases: ["Snow Creator Alias"] }],
  audioUrl: "https://static.wikia.nocookie.net/love-live/images/3/35/Snow_halation.ogg",
  status: "analyzed",
  durationSeconds: 240,
  error: null,
  occurrenceCount: 2,
  occurrences: [fixtureOccurrence("snow-fixture-1", 10), fixtureOccurrence("snow-fixture-2", 30)],
};

export const unavailableSong: CatalogSong = {
  id: "unavailable-fixture",
  titles: { ja: "Unavailable fixture JP", en: "Unavailable fixture" },
  artistNames: ["Fixture Unit"],
  artistAliases: ["Fixture Unit"],
  seriesNames: ["Fixture Series"],
  seriesAliases: ["Fixture Series"],
  creators: [],
  audioUrl: null,
  status: "unavailable",
  durationSeconds: null,
  error: "No fixture audio URL.",
  occurrenceCount: 0,
  occurrences: [],
};

export const failedSong: CatalogSong = {
  id: "failed-fixture",
  titles: { ja: "Failed fixture JP", en: "Failed fixture" },
  artistNames: ["Failed Unit"],
  artistAliases: ["Failed Unit"],
  seriesNames: ["Failed Series"],
  seriesAliases: ["Failed Series"],
  creators: [],
  audioUrl: "https://example.invalid/failed-fixture.ogg",
  status: "failed",
  durationSeconds: null,
  error: "Fixture analysis failure.",
  occurrenceCount: 0,
  occurrences: [],
};

export const fixtureCatalog: Catalog = {
  schemaVersion: "4.2.0",
  isFixture: true,
  patterns: [
    { id: progressionPatternId, label: "IV -> V -> iii -> vi" },
    { id: "iv-v-iii-substitution-vi", label: "IV -> V -> III -> vi" },
  ],
  metrics: {
    matchingSongCount: 1,
    totalOccurrenceCount: snowSong.occurrenceCount,
    analyzedSongCount: 1,
    catalogSongCount: 3,
    unavailableSongCount: 1,
    failedSongCount: 1,
  },
  songs: [snowSong, unavailableSong, failedSong],
};

export const snowOccurrence = snowSong.occurrences[0];
