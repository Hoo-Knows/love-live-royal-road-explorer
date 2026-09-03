export type Language = "en" | "ja";

export interface UiText {
  language: string;
  english: string;
  japanese: string;
  royalRoad: string;
  appBlurb: string;
  matchingSongsMetric: string;
  uniqueMomentsMetric: string;
  analyzedSongsMetric: string;
  catalogTotalMetric: string;
  withoutAudioMetric: string;
  needsReviewMetric: string;
  catalogTotals: string;
  leaderboard: string;
  groupStatisticsBy: string;
  chartBy: string;
  filterSongsBy: string;
  artistsButton: string;
  seriesButton: string;
  series: string;
  matchingSongs: string;
  occurrences: string;
  artist: string;
  artists: string;
  analyzed: string;
  noAudio: string;
  needsReview: string;
  reviewed: string;
  passingChord: string;
  playbackUnavailable: string;
  analysisNeedsAttention: string;
  missingAudioUrl: string;
  songCouldNotBeAnalyzed: string;
  audioPreview: string;
  released: string;
  minuteSource: string;
  fetchingFromWiki: string;
  audioFetchFailed: string;
  playbackBlocked: string;
  playbackStartFailed: string;
  blobDecodeFailed: string;
  audioLoadFailed: string;
  playingSelectedMoment: string;
  playingSong: string;
  audioReady: string;
  audioPreviewFor: string;
  openOriginalWikiAudio: string;
  occurrence: string;
  paddingNote: string;
  noMatch: string;
  songCatalog: string;
  catalogInstruction: string;
  searchLabel: string;
  searchPlaceholder: string;
  clearSearch: string;
  sortSongs: string;
  sort: string;
  moments: string;
  titleAZ: string;
  filterBy: string;
  allSongs: string;
  filterCatalogBySeries: string;
  filterCatalogByArtists: string;
  allArtists: string;
  allSeries: string;
  song: string;
  songs: string;
  orderedByMomentCount: string;
  orderedByTitle: string;
  filteredTo: string;
  fixtureNotice: string;
  noSongsFound: string;
  tryDifferentSearch: string;
  showFullCatalog: string;
  footerDisclaimer: string;
  sourceMetadata: string;
  detectorMit: string;
}

