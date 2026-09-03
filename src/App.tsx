import { Fragment, memo, useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { patternLabel, useCatalog } from "./catalog";
import { isPlaybackCue, useAudioMoment } from "./audio";
import { formatDate, formatSeconds } from "./format";
import {
  facetOptions,
  filterSongs,
  filterSongsByFacet,
  localizedNames,
  localizedSeriesNames,
  sortSongs,
} from "./search";
import type { CatalogFacetFilter, CatalogFilterDimension } from "./search";
import { translations, type Language } from "./i18n";
import {
  buildCatalogStatistics,
  rankStatistics,
  type StatisticDimension,
  type StatisticMetric,
} from "./statistics";
import type { CategoryStatistic } from "./statistics";
import type { CatalogOccurrence, CatalogSong } from "./types";

function Metric({
  value,
  label,
  accent = false,
  language,
}: {
  value: number;
  label: string;
  accent?: boolean;
  language: Language;
}) {
  return (
    <div className={`metric ${accent ? "metric-accent" : ""}`}>
      <strong>{value.toLocaleString(language === "ja" ? "ja-JP" : "en-US")}</strong>
      <span>{label}</span>
    </div>
  );
}

const StatisticsChart = memo(function StatisticsChart({
  statistics,
  metric,
  dimension,
  language,
}: {
  statistics: CategoryStatistic[];
  metric: StatisticMetric;
  dimension: StatisticDimension;
  language: Language;
}) {
  const text = translations[language];
  const rankedStatistics = rankStatistics(statistics, metric);
  const maximum = rankedStatistics[0]?.[metric] ?? 0;
  const isSongChart = metric === "matchingSongCount";
  const title = isSongChart ? text.matchingSongs : text.occurrences;
  const categoryLabel = dimension === "artists" ? text.artist : text.series;
  const hasOverflow = rankedStatistics.length > 10;
  const chartId = `${dimension}-${metric}-chart`;

  return (
    <article className="statistics-chart" aria-labelledby={`${chartId}-title`}>
      <div className="statistics-chart-heading">
        <div>
          <h3 id={`${chartId}-title`}>{title}</h3>
        </div>
      </div>
      <section
        key={dimension}
        className={`statistics-scroll ${hasOverflow ? "statistics-scroll-overflow" : ""}`}
        aria-label={`${title} ${text.chartBy} ${categoryLabel}`}
        tabIndex={hasOverflow ? 0 : undefined}
      >
        <ol className="statistics-list">
          {rankedStatistics.map((statistic, index) => {
            const value = statistic[metric];
            return (
              <li className="statistics-row" key={statistic.name}>
                <span className="statistics-rank" aria-hidden="true">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div className="statistics-entry">
                  <div className="statistics-entry-copy">
                    <span className="statistics-name">{statistic.name}</span>
                    <strong>{value.toLocaleString(language === "ja" ? "ja-JP" : "en-US")}</strong>
                  </div>
                  <div className="statistics-bar-track" aria-hidden="true">
                    <span
                      className="statistics-bar"
                      style={{ width: maximum ? `${(value / maximum) * 100}%` : "0%" }}
                    />
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      </section>
    </article>
  );
});

const CatalogStatisticsSection = memo(function CatalogStatisticsSection({
  songs,
  language,
}: {
  songs: CatalogSong[];
  language: Language;
}) {
  const text = translations[language];
  const [dimension, setDimension] = useState<StatisticDimension>("artists");
  const deferredDimension = useDeferredValue(dimension);
  const statistics = useMemo(() => buildCatalogStatistics(songs, language), [songs, language]);
  const visibleStatistics = statistics[deferredDimension];
  const isRefreshing = deferredDimension !== dimension;

  return (
    <section className="statistics-section" aria-labelledby="statistics-heading">
      <div className="statistics-section-heading">
        <div>
          <h2 id="statistics-heading">{text.leaderboard}</h2>
        </div>
        <fieldset className="toggle-control statistics-toggle">
          <legend className="sr-only">{text.groupStatisticsBy}</legend>
          <span className="toggle-label" aria-hidden="true">{text.groupStatisticsBy}</span>
          <button
            type="button"
            className={dimension === "artists" ? "statistics-toggle-active" : ""}
            aria-pressed={dimension === "artists"}
            onClick={() => setDimension("artists")}
          >
            {text.artistsButton}
          </button>
          <button
            type="button"
            className={dimension === "series" ? "statistics-toggle-active" : ""}
            aria-pressed={dimension === "series"}
            onClick={() => setDimension("series")}
          >
            {text.seriesButton}
          </button>
        </fieldset>
      </div>

      <div className="statistics-grid" aria-busy={isRefreshing}>
        <StatisticsChart
          statistics={visibleStatistics}
          metric="matchingSongCount"
          dimension={deferredDimension}
          language={language}
        />
        <StatisticsChart
          statistics={visibleStatistics}
          metric="occurrenceCount"
          dimension={deferredDimension}
          language={language}
        />
      </div>
    </section>
  );
});

function StatusPill({ status, language }: { status: CatalogSong["status"]; language: Language }) {
  const text = translations[language];
  const labels = {
    analyzed: text.analyzed,
    unavailable: text.noAudio,
    failed: text.needsReview,
  } as const;
  return <span className={`status status-${status}`}>{labels[status]}</span>;
}

function OccurrenceButton({
  occurrence,
  disabled,
  selected,
  activeChordIndex,
  onSelect,
  onFocusLeave,
  language,
}: {
  occurrence: CatalogOccurrence;
  disabled: boolean;
  selected: boolean;
  activeChordIndex: number | null;
  onSelect: () => void;
  onFocusLeave: () => void;
  language: Language;
}) {
  const text = translations[language];
  const chordEntries = occurrence.chordLabels.map((label, position) => ({
    key: `${occurrence.id}-chord-${position}`,
    label,
    position,
  }));
  const romanNumeralText = occurrence.romanNumeralAnalyses
    ?.filter((analysis) => analysis.trim())
    .join(" · ");
  const occurrenceLabel = romanNumeralText || occurrence.patternIds.map(patternLabel).join(" · ");
  return (
    <button
      type="button"
      className={`occurrence-button ${selected ? "occurrence-selected" : ""}`}
      disabled={disabled}
      onClick={onSelect}
      onBlur={() => {
        if (selected) onFocusLeave();
      }}
      aria-pressed={selected}
    >
      <span className="occurrence-time">{formatSeconds(occurrence.exactStartSeconds)}</span>
      <span className="occurrence-copy">
        <span className="occurrence-pattern">
          {occurrenceLabel}
          {occurrence.provenance === "manual" ? <span className="manual-tag">{text.reviewed}</span> : null}
        </span>
        <span className="occurrence-chords">
          {chordEntries.map((entry) => (
            <span
              className="occurrence-chord-entry"
              key={entry.key}
            >
              {entry.position ? <span className="chord-arrow" aria-hidden="true"> → </span> : null}
              <span
                className={[
                  "occurrence-chord",
                  entry.position === occurrence.passingChordIndex ? "passing-chord" : "",
                  entry.position === activeChordIndex ? "occurrence-chord-active" : "",
                ].filter(Boolean).join(" ")}
              >
                {entry.label}
              </span>
              {entry.position === occurrence.passingChordIndex ? <span className="passing-tag">{text.passingChord}</span> : null}
            </span>
          ))}
        </span>
      </span>
      <span className="occurrence-arrow" aria-hidden="true">↗</span>
    </button>
  );
}

function chordIndexAtTime(
  occurrence: CatalogOccurrence,
  playbackTime: number | null,
  isPlaying: boolean,
): number | null {
  if (!isPlaying || playbackTime === null) return null;
  const index = occurrence.chordBounds.findIndex(
    ({ startSeconds, endSeconds }) => playbackTime >= startSeconds && playbackTime < endSeconds,
  );
  return index === -1 ? null : index;
}

function isOccurrenceActiveAtTime(occurrence: CatalogOccurrence, playbackTime: number | null): boolean {
  return playbackTime !== null
    && playbackTime >= occurrence.exactStartSeconds
    && playbackTime < occurrence.exactEndSeconds;
}

interface OccurrenceHighlight {
  occurrence: CatalogOccurrence;
  chordIndex: number | null;
}

function SongPlayer({
  song,
  language,
  onOccurrenceSelect,
  onOccurrenceChordPlay,
  onPlaybackStop,
}: {
  song: CatalogSong;
  language: Language;
  onOccurrenceSelect: (occurrence: CatalogOccurrence) => void;
  onOccurrenceChordPlay: (song: CatalogSong, occurrence: CatalogOccurrence) => void;
  onPlaybackStop: () => void;
}) {
  const text = translations[language];
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playbackTime, setPlaybackTime] = useState<number | null>(null);
  const audio = useAudioMoment(song, audioRef, {
    onPlaybackStop,
    onUserPlaybackControl: onPlaybackStop,
    onPlaybackTimeChange: setPlaybackTime,
  }, text);
  const capturePlaybackTime = (element: HTMLAudioElement) => {
    setPlaybackTime(Number.isFinite(element.currentTime) ? element.currentTime : null);
  };
  const date = formatDate(song.releaseDate, language === "ja" ? "ja-JP" : "en-US");
  const occurrences = song.occurrences;
  const occurrenceCount = song.occurrenceCount;
  const selectedOccurrence = audio.selectedOccurrenceId
    ? occurrences.find(({ id }) => id === audio.selectedOccurrenceId) ?? null
    : null;
  const highlightedOccurrences = audio.playbackMode === "moment"
    ? selectedOccurrence
      ? [{ occurrence: selectedOccurrence, chordIndex: chordIndexAtTime(selectedOccurrence, playbackTime, audio.isPlaying) }]
      : []
    : audio.playbackMode === "song" && audio.isPlaying
      ? occurrences.flatMap((occurrence) => {
          if (!isOccurrenceActiveAtTime(occurrence, playbackTime)) return [];
          return [{ occurrence, chordIndex: chordIndexAtTime(occurrence, playbackTime, true) }];
        })
      : [];
  const highlightedOccurrenceIds = new Set(highlightedOccurrences.map(({ occurrence }) => occurrence.id));
  const activeChordByOccurrenceId = new Map(
    highlightedOccurrences.map(({ occurrence, chordIndex }) => [occurrence.id, chordIndex]),
  );
  const highlightKey = highlightedOccurrences
    .map(({ occurrence, chordIndex }) => `${occurrence.id}:${chordIndex ?? "none"}`)
    .join("|");
  const highlightCacheRef = useRef<{ key: string; song: CatalogSong; highlights: OccurrenceHighlight[] }>({
    key: "",
    song,
    highlights: [],
  });
  if (highlightCacheRef.current.key !== highlightKey || highlightCacheRef.current.song !== song) {
    highlightCacheRef.current = { key: highlightKey, song, highlights: highlightedOccurrences };
  }
  const stableHighlightedOccurrences = highlightCacheRef.current.highlights;

  useEffect(() => {
    stableHighlightedOccurrences.forEach(({ occurrence, chordIndex }) => {
      if (chordIndex !== null) onOccurrenceChordPlay(song, occurrence);
    });
  }, [onOccurrenceChordPlay, song, stableHighlightedOccurrences]);

  if (song.status !== "analyzed" || !song.audioUrl) {
    return (
      <div className={`detail-status detail-status-${song.status}`}>
        <span className="detail-status-icon" aria-hidden="true">{song.status === "unavailable" ? "—" : "!"}</span>
        <div>
          <strong>{song.status === "unavailable" ? text.playbackUnavailable : text.analysisNeedsAttention}</strong>
          <p>{song.error ?? (song.status === "unavailable" ? text.missingAudioUrl : text.songCouldNotBeAnalyzed)}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="song-detail">
      <div className="detail-topline">
        <h3>{text.audioPreview}</h3>
        <div className="detail-meta">
          {date ? <span>{text.released} {date}</span> : null}
          {song.durationSeconds ? <span>{Math.round(song.durationSeconds / 60)} {text.minuteSource}</span> : null}
        </div>
      </div>

      <div className="player-shell">
        <div className="player-label">
          <span className={`pulse-dot ${audio.isPlaying ? "pulse-live" : ""}`} aria-hidden="true" />
          <span>{audio.loadState === "loading"
            ? text.fetchingFromWiki
            : audio.isPlaying
              ? audio.playbackMode === "moment" ? text.playingSelectedMoment : text.playingSong
              : text.audioReady}</span>
        </div>
        {/* biome-ignore lint/a11y/useMediaCaption: The source is instrumental music; chord labels and moment controls provide the available text alternative. */}
        <audio
          ref={audioRef}
          className="audio-control"
          controls
          preload="metadata"
          src={audio.source ?? undefined}
          onLoadedMetadata={(event) => {
            audio.markMetadataReady();
            capturePlaybackTime(event.currentTarget);
          }}
          onError={audio.handleAudioError}
          onPlay={(event) => {
            capturePlaybackTime(event.currentTarget);
            audio.handleAudioPlay();
          }}
          onPause={(event) => {
            capturePlaybackTime(event.currentTarget);
            audio.handleAudioPause();
          }}
          onSeeking={(event) => {
            capturePlaybackTime(event.currentTarget);
            audio.handleAudioSeeking();
          }}
          onTimeUpdate={(event) => capturePlaybackTime(event.currentTarget)}
          aria-label={`${text.audioPreviewFor} ${language === "en"
            ? song.titles.en ?? song.titles.ja ?? song.id
            : song.titles.ja ?? song.titles.en ?? song.id}`}
        />
      </div>

      {audio.errorMessage ? (
        <div className={`audio-message ${audio.loadState === "error" ? "audio-message-error" : ""}`} role="status">
          <span>{audio.errorMessage}</span>{" "}
          <a href={song.audioUrl} target="_blank" rel="noreferrer">{text.openOriginalWikiAudio}</a>
        </div>
      ) : null}

      <div className="occurrence-heading">
        <div>
          <h4>{occurrenceCount} {occurrenceCount === 1 ? text.occurrence : text.occurrences}</h4>
        </div>
        <span className="padding-note">{text.paddingNote}</span>
      </div>
      {occurrences.length ? (
        <div className="occurrence-list">
          {occurrences.map((occurrence) => (
            <OccurrenceButton
              key={occurrence.id}
              occurrence={occurrence}
              disabled={!audio.metadataReady || audio.loadState === "loading" || audio.loadState === "error"}
              selected={highlightedOccurrenceIds.has(occurrence.id)}
              activeChordIndex={activeChordByOccurrenceId.get(occurrence.id) ?? null}
              onFocusLeave={audio.clearMomentSelection}
              onSelect={() => {
                onOccurrenceSelect(occurrence);
                audio.selectOccurrence(occurrence);
                if (audioRef.current) {
                  capturePlaybackTime(audioRef.current);
                }
              }}
              language={language}
            />
          ))}
        </div>
      ) : (
        <p className="empty-occurrences">{text.noMatch}</p>
      )}
    </div>
  );
}

const SongRow = memo(function SongRow({
  song,
  expanded,
  onToggle,
  onOccurrenceSelect,
  onOccurrenceChordPlay,
  onPlaybackStop,
  language,
}: {
  song: CatalogSong;
  expanded: boolean;
  onToggle: (songId: string) => void;
  onOccurrenceSelect: (song: CatalogSong, occurrence: CatalogOccurrence) => void;
  onOccurrenceChordPlay: (song: CatalogSong, occurrence: CatalogOccurrence) => void;
  onPlaybackStop: () => void;
  language: Language;
}) {
  const primaryTitle = language === "en"
    ? song.titles.en ?? song.titles.ja ?? song.id
    : song.titles.ja ?? song.titles.en ?? song.id;
  const subtitle = language === "en"
    && song.titles.ja
    && song.titles.ja !== primaryTitle
    ? song.titles.ja
    : null;
  const occurrenceCount = song.occurrenceCount;
  const metadata = [
    { key: "artists", value: localizedNames(song.artistNames, song.artistAliases, language).join(", ") },
    { key: "series", value: localizedSeriesNames(song.seriesNames, song.seriesAliases, language).join(", ") },
  ].filter(({ value }) => Boolean(value));

  return (
    <li className={`song-card ${expanded ? "song-card-expanded" : ""}`}>
      <button
        type="button"
        className="song-summary"
        onClick={() => onToggle(song.id)}
        aria-expanded={expanded}
        aria-controls={`song-detail-${song.id}`}
      >
        <span className="song-number" aria-hidden="true" />
        <span className="song-heading">
          <span className="song-title">{primaryTitle}</span>
          {subtitle ? <span className="song-subtitle">{subtitle}</span> : null}
          <span className="song-meta">{metadata.map((item) => <span key={item.key}>{item.value}</span>)}</span>
        </span>
        <span className="song-count">
          <strong>{occurrenceCount}</strong>
          <span>{occurrenceCount === 1 ? translations[language].occurrence : translations[language].occurrences}</span>
        </span>
        <StatusPill status={song.status} language={language} />
        <span className={`expand-icon ${expanded ? "expand-icon-open" : ""}`} aria-hidden="true">↓</span>
      </button>
      {expanded ? (
        <div id={`song-detail-${song.id}`} className="song-detail-region">
          <SongPlayer
            song={song}
            language={language}
            onOccurrenceSelect={(occurrence) => onOccurrenceSelect(song, occurrence)}
            onOccurrenceChordPlay={onOccurrenceChordPlay}
            onPlaybackStop={onPlaybackStop}
          />
        </div>
      ) : null}
    </li>
  );
});

const CatalogFacetControls = memo(function CatalogFacetControls({
  songs,
  filter,
  onChange,
  language,
  sortMode,
  onSortModeChange,
}: {
  songs: CatalogSong[];
  filter: CatalogFacetFilter;
  onChange: (nextFilter: CatalogFacetFilter) => void;
  language: Language;
  sortMode: "occurrences" | "title";
  onSortModeChange: (nextSortMode: "occurrences" | "title") => void;
}) {
  const text = translations[language];
  const options = useMemo(
    () => filter.dimension === "all" ? [] : facetOptions(songs, filter.dimension, language),
    [songs, filter.dimension, language],
  );
  const facetLabel = filter.dimension === "artists" ? text.artists : text.series;

  const selectDimension = (dimension: CatalogFilterDimension) => {
    onChange({ dimension, value: null });
  };

  return (
    <div className="catalog-filters">
      <div className="catalog-toggle-row">
        <fieldset className="toggle-control filter-control">
          <legend className="sr-only">{text.filterBy}</legend>
          <span className="toggle-label" aria-hidden="true">{text.filterBy}</span>
          <button
            type="button"
            className={filter.dimension === "all" ? "filter-active" : ""}
            aria-pressed={filter.dimension === "all"}
            onClick={() => selectDimension("all")}
          >
            {text.allSongs}
          </button>
          <button
            type="button"
            className={filter.dimension === "artists" ? "filter-active" : ""}
            aria-pressed={filter.dimension === "artists"}
            onClick={() => selectDimension("artists")}
          >
            {text.artistsButton}
          </button>
          <button
            type="button"
            className={filter.dimension === "series" ? "filter-active" : ""}
            aria-label={text.filterCatalogBySeries}
            aria-pressed={filter.dimension === "series"}
            onClick={() => selectDimension("series")}
          >
            {text.seriesButton}
          </button>
        </fieldset>

        <fieldset className="toggle-control sort-control">
          <legend className="sr-only">{text.sortSongs}</legend>
          <span className="toggle-label" aria-hidden="true">{text.sort}</span>
          <button
            type="button"
            className={sortMode === "occurrences" ? "sort-active" : ""}
            aria-pressed={sortMode === "occurrences"}
            onClick={() => onSortModeChange("occurrences")}
          >
            {text.moments}
          </button>
          <button
            type="button"
            className={sortMode === "title" ? "sort-active" : ""}
            aria-pressed={sortMode === "title"}
            onClick={() => onSortModeChange("title")}
          >
            {text.titleAZ}
          </button>
        </fieldset>
      </div>

      {filter.dimension !== "all" ? (
        <fieldset className="filter-options">
          <legend className="sr-only">{text.filterSongsBy} {facetLabel}</legend>
          <button
            type="button"
            className={`filter-option ${filter.value === null ? "filter-option-active" : ""}`}
            aria-pressed={filter.value === null}
            onClick={() => onChange({ ...filter, value: null })}
          >
            {filter.dimension === "artists" ? text.allArtists : text.allSeries}
          </button>
          {options.map((option) => (
            <button
              type="button"
              className={`filter-option ${filter.value === option.value ? "filter-option-active" : ""}`}
              aria-pressed={filter.value === option.value}
              key={option.value}
              onClick={() => onChange({ ...filter, value: option.value })}
            >
              {option.label}
            </button>
          ))}
        </fieldset>
      ) : null}
    </div>
  );
});

export default function App() {
  const catalog = useCatalog();
  const [language, setLanguage] = useState<Language>("en");
  const [query, setQuery] = useState("");
  const [sortMode, setSortMode] = useState<"occurrences" | "title">("occurrences");
  const [catalogFilter, setCatalogFilter] = useState<CatalogFacetFilter>({ dimension: "all", value: null });
  const [expandedSongId, setExpandedSongId] = useState<string | null>(null);
  const [orangeHighlights, setOrangeHighlights] = useState(false);
  const text = translations[language];
  const deferredQuery = useDeferredValue(query);
  const deferredSortMode = useDeferredValue(sortMode);
  const deferredCatalogFilter = useDeferredValue(catalogFilter);

  useEffect(() => {
    document.documentElement.lang = language;
    document.title = text.royalRoad.replaceAll("\n", " ");
  }, [language, text.royalRoad]);

  const visibleSongs = useMemo(
    () => sortSongs(
      filterSongsByFacet(filterSongs(catalog.songs, deferredQuery), deferredCatalogFilter),
      deferredSortMode,
      language,
    ),
    [catalog.songs, deferredCatalogFilter, deferredQuery, deferredSortMode, language],
  );

  const toggleSong = useCallback((songId: string) => {
    setOrangeHighlights(false);
    setExpandedSongId((current) => current === songId ? null : songId);
  }, []);

  const handleOccurrenceSelect = useCallback(() => {
    setOrangeHighlights(false);
  }, []);

  const handleOccurrenceChordPlay = useCallback((song: CatalogSong, occurrence: CatalogOccurrence) => {
    if (isPlaybackCue(song, occurrence)) {
      setOrangeHighlights(true);
    }
  }, []);

  const clearOrangeHighlights = useCallback(() => {
    setOrangeHighlights(false);
  }, []);

  useEffect(() => {
    if (!orangeHighlights || !expandedSongId) return;
    const expandedSong = catalog.songs.find((song) => song.id === expandedSongId);
    if (expandedSong?.status !== "analyzed" || !expandedSong.audioUrl) {
      setOrangeHighlights(false);
      return;
    }
    if (visibleSongs.some((song) => song.id === expandedSongId)) return;
    setOrangeHighlights(false);
  }, [catalog.songs, expandedSongId, orangeHighlights, visibleSongs]);

  const isCatalogRefreshing = query !== deferredQuery
    || sortMode !== deferredSortMode
    || catalogFilter !== deferredCatalogFilter;
  const selectedFilter = catalogFilter.value && catalogFilter.dimension !== "all"
    ? `${catalogFilter.dimension === "artists" ? text.artist : text.series}: ${facetOptions(
      catalog.songs,
      catalogFilter.dimension,
      language,
    ).find((option) => option.value === catalogFilter.value)?.label ?? catalogFilter.value}`
    : null;
  const clearCatalogView = useCallback(() => {
    setQuery("");
    setCatalogFilter({ dimension: "all", value: null });
  }, []);

  return (
    <div className={`app-shell ${orangeHighlights ? "app-shell-orange-highlights" : ""}`} lang={language}>
      <main>
        <section className="hero" aria-labelledby="page-title">
          <fieldset className="toggle-control language-toggle">
            <legend className="sr-only">{text.language}</legend>
            <button
              type="button"
              className={language === "en" ? "language-toggle-active" : ""}
              aria-pressed={language === "en"}
              onClick={() => setLanguage("en")}
            >
              {text.english}
            </button>
            <button
              type="button"
              className={language === "ja" ? "language-toggle-active" : ""}
              aria-pressed={language === "ja"}
              onClick={() => setLanguage("ja")}
            >
              {text.japanese}
            </button>
          </fieldset>
          <div className="hero-copy">
            <h1 id="page-title" aria-label={text.royalRoad.replaceAll("\n", " ")}>
              {text.royalRoad.split("\n").map((line, index) => (
                <Fragment key={line}>
                  {index > 0 ? <br /> : null}
                  {line}
                </Fragment>
              ))}
            </h1>
            <p className="hero-blurb">{text.appBlurb}</p>
          </div>
        </section>

        <section className="metrics" aria-label={text.catalogTotals}>
          <Metric value={catalog.metrics.matchingSongCount} label={text.matchingSongsMetric} accent language={language} />
          <Metric value={catalog.metrics.totalOccurrenceCount} label={text.uniqueMomentsMetric} accent language={language} />
          <Metric value={catalog.metrics.analyzedSongCount} label={text.analyzedSongsMetric} language={language} />
          <Metric value={catalog.metrics.catalogSongCount} label={text.catalogTotalMetric} language={language} />
          <Metric value={catalog.metrics.unavailableSongCount} label={text.withoutAudioMetric} language={language} />
          <Metric value={catalog.metrics.failedSongCount} label={text.needsReviewMetric} language={language} />
        </section>

        <CatalogStatisticsSection songs={catalog.songs} language={language} />

        <section className="catalog-section" aria-labelledby="catalog-heading">
          <div className="section-heading">
            <div className="section-heading-copy">
              <h2 id="catalog-heading">{text.songCatalog}</h2>
              <p className="section-blurb">{text.catalogInstruction}</p>
            </div>
          </div>

          <div className="toolbar">
            <label className="search-box">
              <span className="search-icon" aria-hidden="true">⌕</span>
              <span className="sr-only">{text.searchLabel}</span>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={text.searchPlaceholder}
                type="search"
                autoComplete="off"
              />
              {query ? <button type="button" className="clear-search" onClick={() => setQuery("")} aria-label={text.clearSearch}>×</button> : null}
            </label>
          </div>

          <CatalogFacetControls
            songs={catalog.songs}
            filter={catalogFilter}
            onChange={setCatalogFilter}
            language={language}
            sortMode={sortMode}
            onSortModeChange={setSortMode}
          />

          <div className="results-line" aria-live="polite" aria-busy={isCatalogRefreshing}>
            <span><strong>{visibleSongs.length}</strong> {visibleSongs.length === 1 ? text.song : text.songs}</span>
            {selectedFilter ? <span>{text.filteredTo} {selectedFilter}</span> : null}
          </div>

          {catalog.isFixture ? (
            <div className="fixture-notice" role="note">
              <span aria-hidden="true">✦</span>
              <span>{text.fixtureNotice}</span>
            </div>
          ) : null}

          {visibleSongs.length ? (
            <ol className="song-list">
              {visibleSongs.map((song) => (
                <SongRow
                  key={song.id}
                  song={song}
                  expanded={expandedSongId === song.id}
                  onToggle={toggleSong}
                  onOccurrenceSelect={handleOccurrenceSelect}
                  onOccurrenceChordPlay={handleOccurrenceChordPlay}
                  onPlaybackStop={clearOrangeHighlights}
                  language={language}
                />
              ))}
            </ol>
          ) : (
            <div className="no-results">
              <span className="no-results-mark" aria-hidden="true">∅</span>
              <h3>{text.noSongsFound}</h3>
              <p>{text.tryDifferentSearch}</p>
              <button type="button" onClick={clearCatalogView}>{text.showFullCatalog}</button>
            </div>
          )}
        </section>
      </main>

      <footer className="site-footer">
        <div className="footer-main">
          <div>
            <p className="footer-disclaimer">{text.footerDisclaimer}</p>
          </div>
          <div className="footer-links">
            <a href="https://github.com/hamproductions/the-sorter/tree/main/data" target="_blank" rel="noreferrer">{text.sourceMetadata}</a>
            <a href="https://github.com/Hoo-Knows/large-vocabulary-chord-recognition" target="_blank" rel="noreferrer">{text.detectorMit}</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
