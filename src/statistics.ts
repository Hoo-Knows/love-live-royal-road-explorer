import { localizedNames, localizedSeriesNames, normalizeSearchText } from "./search";
import type { Language } from "./i18n";
import type { CatalogSong } from "./types";

export type StatisticDimension = "artists" | "series" | "creators";
export type StatisticMetric = "matchingSongCount" | "occurrenceCount";

export interface CategoryStatistic {
  id?: string;
  name: string;
  matchingSongCount: number;
  occurrenceCount: number;
}

export interface CatalogStatistics {
  artists: CategoryStatistic[];
  series: CategoryStatistic[];
  creators: CategoryStatistic[];
}

const statisticCollator = new Intl.Collator(undefined, {
  sensitivity: "base",
  numeric: true,
  usage: "sort",
});

function aggregateDimension(
  songs: CatalogSong[],
  namesForSong: (song: CatalogSong) => string[],
): CategoryStatistic[] {
  const statisticsByName = new Map<string, CategoryStatistic>();

  for (const song of songs) {
    const occurrenceCount = song.occurrenceCount;
    if (occurrenceCount < 1) continue;

    for (const name of new Set(namesForSong(song).filter(Boolean))) {
      const statistic = statisticsByName.get(name) ?? {
        name,
        matchingSongCount: 0,
        occurrenceCount: 0,
      };
      statistic.matchingSongCount += 1;
      statistic.occurrenceCount += occurrenceCount;
      statisticsByName.set(name, statistic);
    }
  }

  return [...statisticsByName.values()];
}

function aggregateCreators(songs: CatalogSong[]): CategoryStatistic[] {
  const statisticsById = new Map<string, CategoryStatistic>();

  for (const song of songs) {
    const occurrenceCount = song.occurrenceCount;
    if (occurrenceCount < 1) continue;

    for (const creator of new Map(song.creators.map((entry) => [entry.id, entry])).values()) {
      const statistic = statisticsById.get(creator.id) ?? {
        id: creator.id,
        name: creator.name,
        matchingSongCount: 0,
        occurrenceCount: 0,
      };
      statistic.matchingSongCount += 1;
      statistic.occurrenceCount += occurrenceCount;
      statisticsById.set(creator.id, statistic);
    }
  }

  return [...statisticsById.values()];
}

export function buildCatalogStatistics(songs: CatalogSong[], language: Language = "ja"): CatalogStatistics {
  return {
    artists: aggregateDimension(songs, (song) => localizedNames(song.artistNames, song.artistAliases, language)),
    series: aggregateDimension(songs, (song) => localizedSeriesNames(song.seriesNames, song.seriesAliases, language)),
    creators: aggregateCreators(songs),
  };
}

export function rankStatistics(
  statistics: CategoryStatistic[],
  metric: StatisticMetric,
): CategoryStatistic[] {
  return [...statistics].sort((left, right) => {
    const countDifference = right[metric] - left[metric];
    if (countDifference !== 0) return countDifference;

    const nameDifference = statisticCollator.compare(
      normalizeSearchText(left.name),
      normalizeSearchText(right.name),
    );
    if (nameDifference !== 0) return nameDifference;
    if (left.id || right.id) return (left.id ?? "").localeCompare(right.id ?? "");
    return left.name.localeCompare(right.name);
  });
}