export const translations: Record<Language, UiText> = {
  en: {
    language: "Language",
    english: "English",
    japanese: "日本語",
    royalRoad: "Love Live! Royal Road Explorer",
    appBlurb: "Have you ever wondered how many Love Live songs use Royal Road in them? No? Just me? Ok whatever here you go anyway\n\nResults are automated chord analysis; chord names/Roman numerals may be incorrect and analysis may have missed occurrences",
    matchingSongsMetric: "matching songs",
    uniqueMomentsMetric: "unique moments",
    analyzedSongsMetric: "songs analyzed",
    catalogTotalMetric: "catalog total",
    withoutAudioMetric: "without audio",
    needsReviewMetric: "needs review",
    catalogTotals: "Catalog totals",
    leaderboard: "Leaderboard",
    groupStatisticsBy: "Group statistics by",
    chartBy: "by",
    filterSongsBy: "Filter songs by",
    artistsButton: "Artists",
    seriesButton: "Series",
    series: "series",
    matchingSongs: "Matching songs",
    occurrences: "Occurrences",
    artist: "artist",
    artists: "artists",
    analyzed: "Analyzed",
    noAudio: "No audio",
    needsReview: "Needs review",
    reviewed: "reviewed",
    passingChord: "passing",
    playbackUnavailable: "Playback is unavailable",
    analysisNeedsAttention: "Analysis needs attention",
    missingAudioUrl: "The source snapshot did not include a wiki audio URL.",
    songCouldNotBeAnalyzed: "This song could not be analyzed.",
    audioPreview: "Audio preview",
    released: "Released",
    minuteSource: "min source",
    fetchingFromWiki: "Fetching audio…",
    audioFetchFailed: "The audio request failed. You can try the original wiki URL below.",
    playbackBlocked: "Playback was blocked by the browser. Use the audio controls to start this moment.",
    playbackStartFailed: "This audio could not start. Try the native audio controls or the original wiki URL.",
    blobDecodeFailed: "The blob could not be decoded. Trying the original wiki URL instead.",
    audioLoadFailed: "The wiki audio could not be loaded. Open the original URL to try it directly.",
    playingSelectedMoment: "Playing moment",
    playingSong: "Playing song",
    audioReady: "Audio ready",
    audioPreviewFor: "Audio preview for",
    openOriginalWikiAudio: "Open original wiki audio ↗",
    occurrence: "occurrence",
    paddingNote: "Playback adds 0.5s on each side",
    noMatch: "The full chord timeline was analyzed, but no match was found.",
    songCatalog: "Song catalog",
    catalogInstruction: "Click on a song to listen to occurrences",
    searchLabel: "Search songs, artists, and series",
    searchPlaceholder: "Search in Japanese, English, or phonetics…",
    clearSearch: "Clear search",
    sortSongs: "Sort songs",
    sort: "Sort",
    moments: "Moments",
    titleAZ: "Title A-Z",
    filterBy: "Filter by",
    allSongs: "All songs",
    filterCatalogBySeries: "Filter catalog by series",
    filterCatalogByArtists: "Filter catalog by artists",
    allArtists: "All artists",
    allSeries: "All series",
    song: "song",
    songs: "songs",
    orderedByMomentCount: "ordered by moment count",
    orderedByTitle: "ordered by title",
    filteredTo: "filtered to",
    fixtureNotice: "This build includes a small offline development slice. The maintainer pipeline can replace it with the complete pinned source snapshot.",
    noSongsFound: "No songs found.",
    tryDifferentSearch: "Try a different title, artist, or series name.",
    showFullCatalog: "Show the full catalog",
    footerDisclaimer: "Results are automated chord analysis and may be wrong. Audio hosted by the Love Live wiki; this site does not mirror recordings.",
    sourceMetadata: "Source metadata ↗",
    detectorMit: "Detector / MIT ↗",
  },
  ja: {
    language: "言語",
    english: "English",
    japanese: "日本語",
    royalRoad: "ラブライブ！王道進行\nエクスプローラー",
    appBlurb: "ラブライブ！の楽曲から、王道進行（IV–V–iii–vi など）が現れる箇所を探して聴けるカタログです。\n\n結果はコードの自動解析によるものです。コード名やローマ数字表記が正しくない場合や、出現箇所を見落としている場合があります。",
    matchingSongsMetric: "一致する楽曲",
    uniqueMomentsMetric: "一致箇所",
    analyzedSongsMetric: "解析済み楽曲",
    catalogTotalMetric: "カタログ総数",
    withoutAudioMetric: "音源なし",
    needsReviewMetric: "要確認",
    catalogTotals: "カタログ合計",
    leaderboard: "ランキング",
    groupStatisticsBy: "集計単位",
    chartBy: "別",
    filterSongsBy: "楽曲を絞り込む",
    artistsButton: "アーティスト",
    seriesButton: "シリーズ",
    series: "シリーズ",
    matchingSongs: "一致楽曲",
    occurrences: "出現箇所",
    artist: "アーティスト",
    artists: "アーティスト",
    analyzed: "解析済み",
    noAudio: "音源なし",
    needsReview: "要確認",
    reviewed: "確認済み",
    passingChord: "経過コード",
    playbackUnavailable: "再生できません",
    analysisNeedsAttention: "解析に問題があります",
    missingAudioUrl: "ソーススナップショットに wiki の音源 URL がありません。",
    songCouldNotBeAnalyzed: "この楽曲は解析できませんでした。",
    audioPreview: "音源プレビュー",
    released: "リリース",
    minuteSource: "分の音源",
    fetchingFromWiki: "wiki から取得中…",
    audioFetchFailed: "音源の取得に失敗しました。下の wiki 元音源 URL をお試しください。",
    playbackBlocked: "ブラウザーによって再生がブロックされました。音源コントロールからこの箇所を再生してください。",
    playbackStartFailed: "音源を再生できませんでした。音源コントロールまたは wiki 元音源 URL をお試しください。",
    blobDecodeFailed: "取得した音源をデコードできませんでした。wiki 元音源 URL を試しています。",
    audioLoadFailed: "wiki の音源を読み込めませんでした。元音源 URL を直接お試しください。",
    playingSelectedMoment: "選択した箇所を再生中",
    playingSong: "楽曲を再生中",
    audioReady: "音源の準備完了",
    audioPreviewFor: "音源プレビュー：",
    openOriginalWikiAudio: "wiki の元音源を開く ↗",
    occurrence: "箇所",
    paddingNote: "前後 0.5 秒を含めて再生",
    noMatch: "コードタイムライン全体を解析しましたが、一致は見つかりませんでした。",
    songCatalog: "楽曲カタログ",
    catalogInstruction: "楽曲をクリックして一致箇所を聴く",
    searchLabel: "楽曲、アーティスト、シリーズを検索",
    searchPlaceholder: "日本語、英語、読み方で検索…",
    clearSearch: "検索をクリア",
    sortSongs: "楽曲を並べ替え",
    sort: "並べ替え",
    moments: "箇所数",
    titleAZ: "タイトル順",
    filterBy: "絞り込み",
    allSongs: "すべての楽曲",
    filterCatalogBySeries: "シリーズでカタログを絞り込む",
    filterCatalogByArtists: "アーティストでカタログを絞り込む",
    allArtists: "すべてのアーティスト",
    allSeries: "すべてのシリーズ",
    song: "曲",
    songs: "曲",
    orderedByMomentCount: "箇所数順",
    orderedByTitle: "タイトル順",
    filteredTo: "絞り込み：",
    fixtureNotice: "このビルドにはオフライン開発用の小さなデータが含まれています。メンテナーパイプラインで固定ソーススナップショット全体に置き換えられます。",
    noSongsFound: "楽曲が見つかりません。",
    tryDifferentSearch: "別のタイトル、アーティスト名、またはシリーズ名を試してください。",
    showFullCatalog: "カタログ全体を表示",
    footerDisclaimer: "結果は自動コード解析であり、誤りを含む場合があります。音源は Love Live wiki にホストされており、このサイトは録音をミラーリングしません。",
    sourceMetadata: "ソースメタデータ ↗",
    detectorMit: "検出器 / MIT ↗",
  },
};
