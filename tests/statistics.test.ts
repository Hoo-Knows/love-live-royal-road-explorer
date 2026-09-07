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
    creators: [],
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
        creators: [
          { id: "creator-1", name: "Creator A", aliases: ["Alias A"] },
          { id: "creator-1", name: "Creator A", aliases: ["Alias A"] },
          { id: "creator-2", name: "Creator B", aliases: [] },
        ],
        occurrenceCount: 3,
      }),
      song({
        id: "match-b",
        artistNames: ["Unit A"],
        seriesNames: ["Series A"],
        creators: [{ id: "creator-1", name: "Creator A", aliases: [] }],
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
    expect(statistics.creators).toEqual(expect.arrayContaining([
      { id: "creator-1", name: "Creator A", matchingSongCount: 2, occurrenceCount: 5 },
      { id: "creator-2", name: "Creator B", matchingSongCount: 1, occurrenceCount: 3 },
    ]));
    expect(statistics.creators).toHaveLength(2);
  });

  it("keeps same-name creators distinct and uses IDs as the final tie-break", () => {
    const statistics = buildCatalogStatistics([
      song({
        id: "one",
        creators: [{ id: "20", name: "Same name", aliases: [] }],
        occurrenceCount: 1,
      }),
      song({
        id: "two",
        creators: [{ id: "10", name: "Same name", aliases: [] }],
        occurrenceCount: 1,
      }),
    ]);

    expect(rankStatistics(statistics.creators, "matchingSongCount").map(({ id }) => id)).toEqual(["10", "20"]);
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
