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
  CardActionArea,
  CardContent,
  Skeleton,
  InputAdornment,
  Chip,
  Snackbar,
  Alert,
  Fab,
  Zoom,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import RefreshIcon from '@mui/icons-material/Refresh';
import SearchIcon from '@mui/icons-material/Search';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import DeveloperBoardOutlinedIcon from '@mui/icons-material/DeveloperBoardOutlined';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import * as api from '@/api/lifecycle';
import type { TaskSummary } from '@/types/lifecycle';

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
  return 'default';
}

export default function TaskDashboard() {
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newGoal, setNewGoal] = useState('');
  const [creating, setCreating] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

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

  return (
    <Box>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-start', gap: 2, mb: 3 }}>
        <Box sx={{ flex: '1 1 280px', minWidth: 0 }}>
          <Typography variant="h4" sx={{ fontWeight: 800, letterSpacing: '-0.03em', mb: 0.5 }}>
            Tasks
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 520, lineHeight: 1.6 }}>
            Durable ML objectives: each task holds experiment runs, jobs, and artifacts. Open a card to inspect
            lineage and add new work items.
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
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
          <Button
            component={RouterLink}
            to="/tasks/board"
            variant="outlined"
            startIcon={<DeveloperBoardOutlinedIcon />}
            sx={{ borderColor: 'var(--border)', fontWeight: 600 }}
          >
            Kanban
          </Button>
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
            New task
          </Button>
        </Box>
      </Box>

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(3, 1fr)' },
          gap: 2,
        }}
      >
        {loading
          ? Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} variant="rounded" height={168} sx={{ borderRadius: 2 }} />
            ))
          : filtered.map((t, idx) => (
              <Zoom in key={t.id} timeout={280} style={{ transitionDelay: `${Math.min(idx, 8) * 40}ms` }}>
                <Card
                  elevation={0}
                  sx={{
                    border: '1px solid',
                    borderColor: 'var(--border)',
                    bgcolor: 'var(--panel)',
                    borderRadius: 2,
                    overflow: 'hidden',
                    transition: 'transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease',
                    '&:hover': {
                      transform: 'translateY(-4px)',
                      boxShadow: 'var(--shadow-1)',
                      borderColor: 'primary.main',
                    },
                  }}
                >
                  <CardActionArea onClick={() => navigate(`/tasks/${t.id}`)} sx={{ alignItems: 'stretch' }}>
                    <CardContent sx={{ p: 2.25, '&:last-child': { pb: 2.25 } }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, mb: 1 }}>
                        <Typography variant="subtitle1" sx={{ fontWeight: 700, lineHeight: 1.3 }} noWrap>
                          {t.title || 'Untitled'}
                        </Typography>
                        <ArrowForwardIcon sx={{ fontSize: 18, color: 'text.secondary', flexShrink: 0 }} />
                      </Box>
                      <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{
                          display: '-webkit-box',
                          WebkitLineClamp: 3,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
                          minHeight: '3.6em',
                          lineHeight: 1.45,
                          mb: 1.5,
                        }}
                      >
                        {t.goal}
                      </Typography>
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, alignItems: 'center' }}>
                        <Chip
                          label={t.status}
                          size="small"
                          color={statusChipColor(t.status)}
                          variant="outlined"
                          sx={{ fontWeight: 600, fontSize: '0.72rem' }}
                        />
                        <Chip
                          label={t.phase.replace(/_/g, ' ')}
                          size="small"
                          color={phaseChipColor(t.phase)}
                          variant="outlined"
                          sx={{ fontWeight: 600, fontSize: '0.72rem' }}
                        />
                        <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>
                          {formatShort(t.updated_at)}
                        </Typography>
                      </Box>
                      <Typography
                        variant="caption"
                        sx={{ display: 'block', mt: 1.25, fontFamily: 'monospace', opacity: 0.65, fontSize: '0.65rem' }}
                      >
                        {t.id}
                      </Typography>
                    </CardContent>
                  </CardActionArea>
                </Card>
              </Zoom>
            ))}
      </Box>

      {!loading && filtered.length === 0 && (
        <Box
          sx={{
            py: 10,
            textAlign: 'center',
            border: '1px dashed',
            borderColor: 'var(--border)',
            borderRadius: 2,
            bgcolor: 'var(--panel)',
          }}
        >
          <Typography variant="h6" color="text.secondary" sx={{ mb: 1 }}>
            {tasks.length === 0 ? 'No tasks yet' : 'No matches'}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {tasks.length === 0 ? 'Create your first durable task to track runs and artifacts.' : 'Try a different search.'}
          </Typography>
          {tasks.length === 0 && (
            <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
              New task
            </Button>
          )}
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
