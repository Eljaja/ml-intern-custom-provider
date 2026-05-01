import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Box,
  Typography,
  Button,
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Card,
  CardContent,
  Skeleton,
  InputAdornment,
  Chip,
  Snackbar,
  Alert,
  Fab,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import RefreshIcon from '@mui/icons-material/Refresh';
import SearchIcon from '@mui/icons-material/Search';
import DragIndicatorIcon from '@mui/icons-material/DragIndicator';
import ViewListIcon from '@mui/icons-material/ViewList';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import * as api from '@/api/lifecycle';
import type { TaskSummary } from '@/types/lifecycle';
import { TASK_KANBAN_COLUMNS, kanbanColumnIdForStatus, kanbanColumnById } from '@/components/Lifecycle/taskKanbanConfig';

const DND_TYPE = 'application/x-ml-task-id';

function formatShort(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch {
    return iso;
  }
}

function phaseChipColor(phase: string): 'default' | 'primary' | 'secondary' | 'success' | 'warning' | 'error' {
  if (phase === 'experimenting' || phase === 'evaluation') return 'primary';
  if (phase === 'release') return 'success';
  if (phase === 'planning' || phase === 'intake') return 'secondary';
  return 'default';
}

function statusChipColor(
  status: string,
): 'default' | 'primary' | 'secondary' | 'success' | 'warning' | 'error' {
  if (status === 'succeeded') return 'success';
  if (status === 'failed' || status === 'cancelled') return 'error';
  if (status === 'running' || status === 'queued') return 'primary';
  if (status === 'awaiting_approval' || status === 'blocked') return 'warning';
  if (status === 'archived') return 'default';
  return 'default';
}

