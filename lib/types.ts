export type ApiEnvelope<T> = {
  ok: boolean;
  data: T;
  message?: string;
};

export type SourceSnippet = {
  title: string;
  source_file: string;
  source_type: string;
  score: number;
  preview: string;
};

export type ChatResponse = {
  answer: string;
  sources: SourceSnippet[];
  provider: string;
  log_id: number;
};

export type ChatStreamProvider = "faq-fast-path" | "qwen-stream" | "local-retrieval";
export type ChatStreamEventName = "meta" | "delta" | "narration" | "done" | "error";

export type ChatStreamEvent = {
  type?: ChatStreamEventName;
  event?: ChatStreamEventName;
  provider?: ChatStreamProvider;
  sources?: SourceSnippet[];
  text?: string;
  delta?: string;
  answer?: string;
  log_id?: number;
  message?: string;
  data?: ChatResponse;
};

export type DigitalHumanDriver = {
  mode: "real_video" | "demo_video" | "audio_2d";
  label: string;
  claim: string;
  status: string;
  provider?: string;
  video_playable: boolean;
  claim_real_lipsync: boolean;
  requires_external_service?: boolean;
  acceptance?: string;
  message?: string;
};

export type RouteStep = {
  index: number;
  spot_id: string;
  name: string;
  reason: string;
  location: string;
  opening: string;
  source_file: string;
  map_x?: number;
  map_y?: number;
};

export type RoutePlan = {
  title: string;
  mood: string;
  interest: string;
  image_url: string;
  steps: RouteStep[];
  source_files: string[];
  guide_title?: string;
  note: string;
};

export type LocationSource = "gps" | "manual" | "camera" | "none";
export type LocationStatus =
  | "idle" | "requesting" | "confirmed" | "uncertain"
  | "denied" | "unavailable" | "stale";
export type LocationDemoScenario = "weak" | "denied" | "timeout";
export type LocationAccuracyBand = "precise" | "approximate" | "weak" | "unknown";
export type CoordinateSystem = "WGS84" | "GCJ02" | "BD09";

export type VisitorLocationState = {
  source: LocationSource;
  status: LocationStatus;
  accuracy_m: number | null;
  current_spot_id: string | null;
  observed_at: number | null;
};

export type GeoPoint = { latitude: number; longitude: number };
export type LocationObservation = GeoPoint & {
  accuracy_m: number;
  observed_at: number;
};
export type SpotCoordinate = GeoPoint & {
  spot_id: string;
  coordinate_system: CoordinateSystem;
  arrival_radius_m: number;
  source: string;
};
export type RoutePlanRequest = { interest: string; start_spot_id?: string };

export type FAQ = {
  id: number;
  question: string;
  answer: string;
  source_title: string;
  source_file: string;
  tags: string[];
};

export type DashboardMetrics = {
  source_file: string;
  total_rows: number;
  unique_tourists: number;
  matching_lingshan_rows: number;
  matching_wuxi_rows?: number;
  data_scope_note: string;
  top_attractions: [string, number][];
  attraction_types: [string, number][];
  monthly_visits: [string, number][];
  gender_distribution: [string, number][];
  age_buckets: [string, number][];
  satisfaction_distribution: [string, number][];
  average_costs: Record<string, number>;
  average_stay_by_type: [string, number][];
  updated_at?: string;
  live_questions?: number;
  live_visitors?: number;
  today_questions?: number;
  today_visitors?: number;
  week_questions?: number;
  week_visitors?: number;
  live_hot_questions?: [string, number][];
  live_spot_distribution?: [string, number][];
  live_keyword_summary?: [string, number][];
  live_question_groups?: QuestionGroup[];
  live_date_distribution?: [string, number][];
  live_feeling_distribution?: [string, number][];
  live_average_rating?: number | null;
};

export type Health = {
  ok: boolean;
  qwen_configured: boolean;
  vivo_configured: boolean;
  vivo_app_id_configured?: boolean;
  asr_provider?: string;
  tts_provider?: string;
  asr_ready?: boolean;
  tts_ready?: boolean;
  asr_effective_provider?: string;
  tts_effective_provider?: string;
  opentalking_configured: boolean;
  opentalking_ready?: boolean;
  opentalking_status?: string;
  opentalking_model?: string;
  opentalking_error?: string;
  demo_video_ready?: boolean;
  demo_video_url?: string;
  demo_video_label?: string;
  vector_backend: string;
  counts: Record<string, number>;
};

export type LogItem = {
  id: number;
  question: string;
  answer: string;
  provider: string;
  created_at: string;
  visitor_id?: string | null;
  user_agent?: string | null;
  spot_name?: string | null;
  rating?: number | null;
  feeling?: string | null;
  note?: string | null;
  sources: SourceSnippet[];
};

export type QuestionGroup = {
  keyword: string;
  count: number;
  log_ids: number[];
  questions: string[];
};

export type LogSummary = {
  total_questions: number;
  unique_visitors: number;
  rated_questions: number;
  average_rating: number | null;
  date_distribution: [string, number][];
  spot_distribution: [string, number][];
  feeling_distribution: [string, number][];
  keyword_summary: [string, number][];
  question_groups: QuestionGroup[];
};

export type SourceDetail = {
  source: { id: number; name: string; file_type: string; checksum: string; imported_at: string; records_count: number };
  attractions: {
    spot_id: string;
    name: string;
    location?: string;
    core_function?: string;
    highlights?: string;
    opening?: string;
  }[];
  chunks: { id: number; title: string; source_type: string; preview: string }[];
  faqs: { question: string; answer: string; source_title: string }[];
};

export type DigitalHumanConfig = {
  id?: number;
  name: string;
  voice: string;
  persona: string;
  avatar_mode: string;
  opentalking_base_url: string;
  updated_at?: string;
};
