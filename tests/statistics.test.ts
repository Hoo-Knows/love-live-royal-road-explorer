import { describe, expect, it } from "vitest";
import {
  buildCatalogStatistics,
  rankStatistics,
} from "../src/statistics";
import type { CatalogSong } from "../src/types";

function song(overrides: Partial<CatalogSong>): CatalogSong {
  return {
    id: "song",
    titles: { en: "Song" },
    artistNames: ["Unit A"],
    artistAliases: [],
    seriesNames: ["Series A"],
    seriesAliases: [],
    audioUrl: null,
    status: "analyzed",
    durationSeconds: 100,
    error: null,
    occurrenceCount: 0,
    occurrences: [],
    ...overrides,
  };
}

describe("catalog statistics", () => {
  it("counts only matching songs and credits every distinct name on a song", () => {
    const statistics = buildCatalogStatistics([
      song({
        id: "match-a",
        artistNames: ["Unit A", "Unit B", "Unit A"],
        seriesNames: ["Series A", "Series B"],
        occurrenceCount: 3,
      }),
      song({
        id: "match-b",
        artistNames: ["Unit A"],
        seriesNames: ["Series A"],
        occurrenceCount: 2,
      }),
      song({
        id: "zero",
        artistNames: ["Unit C"],
        seriesNames: ["Series C"],
        occurrenceCount: 0,
      }),
    ]);

    expect(statistics.artists).toEqual(expect.arrayContaining([
      { name: "Unit A", matchingSongCount: 2, occurrenceCount: 5 },
      { name: "Unit B", matchingSongCount: 1, occurrenceCount: 3 },
    ]));
    expect(statistics.artists).toHaveLength(2);
    expect(statistics.series).toEqual(expect.arrayContaining([
      { name: "Series A", matchingSongCount: 2, occurrenceCount: 5 },
      { name: "Series B", matchingSongCount: 1, occurrenceCount: 3 },
    ]));
    expect(statistics.series).toHaveLength(2);
  });

  it("ranks each metric independently with normalized names breaking ties", () => {
    const source = [
      { name: "Ｂ unit", matchingSongCount: 2, occurrenceCount: 8 },
      { name: "A unit", matchingSongCount: 2, occurrenceCount: 3 },
      { name: "C unit", matchingSongCount: 1, occurrenceCount: 12 },
    ];

    expect(rankStatistics(source, "matchingSongCount").map(({ name }) => name)).toEqual([
      "A unit",
      "Ｂ unit",
      "C unit",
    ]);
    expect(rankStatistics(source, "occurrenceCount").map(({ name }) => name)).toEqual([
      "C unit",
      "Ｂ unit",
      "A unit",
    ]);
    expect(source.map(({ name }) => name)).toEqual(["Ｂ unit", "A unit", "C unit"]);
  });
});
