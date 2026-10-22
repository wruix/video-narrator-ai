// 与后端 API 对应的类型定义

export interface ProviderSpec {
  id: string;
  name: string;
  kind: "vision" | "text" | "tts";
  default_model: string;
  models: string[];
  requires_key: boolean;
  key_hint: string;
  docs: string;
  native_video: boolean;
  native_audio: boolean;
  vision: boolean;
  note: string;
  capabilities: string[];
  key_present?: boolean;
  key_source?: string;
  key_masked?: string;
}

export interface Voice {
  id: string;
  name: string;
  gender: string;
  tone: string;
  provider: string;
  tags: string[];
}

export interface StyleOption {
  id: string;
  name: string;
  name_en?: string;
  desc: string;
  desc_en?: string;
  sample: string;
}

export interface AspectOption {
  id: string;
  name: string;
  name_en?: string;
}

export interface AsrOption {
  id: string;
  name: string;
  name_en?: string;
}

export interface NarrationLanguage {
  id: string;
  name: string;
  name_en?: string;
}

export interface ProviderCatalog {
  vision: ProviderSpec[];
  text: ProviderSpec[];
  tts: ProviderSpec[];
  voices: Voice[];
  styles: StyleOption[];
  aspects: AspectOption[];
  asr: AsrOption[];
  narration_languages?: NarrationLanguage[];
  emotions: string[];
  emotions_en?: string[];
  native_video: string[];
}

export interface Shot {
  id: number;
  index: number;
  start: number;
  end: number;
  duration: number;
  visual: string;
  narration: string;
  dialogue: string;
  emotion: string;
  speed: string;
  frames: string[];
  tts_duration: number;
  locked: boolean;
  updated_at: string | null;
}

export type ProjectStatus =
  | "created"
  | "uploaded"
  | "analyzing"
  | "awaiting_review"
  | "approved"
  | "rendering"
  | "completed"
  | "failed";

export interface Project {
  id: number;
  name: string;
  status: ProjectStatus;
  video_filename: string | null;
  video_size: number;
  duration: number;
  width: number;
  height: number;
  fps: number;
  has_audio: boolean;
  style: string;
  language: string;
  aspect: string;
  analysis_model: string;
  script_model: string;
  asr_provider: string;
  tts_provider: string;
  voice_id: string;
  voice_speed: string;
  voice_emotion: string;
  bgm_volume: number;
  subtitle_enabled: boolean;
  burn_subtitles: boolean;
  user_notes: string;
  error: string | null;
  created_at: string | null;
  updated_at: string | null;
  shots?: Shot[];
  jobs?: Job[];
  renders?: RenderItem[];
}

export interface Job {
  id: number;
  project_id: number;
  kind: string;
  stage: string;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  progress: number;
  message: string;
  detail: string;
  error: string | null;
  created_at: string | null;
  finished_at: string | null;
}

export interface RenderItem {
  id: number;
  project_id: number;
  duration: number;
  size: number;
  width: number;
  height: number;
  has_subtitle: boolean;
  created_at: string | null;
}

export interface HealthInfo {
  status: string;
  version: string;
  ffmpeg: string | null;
  ffprobe: string | null;
  ffmpeg_error?: string;
  ffprobe_error?: string;
}

export interface KeyInfo {
  provider: string;
  source: string;
  present: boolean;
  masked: string;
}

export interface UsageItem {
  id: number;
  project_id: number | null;
  provider: string;
  model: string;
  kind: string;
  units: number;
  unit_name: string;
  note: string;
  created_at: string | null;
}

export interface UsageSummary {
  items: UsageItem[];
  total_tokens: number;
  total_seconds: number;
}
