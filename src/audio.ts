import { type RefObject, useCallback, useEffect, useRef, useState } from "react";
import { formatSeconds } from "./format";
import type { CatalogOccurrence, CatalogSong } from "./types";

export type AudioLoadState = "idle" | "loading" | "ready" | "fallback" | "error";
export type PlaybackMode = "idle" | "song" | "moment";

export interface AudioMomentState {
  loadState: AudioLoadState;
  source: string | null;
  sourceMode: "none" | "blob" | "direct";
  metadataReady: boolean;
  selectedOccurrenceId: string | null;
  playbackMode: PlaybackMode;
  isPlaying: boolean;
  errorMessage: string | null;
}

export interface PlaybackScheduler {
  request: (callback: FrameRequestCallback) => number;
  cancel: (frameId: number) => void;
}

export interface AudioMomentCallbacks {
  onPlaybackStop?: () => void;
  onUserPlaybackControl?: () => void;
  onPlaybackTimeChange?: (currentTime: number) => void;
}

export interface AudioMomentMessages {
  audioFetchFailed: string;
  playbackBlocked: string;
  playbackStartFailed: string;
  blobDecodeFailed: string;
  audioLoadFailed: string;
}

const markedSongId = "579";
const markedSongTitle = "genyou yakou";
const markedMomentLabel = "3:16.4";
// Firefox can reduce media timer precision to 100 ms. A programmatic seek may
// therefore be reported at a slightly different time than the value assigned.
const programmaticSeekToleranceSeconds = 0.125;

export function isPlaybackCue(song: CatalogSong, occurrence: CatalogOccurrence): boolean {
  const normalizedEnglishTitle = song.titles.en?.normalize("NFKC").trim().toLocaleLowerCase("en-US");
  const isMarkedSong = song.id === markedSongId || normalizedEnglishTitle === markedSongTitle;
  return isMarkedSong && formatSeconds(occurrence.exactStartSeconds) === markedMomentLabel;
}

export function stopAudio(audio: HTMLAudioElement | null): void {
  if (!audio) return;
  audio.pause();
  try {
    audio.currentTime = 0;
  } catch {
    // An audio element can reject currentTime while it has no media resource.
  }
}

export function clampPlaybackEnd(
  occurrence: CatalogOccurrence,
  durationSeconds: number | null,
): number {
  if (durationSeconds === null || !Number.isFinite(durationSeconds) || durationSeconds <= 0) {
    return Math.max(occurrence.playbackStartSeconds, occurrence.playbackEndSeconds);
  }
  return Math.min(durationSeconds, Math.max(occurrence.playbackStartSeconds, occurrence.playbackEndSeconds));
}

/** Pause exactly at a moment's padded end and return a cleanup function. */
export function monitorPlayback(
  audio: Pick<HTMLAudioElement, "currentTime" | "pause">
    & Partial<Pick<HTMLAudioElement, "addEventListener" | "removeEventListener">>,
  endSeconds: number,
  onFinished: () => void,
  scheduler?: PlaybackScheduler,
  onPositionChange?: (currentTime: number) => void,
): () => void {
  const activeScheduler = scheduler ?? {
    request: (callback: FrameRequestCallback) => window.requestAnimationFrame(callback),
    cancel: (frameId: number) => window.cancelAnimationFrame(frameId),
  };
  let cancelled = false;
  let frameId: number | null = null;
  let timeoutId: number | null = null;

  const cancelScheduledChecks = () => {
    if (frameId !== null) {
      activeScheduler.cancel(frameId);
      frameId = null;
    }
    if (timeoutId !== null) {
      window.clearTimeout(timeoutId);
      timeoutId = null;
    }
  };

  const cleanup = () => {
    if (cancelled) return;
    cancelled = true;
    cancelScheduledChecks();
    audio.removeEventListener?.("timeupdate", handleTimeUpdate);
  };

  const finish = () => {
    if (cancelled) return;
    audio.pause();
    try {
      audio.currentTime = endSeconds;
    } catch {
      // Ignore media implementations that expose a read-only timeline.
    }
    cleanup();
    onFinished();
  };

  const checkPosition = () => {
    if (cancelled) return;
    onPositionChange?.(audio.currentTime);
    if (audio.currentTime >= endSeconds) {
      finish();
      return;
    }
    scheduleFrame();
    scheduleTimeout();
  };

  const frameCallback: FrameRequestCallback = () => {
    frameId = null;
    checkPosition();
  };

  const scheduleFrame = () => {
    if (!cancelled && frameId === null) {
      frameId = activeScheduler.request(frameCallback);
    }
  };

  const timeoutCallback = () => {
    timeoutId = null;
    checkPosition();
  };

  const scheduleTimeout = () => {
    if (cancelled || timeoutId !== null) return;
    const remainingSeconds = endSeconds - audio.currentTime;
    const delayMilliseconds = Number.isFinite(remainingSeconds)
      ? Math.max(50, Math.min(250, remainingSeconds * 1000))
      : 250;
    timeoutId = window.setTimeout(timeoutCallback, delayMilliseconds);
  };

  const handleTimeUpdate = () => checkPosition();
  audio.addEventListener?.("timeupdate", handleTimeUpdate);
  checkPosition();
  return cleanup;
}

