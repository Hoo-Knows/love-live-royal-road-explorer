import type { CatalogSong } from "./types";
import type { Language } from "./i18n";

export type CatalogFilterDimension = "all" | "artists" | "series";

export interface CatalogFacetFilter {
  dimension: CatalogFilterDimension;
  value: string | null;
}

export interface CatalogFacetOption {
  /** The canonical Japanese name, used as a stable filter value across language changes. */
  value: string;
  /** The name shown in the current language. */
  label: string;
}

/** NFKC keeps compatibility forms searchable while preserving Japanese text. */
export function normalizeSearchText(value: string): string {
  return value.normalize("NFKC").toLowerCase();
}

/** Build a LIKE pattern that allows punctuation or other text between words. */
export function searchLikePattern(query: string): string {
  const normalizedQuery = normalizeSearchText(query.trim());
  return `%${normalizedQuery.replace(/\s+/gu, "%")}%`;
}

/** Match normalized text using SQL LIKE's '%' and '_' wildcards. */
export function sqlLike(value: string, pattern: string): boolean {
  const valueCharacters = Array.from(value);
  const patternCharacters = Array.from(pattern);
  let valueIndex = 0;
  let patternIndex = 0;
  let percentIndex = -1;
  let percentValueIndex = -1;

  while (valueIndex < valueCharacters.length) {
    const patternCharacter = patternCharacters[patternIndex];
    if (
      patternCharacter === "_" ||
      patternCharacter === valueCharacters[valueIndex]
    ) {
      valueIndex += 1;
      patternIndex += 1;
    } else if (patternCharacter === "%") {
      percentIndex = patternIndex;
      percentValueIndex = valueIndex;
      patternIndex += 1;
    } else if (percentIndex !== -1) {
      patternIndex = percentIndex + 1;
      percentValueIndex += 1;
      valueIndex = percentValueIndex;
    } else {
      return false;
    }
  }

  while (patternCharacters[patternIndex] === "%") patternIndex += 1;
  return patternIndex === patternCharacters.length;
}

// Keep series facets in the catalog's chronology instead of locale order.
const seriesSortGroups = [
  { japanese: "ラブライブ！", english: "Love Live!", aliases: ["love live"] },
  { japanese: "ラブライブ！サンシャイン!!", english: "Love Live! Sunshine!!", aliases: ["love live sunshine", "sunshine"] },
  { japanese: "虹ヶ咲学園スクールアイドル同好会", english: "Love Live! Nijigasaki High School Idol Club", aliases: ["niji", "nijigasaki"] },
  { japanese: "ラブライブ！スーパースター!!", english: "Love Live! Superstar!!", aliases: ["love live superstar", "superstar"] },
  { japanese: "スクールアイドルミュージカル", english: "School Idol Musical", aliases: ["school idol musical", "musical"] },
  { japanese: "蓮ノ空女学院スクールアイドルクラブ", english: "Love Live! Hasunosora Girls' High School Idol Club", aliases: ["hasu", "hasunosora"] },
  { japanese: "イキヅライブ！ LOVELIVE! BLUEBIRD", english: "Ikizulive! LOVELIVE! BLUEBIRD", aliases: ["ikizulive! lovelive! bluebird", "bluebird"] },
  { japanese: "幻日のヨハネ -SUNSHINE in the MIRROR-", english: "Yohane the Parhelion -SUNSHINE in the MIRROR-", aliases: ["yohane", "yohane the parhelion"] },
] as const;
const seriesEnglishNames = new Map(
  seriesSortGroups.map(({ japanese, english }) => [normalizeSearchText(japanese), english] as const),
);

function englishSeriesName(name: string | undefined): string | undefined {
  const normalizedName = name?.trim();
  return normalizedName ? seriesEnglishNames.get(normalizeSearchText(normalizedName)) : undefined;
}

export function songSearchValues(song: CatalogSong): string[] {
  return [
    song.titles.ja,
    song.titles.en,
    song.titles.phonetic,
    ...song.artistNames,
    ...(song.artistAliases ?? []),
    ...song.seriesNames.flatMap((name) => [name, englishSeriesName(name)]),
    ...(song.seriesAliases ?? []),
  ].filter((value): value is string => Boolean(value));
}

export function songMatchesQuery(song: CatalogSong, query: string): boolean {
  const likePattern = searchLikePattern(query);
  if (likePattern === "%%") return true;

  return songSearchValues(song).some((value) =>
    sqlLike(normalizeSearchText(value), likePattern),
  );
}

export function filterSongs(songs: CatalogSong[], query: string): CatalogSong[] {
  return songs.filter((song) => songMatchesQuery(song, query));
}

interface FacetEntry {
  ja: string | undefined;
  en: string | undefined;
}

function facetEntries(song: CatalogSong, dimension: Exclude<CatalogFilterDimension, "all">): FacetEntry[] {
  const names = dimension === "artists" ? song.artistNames : song.seriesNames;
  const aliases = dimension === "artists" ? song.artistAliases : song.seriesAliases;
  const entryCount = Math.max(names.length, aliases?.length ?? 0);

  return Array.from({ length: entryCount }, (_, index) => {
    const ja = names[index]?.trim() || undefined;
    return {
      ja,
      en: aliases?.[index]?.trim() || (dimension === "series" ? englishSeriesName(ja) : undefined),
    };
  }).filter((entry) => Boolean(entry.ja || entry.en));
}

