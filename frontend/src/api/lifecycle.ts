import { apiFetch } from '@/utils/api';
import type { Artifact, ExperimentRun, Job, TaskDetail, TaskSummary } from '@/types/lifecycle';

function detailMessage(detail: unknown): string {
  if (detail == null) return 'Request failed';
  if (typeof detail === 'string') return detail;
  if (typeof detail === 'object' && detail !== null && ('message' in detail || 'error' in detail)) {
    const o = detail as { message?: string; error?: string };
    return o.message || o.error || JSON.stringify(detail);
  }
  return JSON.stringify(detail);
}

export async function assertOk(res: Response): Promise<void> {
  if (res.ok) return;
  let msg = `${res.status}`;
  try {
    const j = await res.json();
    msg = detailMessage(j.detail ?? j);
  } catch {
    /* ignore */
  }
  throw new Error(msg);
}

export async function fetchTasks(): Promise<TaskSummary[]> {
  const res = await apiFetch('/api/v2/tasks');
  await assertOk(res);
  return res.json();
}

export async function fetchTaskDetail(taskId: string): Promise<TaskDetail> {
  const res = await apiFetch(`/api/v2/tasks/${encodeURIComponent(taskId)}`);
  await assertOk(res);
  return res.json();
}

export interface CreateTaskBody {
  title?: string;
  goal: string;
  source_session_id?: string | null;
  phase?: string;
  status?: string;
  priority?: number;
  risk_level?: string;
  autonomy_mode?: string;
  constraints?: Record<string, unknown>;
  acceptance?: Record<string, unknown>;
}

export async function createTask(body: CreateTaskBody): Promise<TaskSummary> {
  const res = await apiFetch('/api/v2/tasks', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  await assertOk(res);
  return res.json();
}

export interface PatchTaskBody {
  title?: string;
  goal?: string;
  status?: string;
  phase?: string;
  priority?: number;
  risk_level?: string;
  autonomy_mode?: string;
  constraints?: Record<string, unknown>;
  acceptance?: Record<string, unknown>;
  current_run_id?: string | null;
}

export async function patchTask(taskId: string, body: PatchTaskBody): Promise<TaskSummary> {
  const res = await apiFetch(`/api/v2/tasks/${encodeURIComponent(taskId)}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
  await assertOk(res);
  return res.json();
}

export async function createRun(
  taskId: string,
  body: {
    run_type?: string;
    status?: string;
    parent_run_id?: string | null;
    model_name?: string | null;
    config?: Record<string, unknown>;
    metrics?: Record<string, unknown>;
  },
): Promise<ExperimentRun> {
  const res = await apiFetch(`/api/v2/tasks/${encodeURIComponent(taskId)}/runs`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
  await assertOk(res);
  return res.json();
}

export async function createJob(
  taskId: string,
  body: {
    run_id?: string | null;
    queue_name?: string;
    job_type: string;
    status?: string;
    priority?: number;
    idempotency_key?: string | null;
    executor_type?: string | null;
    payload?: Record<string, unknown>;
    max_attempts?: number;
  },
): Promise<Job> {
  const res = await apiFetch(`/api/v2/tasks/${encodeURIComponent(taskId)}/jobs`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
  await assertOk(res);
  return res.json();
}

export async function createArtifact(
  taskId: string,
  body: {
    run_id?: string | null;
    job_id?: string | null;
    type: string;
    name?: string;
    uri: string;
    storage_backend?: string;
    sha256?: string | null;
    metadata?: Record<string, unknown>;
  },
): Promise<Artifact> {
  const res = await apiFetch(`/api/v2/tasks/${encodeURIComponent(taskId)}/artifacts`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
  await assertOk(res);
  return res.json();
}