export function useAudioMoment(
  song: CatalogSong,
  audioRef: RefObject<HTMLAudioElement | null>,
  callbacks: AudioMomentCallbacks = {},
  messages: AudioMomentMessages,
): AudioMomentState & {
  selectOccurrence: (occurrence: CatalogOccurrence) => void;
  clearMomentSelection: () => void;
  markMetadataReady: () => void;
  handleAudioError: () => void;
  handleAudioPlay: () => void;
  handleAudioPause: () => void;
  handleAudioSeeking: () => void;
} {
  const [loadState, setLoadState] = useState<AudioLoadState>("idle");
  const [source, setSource] = useState<string | null>(null);
  const [sourceMode, setSourceMode] = useState<AudioMomentState["sourceMode"]>("none");
  const [metadataReady, setMetadataReady] = useState(false);
  const [selectedOccurrenceId, setSelectedOccurrenceId] = useState<string | null>(null);
  const [playbackMode, setPlaybackMode] = useState<PlaybackMode>("idle");
  const [isPlaying, setIsPlaying] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const directFallbackTriedRef = useRef(false);
  const playbackMonitorRef = useRef<(() => void) | null>(null);
  const programmaticSeekRef = useRef<number | null>(null);
  const onPlaybackStopRef = useRef(callbacks.onPlaybackStop);
  const onUserPlaybackControlRef = useRef(callbacks.onUserPlaybackControl);
  const onPlaybackTimeChangeRef = useRef(callbacks.onPlaybackTimeChange);
  const messagesRef = useRef(messages);
  const playbackGenerationRef = useRef(0);
  onPlaybackStopRef.current = callbacks.onPlaybackStop;
  onUserPlaybackControlRef.current = callbacks.onUserPlaybackControl;
  onPlaybackTimeChangeRef.current = callbacks.onPlaybackTimeChange;
  messagesRef.current = messages;
  // A new moment stops the current audio first, which can emit a native pause
  // event. Ignore that selection-related pause so the new monitor can start.
  const selectionPauseRef = useRef(false);

  // Keep this separate from isPlaying: a native pause cancels the moment
  // boundary, and a later native play must not recreate it.
  const cancelPlaybackMonitor = useCallback(() => {
    playbackMonitorRef.current?.();
    playbackMonitorRef.current = null;
  }, []);

  const notifyPlaybackStop = useCallback(() => {
    setPlaybackMode("idle");
    setSelectedOccurrenceId(null);
    onPlaybackStopRef.current?.();
  }, []);

  const notifyUserPlaybackControl = useCallback(() => {
    setSelectedOccurrenceId(null);
    onUserPlaybackControlRef.current?.();
  }, []);

  const reportPlaybackTime = useCallback((currentTime: number) => {
    onPlaybackTimeChangeRef.current?.(currentTime);
  }, []);

  const monitorSongPlayback = useCallback((audio: HTMLAudioElement) => {
    playbackMonitorRef.current = monitorPlayback(
      audio,
      Number.POSITIVE_INFINITY,
      () => undefined,
      undefined,
      reportPlaybackTime,
    );
  }, [reportPlaybackTime]);

  useEffect(() => {
    const audio = audioRef.current;
    const controller = new AbortController();
    playbackGenerationRef.current += 1;
    directFallbackTriedRef.current = false;
    selectionPauseRef.current = false;
    programmaticSeekRef.current = null;
    cancelPlaybackMonitor();
    setSelectedOccurrenceId(null);
    setPlaybackMode("idle");
    setIsPlaying(false);
    setMetadataReady(false);
    setErrorMessage(null);

    if (song.status !== "analyzed" || !song.audioUrl) {
      setLoadState("idle");
      setSource(null);
      setSourceMode("none");
      return () => {
        controller.abort();
        stopAudio(audio);
      };
    }

    setLoadState("loading");
    setSource(null);
    setSourceMode("none");

    void fetch(song.audioUrl, {
      signal: controller.signal,
      credentials: "omit",
      referrerPolicy: "no-referrer",
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`The wiki returned HTTP ${response.status}.`);
        }
        return response.blob();
      })
      .then((blob) => {
        if (controller.signal.aborted) return;
        const objectUrl = URL.createObjectURL(blob);
        objectUrlRef.current = objectUrl;
        setSource(objectUrl);
        setSourceMode("blob");
        setLoadState("ready");
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setSource(song.audioUrl);
        setSourceMode("direct");
        setLoadState("fallback");
        setErrorMessage(messagesRef.current.audioFetchFailed);
      });

    return () => {
      controller.abort();
      playbackGenerationRef.current += 1;
      selectionPauseRef.current = false;
      cancelPlaybackMonitor();
      stopAudio(audio);
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
    };
  }, [audioRef, cancelPlaybackMonitor, song.audioUrl, song.status]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!selectedOccurrenceId) return;
    if (song.occurrences.some(({ id }) => id === selectedOccurrenceId)) return;

    selectionPauseRef.current = false;
    programmaticSeekRef.current = null;
    playbackGenerationRef.current += 1;
    cancelPlaybackMonitor();
    stopAudio(audio);
    setSelectedOccurrenceId(null);
    setIsPlaying(false);
    notifyPlaybackStop();
  }, [audioRef, cancelPlaybackMonitor, notifyPlaybackStop, selectedOccurrenceId, song.occurrences]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const handleEnded = () => {
      playbackGenerationRef.current += 1;
      cancelPlaybackMonitor();
      setIsPlaying(false);
      notifyPlaybackStop();
    };
    audio.addEventListener("ended", handleEnded);
    return () => audio.removeEventListener("ended", handleEnded);
  }, [audioRef, cancelPlaybackMonitor, notifyPlaybackStop]);

  const selectOccurrence = (occurrence: CatalogOccurrence) => {
    const audio = audioRef.current;
    if (!audio || !metadataReady) return;
    const playbackGeneration = playbackGenerationRef.current + 1;
    playbackGenerationRef.current = playbackGeneration;
    cancelPlaybackMonitor();
    selectionPauseRef.current = true;
    programmaticSeekRef.current = null;
    // Rewinding before the new seek can queue a stale seeking event that
    // arrives after playback starts and looks like native user input.
    audio.pause();
    setSelectedOccurrenceId(occurrence.id);
    setPlaybackMode("moment");
    setErrorMessage(null);
    const end = clampPlaybackEnd(occurrence, Number.isFinite(audio.duration) ? audio.duration : song.durationSeconds);
    const start = Math.min(occurrence.playbackStartSeconds, Math.max(0, end));
    try {
      programmaticSeekRef.current = start;
      audio.currentTime = start;
      const playResult = audio.play();
      playbackMonitorRef.current = monitorPlayback(
        audio,
        end,
        () => {
          if (playbackGenerationRef.current !== playbackGeneration) return;
          playbackMonitorRef.current = null;
          setIsPlaying(false);
          notifyPlaybackStop();
        },
        undefined,
        reportPlaybackTime,
      );
      if (playResult) {
        void playResult.then(
          () => {
            if (playbackGenerationRef.current !== playbackGeneration) return;
            selectionPauseRef.current = false;
          },
          () => {
            if (playbackGenerationRef.current !== playbackGeneration) return;
            selectionPauseRef.current = false;
            cancelPlaybackMonitor();
            setIsPlaying(false);
            notifyPlaybackStop();
            setErrorMessage(messagesRef.current.playbackBlocked);
          },
        );
      } else {
        selectionPauseRef.current = false;
      }
      setIsPlaying(true);
    } catch {
      if (playbackGenerationRef.current !== playbackGeneration) return;
      selectionPauseRef.current = false;
      programmaticSeekRef.current = null;
      cancelPlaybackMonitor();
      setIsPlaying(false);
      notifyPlaybackStop();
      setErrorMessage(messagesRef.current.playbackStartFailed);
    }
  };

  const clearMomentSelection = useCallback(() => {
    if (!selectedOccurrenceId) return;
    const audio = audioRef.current;
    playbackGenerationRef.current += 1;
    selectionPauseRef.current = false;
    programmaticSeekRef.current = null;
    cancelPlaybackMonitor();
    if (audio && isPlaying) {
      setPlaybackMode("song");
      notifyUserPlaybackControl();
      monitorSongPlayback(audio);
    } else {
      setIsPlaying(false);
      notifyPlaybackStop();
    }
  }, [audioRef, cancelPlaybackMonitor, isPlaying, monitorSongPlayback, notifyPlaybackStop, notifyUserPlaybackControl, selectedOccurrenceId]);

  const handleAudioError = () => {
    if (song.audioUrl && sourceMode === "blob" && !directFallbackTriedRef.current) {
      directFallbackTriedRef.current = true;
      playbackGenerationRef.current += 1;
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
      setSource(song.audioUrl);
      setSourceMode("direct");
      setLoadState("fallback");
      setMetadataReady(false);
      selectionPauseRef.current = false;
      programmaticSeekRef.current = null;
      cancelPlaybackMonitor();
      setIsPlaying(false);
      notifyPlaybackStop();
      setErrorMessage(messagesRef.current.blobDecodeFailed);
      return;
    }
    playbackGenerationRef.current += 1;
    setLoadState("error");
    selectionPauseRef.current = false;
    programmaticSeekRef.current = null;
    cancelPlaybackMonitor();
    setIsPlaying(false);
    notifyPlaybackStop();
    setErrorMessage(messagesRef.current.audioLoadFailed);
  };

  return {
    loadState,
    source,
    sourceMode,
    metadataReady,
    selectedOccurrenceId,
    playbackMode,
    isPlaying,
    errorMessage,
    selectOccurrence,
    clearMomentSelection,
    markMetadataReady: () => setMetadataReady(true),
    handleAudioError,
    handleAudioPlay: () => {
      if (selectionPauseRef.current) {
        selectionPauseRef.current = false;
        setPlaybackMode("moment");
      } else {
        playbackGenerationRef.current += 1;
        programmaticSeekRef.current = null;
        cancelPlaybackMonitor();
        setPlaybackMode("song");
        notifyUserPlaybackControl();
        const audio = audioRef.current;
        if (audio) monitorSongPlayback(audio);
      }
      setIsPlaying(true);
    },
    handleAudioPause: () => {
      if (selectionPauseRef.current) {
        // Ignore the pause emitted while switching moments. The following
        // programmatic play event clears this guard.
      } else {
        playbackGenerationRef.current += 1;
        programmaticSeekRef.current = null;
        cancelPlaybackMonitor();
        notifyPlaybackStop();
      }
      setPlaybackMode("idle");
      setIsPlaying(false);
    },
    handleAudioSeeking: () => {
      const audio = audioRef.current;
      const programmaticSeek = programmaticSeekRef.current;
      if (
        audio
        && programmaticSeek !== null
        && Math.abs(audio.currentTime - programmaticSeek) <= programmaticSeekToleranceSeconds
      ) {
        programmaticSeekRef.current = null;
        return;
      }
      if (selectionPauseRef.current) return;
      programmaticSeekRef.current = null;
      playbackGenerationRef.current += 1;
      cancelPlaybackMonitor();
      // A user seek hands control back from a clicked moment. If that moment
      // was playing, wait for an explicit native play before entering the
      // live whole-song highlighting mode.
      if (playbackMode === "moment") setPlaybackMode("idle");
      notifyUserPlaybackControl();
    },
  };
}