export function localizedNames(
  names: string[],
  aliases: string[] | undefined,
  language: Language,
): string[] {
  const values: string[] = [];
  const seen = new Set<string>();
  const entryCount = Math.max(names.length, aliases?.length ?? 0);

  for (let index = 0; index < entryCount; index += 1) {
    const ja = names[index]?.trim();
    const en = aliases?.[index]?.trim();
    const value = language === "en" ? en || ja : ja || en;
    if (!value) continue;
    const key = normalizeSearchText(value);
    if (seen.has(key)) continue;
    seen.add(key);
    values.push(value);
  }

  return values;
}

export function localizedSeriesNames(
  names: string[],
  aliases: string[] | undefined,
  language: Language,
): string[] {
  const values: string[] = [];
  const seen = new Set<string>();
  const entryCount = Math.max(names.length, aliases?.length ?? 0);

  for (let index = 0; index < entryCount; index += 1) {
    const ja = names[index]?.trim();
    const en = aliases?.[index]?.trim() || englishSeriesName(ja);
    const value = language === "en" ? en || ja : ja || en;
    if (!value) continue;
    const key = normalizeSearchText(value);
    if (seen.has(key)) continue;
    seen.add(key);
    values.push(value);
  }

  return values;
}

function facetSearchValues(song: CatalogSong, dimension: Exclude<CatalogFilterDimension, "all">): string[] {
  return facetEntries(song, dimension).flatMap((entry) => [entry.ja, entry.en])
    .filter((value): value is string => Boolean(value));
}

export function songMatchesFacet(song: CatalogSong, filter: CatalogFacetFilter): boolean {
  if (filter.dimension === "all" || !filter.value?.trim()) return true;

  const target = normalizeSearchText(filter.value.trim());
  return facetSearchValues(song, filter.dimension).some((value) => normalizeSearchText(value.trim()) === target);
}

export function filterSongsByFacet(songs: CatalogSong[], filter: CatalogFacetFilter): CatalogSong[] {
  return songs.filter((song) => songMatchesFacet(song, filter));
}

const titleCollator = new Intl.Collator(undefined, {
  sensitivity: "base",
  numeric: true,
  usage: "sort",
});

const seriesSortIndex = new Map(
  seriesSortGroups.flatMap((group, index) => [group.japanese, group.english, ...group.aliases]
    .map((value) => [normalizeSearchText(value), index] as const)),
);

interface FacetAccumulator {
  value: string;
  labels: { ja?: string; en?: string };
  songIds: Set<string>;
}

export function facetOptions(
  songs: CatalogSong[],
  dimension: Exclude<CatalogFilterDimension, "all">,
  language: Language = "ja",
): CatalogFacetOption[] {
  const options = new Set<FacetAccumulator>();
  const valueKeys = new Map<string, FacetAccumulator>();

  for (const song of songs) {
    for (const entry of facetEntries(song, dimension)) {
      const entryKeys = [entry.ja, entry.en]
        .filter((value): value is string => Boolean(value))
        .map(normalizeSearchText);
      const existing = entryKeys.map((key) => valueKeys.get(key)).find(Boolean);
      const option = existing ?? {
        value: entry.ja ?? entry.en ?? "",
        labels: {},
        songIds: new Set<string>(),
      };
      if (!existing) options.add(option);
      option.labels.ja ??= entry.ja;
      option.labels.en ??= entry.en;
      option.songIds.add(song.id);

      for (const key of entryKeys) {
        valueKeys.set(key, option);
      }
    }
  }

  return [...options]
    .sort((left, right) => {
      if (dimension === "artists") {
        const songCountDifference = right.songIds.size - left.songIds.size;
        if (songCountDifference !== 0) return songCountDifference;
      }

      if (dimension === "series") {
        const leftLabel = left.labels[language] ?? left.labels.ja ?? left.labels.en ?? left.value;
        const rightLabel = right.labels[language] ?? right.labels.ja ?? right.labels.en ?? right.value;
        const leftOrder = seriesSortIndex.get(normalizeSearchText(leftLabel)) ?? seriesSortGroups.length;
        const rightOrder = seriesSortIndex.get(normalizeSearchText(rightLabel)) ?? seriesSortGroups.length;
        if (leftOrder !== rightOrder) return leftOrder - rightOrder;
      }

      const leftLabel = left.labels[language] ?? left.labels.ja ?? left.labels.en ?? left.value;
      const rightLabel = right.labels[language] ?? right.labels.ja ?? right.labels.en ?? right.value;
      return titleCollator.compare(leftLabel, rightLabel);
    })
    .map((option) => ({
      value: option.value,
      label: option.labels[language] ?? option.labels.ja ?? option.labels.en ?? option.value,
    }));
}

export function facetValues(
  songs: CatalogSong[],
  dimension: Exclude<CatalogFilterDimension, "all">,
  language: Language = "ja",
): string[] {
  return facetOptions(songs, dimension, language).map(({ label }) => label);
}

export function normalizedTitle(song: CatalogSong, language: Language = "ja"): string {
  const title = language === "en"
    ? song.titles.en ?? song.titles.ja ?? song.id
    : song.titles.ja ?? song.titles.en ?? song.id;
  return normalizeSearchText(title);
}

export function sortSongs(
  songs: CatalogSong[],
  sortMode: "occurrences" | "title" = "occurrences",
  language: Language = "ja",
): CatalogSong[] {
  return [...songs].sort((left, right) => {
    if (sortMode === "occurrences") {
      const countDifference = right.occurrenceCount - left.occurrenceCount;
      if (countDifference !== 0) return countDifference;
    }

    const titleDifference = titleCollator.compare(
      normalizedTitle(left, language),
      normalizedTitle(right, language),
    );
    return titleDifference || left.id.localeCompare(right.id);
  });
}
