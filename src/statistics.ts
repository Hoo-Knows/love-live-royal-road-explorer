import { localizedNames, localizedSeriesNames, normalizeSearchText } from "./search";
import type { Language } from "./i18n";
import type { CatalogSong } from "./types";

export type StatisticDimension = "artists" | "series";
export type StatisticMetric = "matchingSongCount" | "occurrenceCount";

export interface CategoryStatistic {
  name: string;
  matchingSongCount: number;
  occurrenceCount: number;
}

export interface CatalogStatistics {
  artists: CategoryStatistic[];
  series: CategoryStatistic[];
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

export function buildCatalogStatistics(songs: CatalogSong[], language: Language = "ja"): CatalogStatistics {
  return {
    artists: aggregateDimension(songs, (song) => localizedNames(song.artistNames, song.artistAliases, language)),
    series: aggregateDimension(songs, (song) => localizedSeriesNames(song.seriesNames, song.seriesAliases, language)),
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
    return nameDifference || left.name.localeCompare(right.name);
  });
}
