/** Mirrors backend lifecycle JSON (snake_case). */

export type TaskStatus =
  | 'draft'
  | 'planning'
  | 'queued'
  | 'running'
  | 'awaiting_approval'
  | 'blocked'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'archived';

export type TaskPhase =
  | 'intake'
  | 'planning'
  | 'data_inspection'
  | 'experimenting'
  | 'evaluation'
  | 'artifact_review'
  | 'release';

export interface TaskSummary {
  id: string;
  owner_user_id: string;
  source_session_id: string | null;
  title: string;
  goal: string;
  status: string;
  phase: string;
  priority: number;
  risk_level: string;
  autonomy_mode: string;
  current_run_id: string | null;
  latest_plan_revision_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExperimentRun {
  id: string;
  task_id: string;
  parent_run_id: string | null;
  run_type: string;
  status: string;
  model_name: string | null;
  dataset_artifact_id: string | null;
  model_artifact_id: string | null;
  code_version: string | null;
  executor_type: string | null;
  repro_command: string | null;
  config: Record<string, unknown>;
  metrics: Record<string, unknown>;
  summary: Record<string, unknown>;
  cost: Record<string, unknown>;
  failure_reason: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface Job {
  id: string;
  task_id: string;
  run_id: string | null;
  queue_name: string;
  job_type: string;
  status: string;
  priority: number;
  idempotency_key: string | null;
  executor_type: string | null;
  payload: Record<string, unknown>;
  result: Record<string, unknown>;
  checkpoint_uri: string | null;
  attempt_count: number;
  max_attempts: number;
  next_attempt_at: string | null;
  lease_owner: string | null;
  lease_expires_at: string | null;
  last_error: string | null;
  created_by: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface Artifact {
  id: string;
  task_id: string;
  run_id: string | null;
  job_id: string | null;
  type: string;
  name: string;
  version: string | null;
  uri: string;
  storage_backend: string;
  content_type: string | null;
  sha256: string | null;
  size_bytes: number | null;
  metadata: Record<string, unknown>;
  created_by: string | null;
  created_at: string;
}

export interface TaskDetail extends TaskSummary {
  constraints: Record<string, unknown>;
  acceptance: Record<string, unknown>;
  started_at: string | null;
  finished_at: string | null;
  runs: ExperimentRun[];
  jobs: Job[];
  artifacts: Artifact[];
}
