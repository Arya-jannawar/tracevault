/* TypeScript mirrors of the TraceVault API contract (docs/api-contract.md). */

export interface User {
  username: string;
  role: string;
}

export interface ErrorEnvelope {
  code: string;
  message: string;
  request_id?: string | null;
}

/* ---------------- documents ---------------- */

export interface DocumentOut {
  id: string;
  title: string;
  state: string;
  created_at: string;
  updated_at: string;
  version_count: number;
  chunk_count: number;
  summary_count: number;
  answer_count: number;
  cache_count: number;
}

export interface DocumentVersionOut {
  id: string;
  version: number;
  source_type: string;
  filename: string;
  checksum: string;
  content_state: string;
  created_at: string;
}

export interface DocumentDetail extends DocumentOut {
  versions: DocumentVersionOut[];
  coverage_notes: string[];
}

export interface ChunkOut {
  artifact_id: string;
  index: number;
  start: number;
  end: number;
  text: string | null;
  lifecycle_state: string;
}

export type CoverageWarning = string | Record<string, unknown>;

export interface DeletionImpact {
  document_id: string;
  affected_count: number;
  affected_by_type: Record<string, number>;
  coverage_warnings: CoverageWarning[];
  scope_exclusions: string[];
}

/* ---------------- RAG ---------------- */

export interface Citation {
  label: string;
  chunk_artifact_id: string;
  document_id: string;
  score: number;
  snippet: string;
}

export type RagMode = 'llm' | 'extractive' | 'deterministic' | string;

export interface RagQueryResponse {
  answer: string;
  answer_note: string | null;
  citations: Citation[];
  cache_hit: boolean;
  cache_type: 'exact' | 'semantic' | null;
  mode: RagMode;
  model: string;
  latency_ms: number;
  answer_artifact_id: string | null;
}

export interface ClaimOut {
  id: string;
  idx: number;
  text: string | null;
  status: string;
}

export interface SummaryOut {
  artifact_id: string;
  document_id: string;
  summary_version: number;
  content: string | null;
  lifecycle_state: string;
  claims: ClaimOut[];
}

export interface RepairJob {
  job_id: string;
  status: string;
  attempts?: number;
  last_error?: string | null;
}

export interface RepairCandidateOut {
  summary_artifact_id: string;
  document_id: string;
  summary_version: number;
  total_claims: number;
  surviving_supports: number;
  surviving_source_docs: string[];
  repairable: boolean;
}

/* ---------------- provenance ---------------- */

export type ProvenanceNodeType =
  | 'document_version'
  | 'chunk'
  | 'vector'
  | 'summary'
  | 'answer'
  | 'cache_entry'
  | string;

export interface ProvenanceNode {
  id: string;
  type: ProvenanceNodeType;
  document_id: string | null;
  document_version_id: string | null;
  version: number;
  lifecycle_state: string;
  provenance_status: string;
  meta: Record<string, unknown>;
}

export interface ProvenanceEdge {
  parent: string;
  child: string;
  relationship: string;
  source_version: number;
}

export interface ProvenanceGraph {
  nodes: ProvenanceNode[];
  edges: ProvenanceEdge[];
}

export interface DependencyRef {
  id: string;
  type: string;
  state: string;
  document_id?: string | null;
}

export interface DependencyTable {
  artifact: DependencyRef;
  dependencies: DependencyRef[];
  dependants: DependencyRef[];
}

/* ---------------- deletion center ---------------- */

export type DeletionState =
  | 'ACCEPTED'
  | 'FENCED'
  | 'DISCOVERING'
  | 'INVALIDATING'
  | 'REMOVING'
  | 'VERIFYING'
  | 'COMPLETED'
  | 'RETRY_PENDING'
  | 'INCOMPLETE'
  | 'FAILED';

export interface DeletionStepOut {
  step: string;
  status: string;
  attempts: number;
  error_code: string | null;
  detail: Record<string, unknown> | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface VerificationCheckOut {
  check_type: string;
  target_label: string;
  result: string;
  error_code: string | null;
  scope: Record<string, unknown>;
  started_at: string | null;
  finished_at: string | null;
}

export interface DeletionRequestOut {
  id: string;
  document_id: string;
  state: DeletionState;
  fence_epoch: number;
  repair_enabled: boolean;
  accepted_at: string;
  started_at: string | null;
  finished_at: string | null;
  failure_reason: string | null;
  report: DeletionReport | null;
}

export interface DeletionReport {
  affected_count?: number;
  affected_ids?: string[];
  affected_by_type?: Record<string, string[]>;
  coverage_warnings?: CoverageWarning[];
  scope_exclusions?: string[];
  discovered_at?: string;
  latency?: number;
  [key: string]: unknown;
}

export interface DeletionRequestDetail extends DeletionRequestOut {
  steps: DeletionStepOut[];
  verification: VerificationCheckOut[];
}

/* ---------------- audit ---------------- */

export interface AuditEventOut {
  id: number;
  type: string;
  actor: string;
  deletion_request_id: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

/* ---------------- evaluation ---------------- */

export type EvalBaseline =
  | 'vector_only'
  | 'broad_conservative'
  | 'provenance_conservative'
  | 'provenance_repair';

export interface ScenarioOut {
  name: string;
  description: string;
}

export interface EvaluationRunOut {
  id: string;
  scenario: string;
  baseline: EvalBaseline;
  seed: number;
  status: 'queued' | 'running' | 'completed' | 'failed' | string;
  metrics: Record<string, unknown> | null;
  counts: Record<string, number> | null;
  config: Record<string, unknown>;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

/* ---------------- system ---------------- */

export interface Capabilities {
  system: string;
  academic_title: string;
  tagline: string;
  is_research_prototype: true;
  operating_modes: Record<string, unknown>;
  embedding: Record<string, unknown>;
  llm: Record<string, unknown>;
  flags: {
    selective_repair?: boolean;
    semantic_cache?: boolean;
    pending_jobs?: number;
    [key: string]: unknown;
  };
  connectors: Record<string, boolean>;
  boundary: string[];
}

export interface HealthOut {
  status: 'ok' | 'degraded';
  checks: Record<string, boolean | string>;
}

/* ---------------- deletion pipeline helpers ---------------- */

export const DELETION_STEP_ORDER = [
  'FENCED',
  'DISCOVERING',
  'INVALIDATING',
  'REMOVING',
  'VERIFYING',
] as const;

/** States that are still moving — safe to poll aggressively. */
export const TRANSITIONAL_STATES: readonly DeletionState[] = [
  'ACCEPTED',
  'FENCED',
  'DISCOVERING',
  'INVALIDATING',
  'REMOVING',
  'VERIFYING',
];

export const FAILED_STATES: readonly DeletionState[] = [
  'RETRY_PENDING',
  'INCOMPLETE',
  'FAILED',
];

export function isTransitional(state: string | null | undefined): boolean {
  return !!state && (TRANSITIONAL_STATES as readonly string[]).includes(state);
}
