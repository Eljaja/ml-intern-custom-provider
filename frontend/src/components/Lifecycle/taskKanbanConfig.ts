/** Kanban columns: groups lifecycle task statuses for the board view. */

export interface TaskKanbanColumn {
  id: string;
  title: string;
  /** Human hint under the title */
  hint: string;
  statuses: readonly string[];
  /** Applied when a card is dropped here from another column */
  dropStatus: string;
}

export const TASK_KANBAN_COLUMNS: TaskKanbanColumn[] = [
  {
    id: 'backlog',
    title: 'Backlog',
    hint: 'Draft & planning',
    statuses: ['draft', 'planning'],
    dropStatus: 'planning',
  },
  {
    id: 'ready',
    title: 'Ready',
    hint: 'Queued to run',
    statuses: ['queued'],
    dropStatus: 'queued',
  },
  {
    id: 'active',
    title: 'Active',
    hint: 'Running & approvals',
    statuses: ['running', 'awaiting_approval'],
    dropStatus: 'running',
  },
  {
    id: 'blocked',
    title: 'Blocked',
    hint: 'Needs attention',
    statuses: ['blocked'],
    dropStatus: 'blocked',
  },
  {
    id: 'done',
    title: 'Done',
    hint: 'Succeeded',
    statuses: ['succeeded'],
    dropStatus: 'succeeded',
  },
  {
    id: 'closed',
    title: 'Closed',
    hint: 'Failed / cancelled / archived',
    statuses: ['failed', 'cancelled', 'archived'],
    dropStatus: 'cancelled',
  },
];

const STATUS_TO_COLUMN = new Map<string, string>();
for (const col of TASK_KANBAN_COLUMNS) {
  for (const s of col.statuses) {
    STATUS_TO_COLUMN.set(s, col.id);
  }
}

export function kanbanColumnIdForStatus(status: string): string {
  return STATUS_TO_COLUMN.get(status) ?? 'backlog';
}

export function kanbanColumnById(id: string): TaskKanbanColumn | undefined {
  return TASK_KANBAN_COLUMNS.find((c) => c.id === id);
}
