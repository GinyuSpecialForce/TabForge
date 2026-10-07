/** Shared types between the API routes and the UI. */

export type JobStatus = "queued" | "running" | "done" | "failed";

/**
 * Pipeline stages in order — the single source of truth for the progress
 * stepper. Worker parity is enforced by worker/tests/test_contract.py.
 */
export const STAGES = [
  "downloading",
  "separating",
  "transcribing",
  "solving",
  "emitting",
] as const;
export type PipelineStage = (typeof STAGES)[number];

export type JobStage = "queued" | PipelineStage | "done" | "failed";

export interface JobOptions {
  tuning: string;
  capo: number;
  transpose: number;
  simplify: "none" | "top" | "roots";
  bpm?: number | null;
  max_seconds?: number;
  /** false = skip Demucs isolation and transcribe the full mix (fast mode) */
  separate?: boolean;
}

export interface JobResult {
  artifacts?: string[];
  warnings?: string[];
  noteCount?: number;
  droppedNotes?: number;
  bpm?: number;
  tuning?: number[];
  capo?: number;
  measureCount?: number;
  /** seconds spent per pipeline stage (written by the worker) */
  timings?: Record<string, number>;
}

export interface Job {
  id: string;
  youtube_url: string;
  status: JobStatus;
  stage: JobStage;
  progress: number;
  error: string | null;
  title: string | null;
  artist: string | null;
  duration_seconds: number | null;
  thumbnail_url: string | null;
  options: JobOptions;
  result: JobResult;
  created_at: string;
  updated_at: string;
}

/** Shape of the tab.json artifact written by the worker. */
export interface TabNoteJson {
  start: number;
  duration: number;
  pitch: number;
  string: number;
  fret: number;
  amplitude: number;
}

export interface ChordJson {
  start: number;
  end: number;
  name: string;
}

export interface TabJson {
  title: string;
  artist: string;
  bpm: number;
  tuning: number[];
  capo: number;
  beatsPerMeasure: number;
  beatValue: number;
  maxFret: number;
  droppedNotes: number;
  chords: ChordJson[];
  notes: TabNoteJson[];
}

export const TUNING_PRESETS: Record<string, string> = {
  standard: "Standard (E A D G B E)",
  drop_d: "Drop D",
  half_step_down: "Half step down",
  d_standard: "D standard",
  drop_c: "Drop C",
  open_g: "Open G",
};

export const STAGE_LABELS: Record<JobStage, string> = {
  queued: "Queued",
  downloading: "Downloading audio",
  separating: "Isolating guitar",
  transcribing: "Transcribing notes",
  solving: "Solving fingerings",
  emitting: "Writing tab files",
  done: "Done",
  failed: "Failed",
};
