export type AnalysisStatus = "analyzed" | "unavailable" | "failed";
export type OccurrenceProvenance = "automatic" | "manual";

export interface SongTitles {
  ja?: string;
  en?: string;
  phonetic?: string;
}

export interface CatalogChordBound {
  startSeconds: number;
  endSeconds: number;
}

export interface CatalogOccurrence {
  id: string;
  exactStartSeconds: number;
  exactEndSeconds: number;
  playbackStartSeconds: number;
  playbackEndSeconds: number;
  chordLabels: string[];
  chordBounds: CatalogChordBound[];
  patternIds: string[];
  /** Optional for compatibility with hand-built test/catalog snapshots. */
  romanNumeralAnalyses?: string[];
  passingChordIndex: number | null;
  provenance: OccurrenceProvenance;
}

export interface CatalogSong {
  id: string;
  titles: SongTitles;
  artistNames: string[];
  artistAliases: string[];
  seriesNames: string[];
  seriesAliases: string[];
  audioUrl: string | null;
  releaseDate?: string | null;
  status: AnalysisStatus;
  durationSeconds: number | null;
  error: string | null;
  occurrenceCount: number;
  occurrences: CatalogOccurrence[];
}

export interface CatalogPattern {
  id: string;
  label: string;
}

export interface CatalogMetrics {
  matchingSongCount: number;
  totalOccurrenceCount: number;
  analyzedSongCount: number;
  catalogSongCount: number;
  unavailableSongCount: number;
  failedSongCount: number;
}

export interface Catalog {
  schemaVersion: string;
  isFixture: boolean;
  patterns: CatalogPattern[];
  metrics: CatalogMetrics;
  songs: CatalogSong[];
}
