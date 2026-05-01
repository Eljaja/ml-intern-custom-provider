export const TASK_STATUSES = [
  'draft',
  'planning',
  'queued',
  'running',
  'awaiting_approval',
  'blocked',
  'succeeded',
  'failed',
  'cancelled',
  'archived',
] as const;

export const TASK_PHASES = [
  'intake',
  'planning',
  'data_inspection',
  'experimenting',
  'evaluation',
  'artifact_review',
  'release',
] as const;

export const RUN_TYPES = [
  'research',
  'training',
  'evaluation',
  'sweep',
  'deployment_candidate',
  'benchmark',
] as const;
