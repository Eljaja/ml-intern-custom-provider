/**
 * Bridge chat sessions + agent plan tool → /api/v2 lifecycle tasks (Kanban).
 */
import * as api from '@/api/lifecycle';
import { useSessionStore } from '@/store/sessionStore';
import { logger } from '@/utils/logger';

export const AGENT_SYNC = '_agent' as const;

type PlanRow = { id: string; content: string; status: string };

function mapPlanStatusToTaskStatus(s: string): string {
  const v = (s || '').toLowerCase();
  if (v === 'completed') return 'succeeded';
  if (v === 'in_progress' || v === 'in-progress') return 'running';
  return 'planning';
}

/**
 * Create the durable root task for this chat on first user message (one per session).
 */
export async function ensureChatRootLifecycleTask(sessionId: string, goal: string): Promise<string | null> {
  const snap = useSessionStore.getState().sessions.find((s) => s.id === sessionId);
  if (snap?.lifecycleRootTaskId) return snap.lifecycleRootTaskId;

  const line = goal.split('\n')[0]?.trim() || 'Chat task';
  const title = line.slice(0, 120);
  try {
    const task = await api.createTask({
      title,
      goal: goal.slice(0, 32000),
      source_session_id: sessionId,
      status: 'planning',
      phase: 'intake',
      constraints: {
        [AGENT_SYNC]: { kind: 'chat_root', session_id: sessionId },
      },
    });
    useSessionStore.getState().setLifecycleRootTask(sessionId, task.id);
    return task.id;
  } catch (e) {
    logger.error('ensureChatRootLifecycleTask failed', e);
    return null;
  }
}

/**
 * Upsert one Kanban task per agent plan row; archive steps removed from the latest plan.
 */
export async function syncAgentPlanToLifecycle(sessionId: string, plan: PlanRow[]): Promise<void> {
  if (!plan.length) return;

  const session = useSessionStore.getState().sessions.find((s) => s.id === sessionId);
  const rootId = session?.lifecycleRootTaskId;
  if (!rootId) return;

  const stepMap: Record<string, string> = { ...(session.lifecyclePlanStepTasks ?? {}) };
  const nextIds = new Set(plan.map((p) => p.id));

  for (const stepId of Object.keys(stepMap)) {
    if (!nextIds.has(stepId)) {
      const taskId = stepMap[stepId];
      delete stepMap[stepId];
      try {
        await api.patchTask(taskId, { status: 'archived' });
      } catch {
        /* already gone or forbidden */
      }
    }
  }

  for (const item of plan) {
    const status = mapPlanStatusToTaskStatus(item.status);
    const content = (item.content || '').slice(0, 32000);
    const title = (content.split('\n')[0]?.trim() || 'Plan step').slice(0, 512);
    const constraints = {
      [AGENT_SYNC]: {
        kind: 'plan_step',
        session_id: sessionId,
        root_task_id: rootId,
        step_id: item.id,
      },
    };

    const existingId = stepMap[item.id];
    try {
      if (existingId) {
        await api.patchTask(existingId, { title, goal: content, status });
      } else {
        const t = await api.createTask({
          title: title.slice(0, 120),
          goal: content,
          source_session_id: sessionId,
          status,
          phase: 'planning',
          constraints,
        });
        stepMap[item.id] = t.id;
      }
    } catch (e) {
      logger.error('syncAgentPlanToLifecycle step failed', item.id, e);
    }
  }

  useSessionStore.getState().setLifecyclePlanStepTasks(sessionId, stepMap);
}