export default function TaskKanban() {
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newGoal, setNewGoal] = useState('');
  const [creating, setCreating] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [dragOverColumn, setDragOverColumn] = useState<string | null>(null);
  const [movingId, setMovingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const list = await api.fetchTasks();
      setTasks(list);
    } catch (e) {
      setToast(e instanceof Error ? e.message : 'Failed to load tasks');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return tasks;
    return tasks.filter(
      (t) =>
        t.title.toLowerCase().includes(q) ||
        t.goal.toLowerCase().includes(q) ||
        t.id.toLowerCase().includes(q) ||
        t.status.toLowerCase().includes(q),
    );
  }, [tasks, query]);

  const byColumn = useMemo(() => {
    const map = new Map<string, TaskSummary[]>();
    for (const col of TASK_KANBAN_COLUMNS) {
      map.set(col.id, []);
    }
    for (const t of filtered) {
      const colId = kanbanColumnIdForStatus(t.status);
      const list = map.get(colId) ?? map.get('backlog')!;
      list.push(t);
    }
    for (const [, list] of map) {
      list.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
    }
    return map;
  }, [filtered]);

  const handleDrop = useCallback(
    async (columnId: string, taskId: string) => {
      const col = kanbanColumnById(columnId);
      if (!col) return;

      const task = tasks.find((t) => t.id === taskId);
      if (!task) return;

      const fromCol = kanbanColumnIdForStatus(task.status);
      if (fromCol === columnId && col.statuses.includes(task.status)) {
        return;
      }

      if (task.status === col.dropStatus && col.statuses.includes(task.status)) {
        return;
      }

      const prev = tasks;
      setTasks((cur) => cur.map((t) => (t.id === taskId ? { ...t, status: col.dropStatus } : t)));
      setMovingId(taskId);

      try {
        const updated = await api.patchTask(taskId, { status: col.dropStatus });
        setTasks((cur) => cur.map((t) => (t.id === taskId ? { ...t, ...updated } : t)));
      } catch (e) {
        setTasks(prev);
        setToast(e instanceof Error ? e.message : 'Could not move task');
      } finally {
        setMovingId(null);
      }
    },
    [tasks],
  );

  const handleCreate = async () => {
    if (!newGoal.trim()) {
      setToast('Goal is required');
      return;
    }
    setCreating(true);
    try {
      const t = await api.createTask({
        title: newTitle.trim() || 'Untitled task',
        goal: newGoal.trim(),
      });
      setCreateOpen(false);
      setNewTitle('');
      setNewGoal('');
      navigate(`/tasks/${t.id}`);
    } catch (e) {
      setToast(e instanceof Error ? e.message : 'Create failed');
    } finally {
      setCreating(false);
    }
  };

  const onDragStart = (e: React.DragEvent, taskId: string) => {
    e.dataTransfer.setData(DND_TYPE, taskId);
    e.dataTransfer.effectAllowed = 'move';
  };

  return (
    <Box sx={{ width: '100%', minWidth: 0 }}>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-start', gap: 2, mb: 3 }}>
        <Box sx={{ flex: '1 1 280px', minWidth: 0 }}>
          <Typography variant="h4" sx={{ fontWeight: 800, letterSpacing: '-0.03em', mb: 0.5 }}>
            Task board
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 560, lineHeight: 1.6 }}>
            Plan work by status: drag the handle on a card to move it between columns. Your changes sync to the server
            immediately.
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
          <Button
            component={RouterLink}
            to="/tasks"
            variant="outlined"
            startIcon={<ViewListIcon />}
            sx={{ borderColor: 'var(--border)', fontWeight: 600 }}
          >
            List view
          </Button>
          <TextField
            size="small"
            placeholder="Search…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon sx={{ color: 'text.secondary', fontSize: 20 }} />
                </InputAdornment>
              ),
            }}
            sx={{ minWidth: { xs: '100%', sm: 220 }, bgcolor: 'var(--panel)' }}
          />
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={load}
            disabled={loading}
            sx={{ borderColor: 'var(--border)' }}
          >
            Refresh
          </Button>
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
            New task
          </Button>
        </Box>
      </Box>

      <Box
        sx={{
          display: 'flex',
          gap: 2,
          alignItems: 'stretch',
          overflowX: 'auto',
          overflowY: 'hidden',
          pb: 2,
          mx: { xs: -2, md: -3 },
          px: { xs: 2, md: 3 },
          scrollSnapType: 'x proximity',
        }}
      >
        {TASK_KANBAN_COLUMNS.map((col) => {
          const list = byColumn.get(col.id) ?? [];
          const isOver = dragOverColumn === col.id;

          return (
            <Box
              key={col.id}
              onDragOver={(e) => {
                if (!Array.from(e.dataTransfer.types).includes(DND_TYPE)) return;
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                setDragOverColumn(col.id);
              }}
              onDragLeave={() => {
                setDragOverColumn((cur) => (cur === col.id ? null : cur));
              }}
              onDrop={(e) => {
                e.preventDefault();
                setDragOverColumn(null);
                const id = e.dataTransfer.getData(DND_TYPE);
                if (id) void handleDrop(col.id, id);
              }}
              sx={{
                flex: '0 0 300px',
                width: 300,
                minHeight: 420,
                scrollSnapAlign: 'start',
                borderRadius: 2,
                bgcolor: isOver ? 'action.hover' : 'var(--panel)',
                border: '1px solid',
                borderColor: isOver ? 'primary.main' : 'var(--border)',
                boxShadow: isOver ? 'var(--shadow-1)' : 'none',
                transition: 'border-color 0.15s ease, background-color 0.15s ease, box-shadow 0.15s ease',
                display: 'flex',
                flexDirection: 'column',
                maxHeight: 'calc(100vh - 220px)',
              }}
            >
              <Box sx={{ p: 2, pb: 1.5, flexShrink: 0, borderBottom: '1px solid', borderColor: 'divider' }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 800, letterSpacing: '-0.02em' }}>
                  {col.title}
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.25 }}>
                  {col.hint} · {list.length}
                </Typography>
              </Box>

              <Box
                sx={{
                  flex: 1,
                  overflowY: 'auto',
                  p: 1.5,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 1.25,
                }}
              >
                {loading
                  ? Array.from({ length: 3 }).map((_, i) => (
                      <Skeleton key={i} variant="rounded" height={112} sx={{ borderRadius: 2, flexShrink: 0 }} />
                    ))
                  : list.map((t) => (
                      <Card
                        key={t.id}
                        elevation={0}
                        sx={{
                          flexShrink: 0,
                          border: '1px solid',
                          borderColor: movingId === t.id ? 'primary.main' : 'var(--border)',
                          bgcolor: 'background.paper',
                          borderRadius: 2,
                          opacity: movingId === t.id ? 0.75 : 1,
                          transition: 'border-color 0.15s ease, opacity 0.15s ease, transform 0.15s ease',
                          '&:hover': { borderColor: 'primary.main', transform: 'translateY(-2px)' },
                        }}
                      >
                        <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
                          <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
                            <Box
                              component="span"
                              draggable
                              onDragStart={(e) => onDragStart(e, t.id)}
                              sx={{
                                cursor: 'grab',
                                color: 'text.secondary',
                                display: 'flex',
                                alignItems: 'center',
                                mt: 0.25,
                                touchAction: 'none',
                                '&:active': { cursor: 'grabbing' },
                              }}
                              aria-label={`Move task ${t.title}`}
                            >
                              <DragIndicatorIcon sx={{ fontSize: 22 }} />
                            </Box>
                            <Box
                              sx={{ flex: 1, minWidth: 0, cursor: 'pointer' }}
                              onClick={() => navigate(`/tasks/${t.id}`)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter' || e.key === ' ') {
                                  e.preventDefault();
                                  navigate(`/tasks/${t.id}`);
                                }
                              }}
                              role="button"
                              tabIndex={0}
                            >
                              <Typography variant="subtitle2" sx={{ fontWeight: 700, lineHeight: 1.3, mb: 0.75 }} noWrap>
                                {t.title || 'Untitled'}
                              </Typography>
                              <Typography
                                variant="caption"
                                color="text.secondary"
                                sx={{
                                  display: '-webkit-box',
                                  WebkitLineClamp: 2,
                                  WebkitBoxOrient: 'vertical',
                                  overflow: 'hidden',
                                  lineHeight: 1.45,
                                  mb: 1,
                                }}
                              >
                                {t.goal}
                              </Typography>
                              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, alignItems: 'center' }}>
                                <Chip
                                  label={t.status.replace(/_/g, ' ')}
                                  size="small"
                                  color={statusChipColor(t.status)}
                                  variant="outlined"
                                  sx={{ fontWeight: 600, fontSize: '0.65rem', height: 22 }}
                                />
                                <Chip
                                  label={t.phase.replace(/_/g, ' ')}
                                  size="small"
                                  color={phaseChipColor(t.phase)}
                                  variant="outlined"
                                  sx={{ fontWeight: 600, fontSize: '0.65rem', height: 22 }}
                                />
                                <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto', fontSize: '0.65rem' }}>
                                  {formatShort(t.updated_at)}
                                </Typography>
                              </Box>
                              <Typography
                                variant="caption"
                                sx={{ display: 'block', mt: 0.75, fontFamily: 'monospace', opacity: 0.55, fontSize: '0.6rem' }}
                              >
                                {t.id}
                              </Typography>
                            </Box>
                          </Box>
                        </CardContent>
                      </Card>
                    ))}
              </Box>
            </Box>
          );
        })}
      </Box>

      {!loading && filtered.length === 0 && (
        <Box
          sx={{
            py: 8,
            textAlign: 'center',
            border: '1px dashed',
            borderColor: 'var(--border)',
            borderRadius: 2,
            bgcolor: 'var(--panel)',
            mt: 2,
          }}
        >
          <Typography variant="h6" color="text.secondary" sx={{ mb: 1 }}>
            {tasks.length === 0 ? 'No tasks yet' : 'No matches'}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {tasks.length === 0
              ? 'Create a task from the button above — it will appear in Backlog.'
              : 'Try a different search or clear the filter.'}
          </Typography>
        </Box>
      )}

      <Fab
        color="primary"
        sx={{ position: 'fixed', bottom: 24, right: 24, display: { xs: 'flex', md: 'none' } }}
        onClick={() => setCreateOpen(true)}
        aria-label="new task"
      >
        <AddIcon />
      </Fab>

      <Dialog open={createOpen} onClose={() => !creating && setCreateOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle sx={{ fontWeight: 700 }}>New task</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 1 }}>
          <TextField
            label="Title"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="Optional short label"
            fullWidth
          />
          <TextField
            label="Goal"
            value={newGoal}
            onChange={(e) => setNewGoal(e.target.value)}
            placeholder="What should this task achieve?"
            multiline
            minRows={4}
            fullWidth
            required
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setCreateOpen(false)} disabled={creating}>
            Cancel
          </Button>
          <Button variant="contained" onClick={handleCreate} disabled={creating}>
            {creating ? 'Creating…' : 'Create & open'}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar open={!!toast} autoHideDuration={6000} onClose={() => setToast(null)} anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        <Alert severity="error" onClose={() => setToast(null)} sx={{ width: '100%' }}>
          {toast}
        </Alert>
      </Snackbar>
    </Box>
  );
}
