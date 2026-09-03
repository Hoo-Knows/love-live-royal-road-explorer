import { describe, expect, it } from "vitest";
import {
  facetOptions,
  facetValues,
  filterSongs,
  filterSongsByFacet,
  localizedSeriesNames,
  normalizeSearchText,
  searchLikePattern,
  sortSongs,
  sqlLike,
} from "../src/search";
import type { CatalogSong } from "../src/types";

const song = (overrides: Partial<CatalogSong>): CatalogSong => ({
  id: "default",
  titles: { ja: "既定", en: "Default", phonetic: "きてい" },
  artistNames: ["μ's"],
  artistAliases: [],
  seriesNames: ["ラブライブ！"],
  seriesAliases: [],
  audioUrl: null,
  status: "analyzed",
  durationSeconds: 100,
  error: null,
  occurrenceCount: 0,
  occurrences: [],
  ...overrides,
});

describe("catalog search and sorting", () => {
  it("normalizes compatibility forms and performs Unicode-aware case-insensitive matching", () => {
    expect(normalizeSearchText("ＳＮＯＷ HALATION")).toBe("snow halation");
    const songs = [song({ id: "snow", titles: { ja: "スノー", en: "Snow halation", phonetic: "すのー" } })];
    expect(filterSongs(songs, "HALATION").map(({ id }) => id)).toEqual(["snow"]);
    expect(filterSongs(songs, "すのー").map(({ id }) => id)).toEqual(["snow"]);
  });

  it("searches artist and series names while retaining zero-count rows", () => {
    const songs = [song({ id: "zero", artistNames: ["Aqours"], seriesNames: ["ラブライブ！サンシャイン!!"] })];
    expect(filterSongs(songs, "aqours")).toHaveLength(1);
    expect(filterSongs(songs, "サンシャイン")).toHaveLength(1);
  });

  it("searches English and romanized aliases for credited names", () => {
    const songs = [song({
      id: "cerise",
      artistNames: ["スリーズブーケ"],
      artistAliases: ["Cerise Bouquet"],
    })];

    expect(filterSongs(songs, "cerise").map(({ id }) => id)).toEqual(["cerise"]);
  });

  it("filters by artist or series names, including aliases", () => {
    const songs = [
      song({
        id: "aqours",
        artistNames: ["Aqours"],
        artistAliases: ["Aqours English"],
        seriesNames: ["Love Live! Sunshine!!"],
        seriesAliases: ["Sunshine"],
      }),
      song({
        id: "muse",
        artistNames: ["μ's"],
        seriesNames: ["Love Live!"],
      }),
      song({
        id: "aqours-second-song",
        artistNames: ["Aqours"],
        seriesNames: ["Love Live!"],
      }),
    ];

    expect(facetValues(songs, "artists")).toEqual(["Aqours", "μ's"]);
    expect(facetValues(songs, "artists", "en")).toEqual(["Aqours English", "μ's"]);
    expect(facetOptions(songs, "artists", "en")).toEqual([
      { value: "Aqours", label: "Aqours English" },
      { value: "μ's", label: "μ's" },
    ]);
    expect(facetValues(songs, "series")).toEqual(["Love Live!", "Love Live! Sunshine!!"]);
    expect(filterSongsByFacet(songs, { dimension: "artists", value: "aqours" }).map(({ id }) => id)).toEqual(["aqours", "aqours-second-song"]);
    expect(filterSongsByFacet(songs, { dimension: "series", value: "SUNSHINE" }).map(({ id }) => id)).toEqual(["aqours"]);
    expect(filterSongsByFacet(songs, { dimension: "all", value: null })).toEqual(songs);
  });

  it("uses English series names in English mode when the catalog has no series aliases", () => {
    const songs = [song({ seriesNames: ["ラブライブ！サンシャイン!!"] })];

    expect(localizedSeriesNames(songs[0].seriesNames, songs[0].seriesAliases, "ja")).toEqual(["ラブライブ！サンシャイン!!"]);
    expect(localizedSeriesNames(songs[0].seriesNames, songs[0].seriesAliases, "en")).toEqual(["Love Live! Sunshine!!"]);
    expect(facetValues(songs, "series", "en")).toEqual(["Love Live! Sunshine!!"]);
  });

  it("orders series facets in the requested catalog order", () => {
    const series = [
      "幻日のヨハネ -SUNSHINE in the MIRROR-",
      "イキヅライブ！ LOVELIVE! BLUEBIRD",
      "蓮ノ空女学院スクールアイドルクラブ",
      "スクールアイドルミュージカル",
      "ラブライブ！スーパースター!!",
      "虹ヶ咲学園スクールアイドル同好会",
      "ラブライブ！サンシャイン!!",
      "ラブライブ！",
    ];

    const songs = series.map((seriesName, index) => song({ id: `series-${index}`, seriesNames: [seriesName] }));
    expect(facetValues(songs, "series")).toEqual([
      "ラブライブ！",
      "ラブライブ！サンシャイン!!",
      "虹ヶ咲学園スクールアイドル同好会",
      "ラブライブ！スーパースター!!",
      "スクールアイドルミュージカル",
      "蓮ノ空女学院スクールアイドルクラブ",
      "イキヅライブ！ LOVELIVE! BLUEBIRD",
      "幻日のヨハネ -SUNSHINE in the MIRROR-",
    ]);
  });

  it("uses LIKE wildcards between query words", () => {
    const songs = [song({
      id: "sangenshoku",
      titles: {
        ja: "今、過去、未来の三原色",
        en: "Ima, Kako, Mirai no Sangenshoku",
        phonetic: "いまかこみらいのさんげんしょく",
      },
    })];

    expect(searchLikePattern("ima kako mirai")).toBe("%ima%kako%mirai%");
    expect(filterSongs(songs, "ima kako mirai").map(({ id }) => id)).toEqual(["sangenshoku"]);
  });

  it("supports SQL LIKE percent and single-character wildcards", () => {
    expect(sqlLike("snow halation", "%snow%ation")).toBe(true);
    expect(sqlLike("snow halation", "snow_halation")).toBe(true);
    expect(sqlLike("snow halation", "snow_halatio_")).toBe(true);
    expect(sqlLike("snow halation", "snow_halationx")).toBe(false);
  });

  it("sorts by occurrences descending, then normalized title, with a title mode", () => {
    const songs = [
      song({ id: "b", titles: { ja: "Beta", en: "Beta" }, occurrenceCount: 1 }),
      song({ id: "a", titles: { ja: "Alpha", en: "Alpha" }, occurrenceCount: 1 }),
      song({ id: "zero", titles: { ja: "Zero", en: "Zero" }, occurrenceCount: 0 }),
    ];
    expect(sortSongs(songs, "occurrences").map(({ id }) => id)).toEqual(["a", "b", "zero"]);
    expect(sortSongs(songs, "title").map(({ id }) => id)).toEqual(["a", "b", "zero"]);
  });

  it("sorts title facets in the selected catalog language", () => {
    const songs = [
      song({ id: "japanese-first", titles: { ja: "あ", en: "Z" } }),
      song({ id: "english-first", titles: { ja: "い", en: "A" } }),
    ];

    expect(sortSongs(songs, "title", "ja").map(({ id }) => id)).toEqual(["japanese-first", "english-first"]);
    expect(sortSongs(songs, "title", "en").map(({ id }) => id)).toEqual(["english-first", "japanese-first"]);
  });
});
