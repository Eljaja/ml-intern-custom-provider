import { useCallback, useEffect, useState } from 'react';
import {
  Box,
  Typography,
  Button,
  Tabs,
  Tab,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  MenuItem,
  IconButton,
  Breadcrumbs,
  Link,
  Snackbar,
  Alert,
  Skeleton,
  Tooltip,
} from '@mui/material';
import { useNavigate, useParams, Link as RouterLink } from 'react-router-dom';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import RefreshIcon from '@mui/icons-material/Refresh';
import AddCircleOutlineIcon from '@mui/icons-material/AddCircleOutline';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import * as api from '@/api/lifecycle';
import type { TaskDetail } from '@/types/lifecycle';
import { RUN_TYPES, TASK_PHASES, TASK_STATUSES } from '@/components/Lifecycle/lifecycleConstants';

function statusChipColor(
  status: string,
): 'default' | 'primary' | 'secondary' | 'success' | 'warning' | 'error' {
  if (status === 'succeeded') return 'success';
  if (status === 'failed' || status === 'cancelled') return 'error';
  if (status === 'running' || status === 'queued' || status === 'leased') return 'primary';
  if (status === 'awaiting_approval' || status === 'blocked') return 'warning';
  return 'default';
}

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel({ children, value, index }: TabPanelProps) {
  return (
    <div role="tabpanel" hidden={value !== index} style={{ marginTop: 16 }}>
      {value === index ? children : null}
    </div>
  );
}

export default function TaskDetail() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<TaskDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState(0);
  const [toast, setToast] = useState<{ msg: string; sev: 'success' | 'error' | 'info' } | null>(null);

  const load = useCallback(async () => {
    if (!taskId) return;
    setLoading(true);
    try {
      const d = await api.fetchTaskDetail(taskId);
      setDetail(d);
    } catch (e) {
      setToast({ msg: e instanceof Error ? e.message : 'Load failed', sev: 'error' });
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  useEffect(() => {
    load();
  }, [load]);

  const copy = (s: string) => {
    void navigator.clipboard.writeText(s);
    setToast({ msg: 'Copied', sev: 'success' });
  };

  /* ---- dialogs ---- */
  const [runOpen, setRunOpen] = useState(false);
  const [runType, setRunType] = useState<string>('research');
  const [runModel, setRunModel] = useState('');
  const [runConfigJson, setRunConfigJson] = useState('{}');

  const [jobOpen, setJobOpen] = useState(false);
  const [jobType, setJobType] = useState('plan');
  const [jobRunId, setJobRunId] = useState<string>('');
  const [jobPayloadJson, setJobPayloadJson] = useState('{}');

  const [artOpen, setArtOpen] = useState(false);
  const [artType, setArtType] = useState('metrics');
  const [artUri, setArtUri] = useState('');
  const [artRunId, setArtRunId] = useState<string>('');
  const [artJobId, setArtJobId] = useState<string>('');

  const [savingMeta, setSavingMeta] = useState(false);
  const [editStatus, setEditStatus] = useState('');
  const [editPhase, setEditPhase] = useState('');
  const [constraintsJson, setConstraintsJson] = useState('{}');
  const [acceptanceJson, setAcceptanceJson] = useState('{}');

  useEffect(() => {
    if (!detail) return;
    setEditStatus(detail.status);
    setEditPhase(detail.phase);
    setConstraintsJson(JSON.stringify(detail.constraints ?? {}, null, 2));
    setAcceptanceJson(JSON.stringify(detail.acceptance ?? {}, null, 2));
  }, [detail]);

  const submitRun = async () => {
    if (!taskId) return;
    let config: Record<string, unknown> = {};
    try {
      config = JSON.parse(runConfigJson || '{}') as Record<string, unknown>;
    } catch {
      setToast({ msg: 'Run config must be valid JSON', sev: 'error' });
      return;
    }
    try {
      await api.createRun(taskId, {
        run_type: runType,
        model_name: runModel || null,
        config,
      });
      setRunOpen(false);
      setRunConfigJson('{}');
      setToast({ msg: 'Run created', sev: 'success' });
      await load();
      setTab(1);
    } catch (e) {
      setToast({ msg: e instanceof Error ? e.message : 'Failed', sev: 'error' });
    }
  };

  const submitJob = async () => {
    if (!taskId) return;
    let payload: Record<string, unknown> = {};
    try {
      payload = JSON.parse(jobPayloadJson || '{}') as Record<string, unknown>;
    } catch {
      setToast({ msg: 'Job payload must be valid JSON', sev: 'error' });
      return;
    }
    try {
      await api.createJob(taskId, {
        job_type: jobType,
        run_id: jobRunId || null,
        payload,
      });
      setJobOpen(false);
      setJobPayloadJson('{}');
      setToast({ msg: 'Job queued', sev: 'success' });
      await load();
      setTab(2);
    } catch (e) {
      setToast({ msg: e instanceof Error ? e.message : 'Failed', sev: 'error' });
    }
  };

  const submitArtifact = async () => {
    if (!taskId) return;
    if (!artUri.trim()) {
      setToast({ msg: 'URI required', sev: 'error' });
      return;
    }
    try {
      await api.createArtifact(taskId, {
        type: artType,
        uri: artUri.trim(),
        run_id: artRunId || null,
        job_id: artJobId || null,
      });
      setArtOpen(false);
      setArtUri('');
      setToast({ msg: 'Artifact registered', sev: 'success' });
      await load();
      setTab(3);
    } catch (e) {
      setToast({ msg: e instanceof Error ? e.message : 'Failed', sev: 'error' });
    }
  };

  const saveTaskMeta = async () => {
    if (!taskId) return;
    let constraints: Record<string, unknown> = {};
    let acceptance: Record<string, unknown> = {};
    try {
      constraints = JSON.parse(constraintsJson || '{}') as Record<string, unknown>;
      acceptance = JSON.parse(acceptanceJson || '{}') as Record<string, unknown>;
    } catch {
      setToast({ msg: 'Constraints / acceptance must be valid JSON', sev: 'error' });
      return;
    }
    setSavingMeta(true);
    try {
      await api.patchTask(taskId, {
        status: editStatus,
        phase: editPhase,
        constraints,
        acceptance,
      });
      setToast({ msg: 'Task updated', sev: 'success' });
      await load();
    } catch (e) {
      setToast({ msg: e instanceof Error ? e.message : 'Failed', sev: 'error' });
    } finally {
      setSavingMeta(false);
    }
  };

  if (!taskId) {
    return null;
  }

  return (
    <Box>
      <Breadcrumbs sx={{ mb: 1, '& a': { textDecoration: 'none' } }}>
        <Link component={RouterLink} to="/tasks" color="inherit" sx={{ fontWeight: 600 }}>
          Tasks
        </Link>
        <Typography color="text.primary" variant="body2" sx={{ fontWeight: 700 }}>
          {loading ? '…' : detail?.title || detail?.id}
        </Typography>
      </Breadcrumbs>

      <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-start', gap: 2, mb: 2 }}>
        <IconButton onClick={() => navigate('/tasks')} size="small" sx={{ border: '1px solid', borderColor: 'divider' }}>
          <ArrowBackIcon />
        </IconButton>
        <Box sx={{ flex: '1 1 240px', minWidth: 0 }}>
          {loading || !detail ? (
            <Skeleton variant="text" width="60%" height={40} />
          ) : (
            <>
              <Typography variant="h4" sx={{ fontWeight: 800, letterSpacing: '-0.03em', lineHeight: 1.2 }}>
                {detail.title || 'Untitled task'}
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center', mt: 1 }}>
                <Chip label={detail.status} size="small" color={statusChipColor(detail.status)} variant="outlined" />
                <Chip label={detail.phase.replace(/_/g, ' ')} size="small" variant="outlined" />
                <Chip label={`P${detail.priority}`} size="small" variant="outlined" />
                <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                  {detail.id}
                  <IconButton size="small" onClick={() => copy(detail.id)}>
                    <ContentCopyIcon sx={{ fontSize: 14 }} />
                  </IconButton>
                </Typography>
              </Box>
            </>
          )}
        </Box>
        <Button startIcon={<RefreshIcon />} variant="outlined" onClick={load} disabled={loading} sx={{ borderColor: 'var(--border)' }}>
          Refresh
        </Button>
      </Box>

      <Paper elevation={0} sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, overflow: 'hidden', bgcolor: 'var(--panel)' }}>
        <Tabs
          value={tab}
          onChange={(_, v) => setTab(v)}
          variant="scrollable"
          scrollButtons="auto"
          sx={{
            borderBottom: 1,
            borderColor: 'divider',
            px: 1,
            '& .MuiTab-root': { fontWeight: 700, textTransform: 'none' },
          }}
        >
          <Tab label="Overview" />
          <Tab label={`Runs (${detail?.runs.length ?? 0})`} />
          <Tab label={`Jobs (${detail?.jobs.length ?? 0})`} />
          <Tab label={`Artifacts (${detail?.artifacts.length ?? 0})`} />
        </Tabs>

        <Box sx={{ p: 2.5 }}>
          <TabPanel value={tab} index={0}>
            {loading || !detail ? (
              <Skeleton variant="rounded" height={320} />
            ) : (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <Typography variant="body1" color="text.secondary" sx={{ lineHeight: 1.7 }}>
                  {detail.goal}
                </Typography>
                {detail.source_session_id && (
                  <Alert severity="info" sx={{ py: 0 }}>
                    Linked session{' '}
                    <strong style={{ fontFamily: 'monospace' }}>{detail.source_session_id}</strong>
                    <Button size="small" component={RouterLink} to="/" sx={{ ml: 1 }}>
                      Open chat layout
                    </Button>
                  </Alert>
                )}
                <Box
                  sx={{
                    display: 'grid',
                    gridTemplateColumns: { xs: '1fr', md: 'repeat(2, 1fr)' },
                    gap: 2,
                  }}
                >
                  <TextField select label="Status" value={editStatus} onChange={(e) => setEditStatus(e.target.value)} fullWidth>
                    {TASK_STATUSES.map((s) => (
                      <MenuItem key={s} value={s}>
                        {s}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField select label="Phase" value={editPhase} onChange={(e) => setEditPhase(e.target.value)} fullWidth>
                    {TASK_PHASES.map((p) => (
                      <MenuItem key={p} value={p}>
                        {p.replace(/_/g, ' ')}
                      </MenuItem>
                    ))}
                  </TextField>
                </Box>
                <TextField
                  label="Constraints (JSON)"
                  value={constraintsJson}
                  onChange={(e) => setConstraintsJson(e.target.value)}
                  multiline
                  minRows={4}
                  fullWidth
                  sx={{ fontFamily: 'monospace' }}
                />
                <TextField
                  label="Acceptance criteria (JSON)"
                  value={acceptanceJson}
                  onChange={(e) => setAcceptanceJson(e.target.value)}
                  multiline
                  minRows={4}
                  fullWidth
                  sx={{ fontFamily: 'monospace' }}
                />
                <Button variant="contained" onClick={saveTaskMeta} disabled={savingMeta} sx={{ alignSelf: 'flex-start' }}>
                  {savingMeta ? 'Saving…' : 'Save overview'}
                </Button>
              </Box>
            )}
          </TabPanel>

          <TabPanel value={tab} index={1}>
            <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 1 }}>
              <Button startIcon={<AddCircleOutlineIcon />} variant="contained" onClick={() => setRunOpen(true)}>
                Add run
              </Button>
            </Box>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>ID</TableCell>
                    <TableCell>Type</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Model</TableCell>
                    <TableCell>Created</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(detail?.runs ?? []).map((r) => (
                    <TableRow key={r.id} hover sx={{ '& td': { fontFamily: 'monospace', fontSize: '0.78rem' } }}>
                      <TableCell>
                        <Tooltip title="Copy id">
                          <Button size="small" onClick={() => copy(r.id)}>
                            {r.id.slice(0, 14)}…
                          </Button>
                        </Tooltip>
                      </TableCell>
                      <TableCell>{r.run_type}</TableCell>
                      <TableCell>
                        <Chip label={r.status} size="small" color={statusChipColor(r.status)} variant="outlined" />
                      </TableCell>
                      <TableCell>{r.model_name ?? '—'}</TableCell>
                      <TableCell>{r.created_at}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            {!loading && detail && detail.runs.length === 0 && (
              <Typography color="text.secondary" sx={{ py: 4, textAlign: 'center' }}>
                No runs yet — add one to track experiments.
              </Typography>
            )}
          </TabPanel>

          <TabPanel value={tab} index={2}>
            <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 1 }}>
              <Button startIcon={<AddCircleOutlineIcon />} variant="contained" onClick={() => setJobOpen(true)}>
                Add job
              </Button>
            </Box>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>ID</TableCell>
                    <TableCell>Type</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Run</TableCell>
                    <TableCell>Priority</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(detail?.jobs ?? []).map((j) => (
                    <TableRow key={j.id} hover sx={{ '& td': { fontFamily: 'monospace', fontSize: '0.78rem' } }}>
                      <TableCell>{j.id.slice(0, 18)}…</TableCell>
                      <TableCell>{j.job_type}</TableCell>
                      <TableCell>
                        <Chip label={j.status} size="small" color={statusChipColor(j.status)} variant="outlined" />
                      </TableCell>
                      <TableCell>{j.run_id ?? '—'}</TableCell>
                      <TableCell>{j.priority}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            {!loading && detail && detail.jobs.length === 0 && (
              <Typography color="text.secondary" sx={{ py: 4, textAlign: 'center' }}>
                No jobs queued yet.
              </Typography>
            )}
          </TabPanel>

          <TabPanel value={tab} index={3}>
            <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 1 }}>
              <Button startIcon={<AddCircleOutlineIcon />} variant="contained" onClick={() => setArtOpen(true)}>
                Register artifact
              </Button>
            </Box>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>ID</TableCell>
                    <TableCell>Type</TableCell>
                    <TableCell>URI</TableCell>
                    <TableCell>Run</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(detail?.artifacts ?? []).map((a) => (
                    <TableRow key={a.id} hover sx={{ '& td': { fontFamily: 'monospace', fontSize: '0.78rem' } }}>
                      <TableCell>{a.id.slice(0, 14)}…</TableCell>
                      <TableCell>{a.type}</TableCell>
                      <TableCell sx={{ maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis' }}>{a.uri}</TableCell>
                      <TableCell>{a.run_id ?? '—'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            {!loading && detail && detail.artifacts.length === 0 && (
              <Typography color="text.secondary" sx={{ py: 4, textAlign: 'center' }}>
                No artifacts registered.
              </Typography>
            )}
          </TabPanel>
        </Box>
      </Paper>

      {/* Run dialog */}
      <Dialog open={runOpen} onClose={() => setRunOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle sx={{ fontWeight: 700 }}>New experiment run</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 1 }}>
          <TextField select label="Run type" value={runType} onChange={(e) => setRunType(e.target.value)} fullWidth>
            {RUN_TYPES.map((t) => (
              <MenuItem key={t} value={t}>
                {t}
              </MenuItem>
            ))}
          </TextField>
          <TextField label="Model name (optional)" value={runModel} onChange={(e) => setRunModel(e.target.value)} fullWidth />
          <TextField
            label="Config JSON"
            value={runConfigJson}
            onChange={(e) => setRunConfigJson(e.target.value)}
            multiline
            minRows={4}
            fullWidth
            sx={{ fontFamily: 'monospace' }}
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setRunOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={() => void submitRun()}>
            Create
          </Button>
        </DialogActions>
      </Dialog>

      {/* Job dialog */}
      <Dialog open={jobOpen} onClose={() => setJobOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle sx={{ fontWeight: 700 }}>Queue job</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 1 }}>
          <TextField label="Job type" value={jobType} onChange={(e) => setJobType(e.target.value)} fullWidth placeholder="plan, research, …" />
          <TextField select label="Link to run (optional)" value={jobRunId} onChange={(e) => setJobRunId(e.target.value)} fullWidth>
            <MenuItem value="">— none —</MenuItem>
            {(detail?.runs ?? []).map((r) => (
              <MenuItem key={r.id} value={r.id}>
                {r.id} ({r.run_type})
              </MenuItem>
            ))}
          </TextField>
          <TextField
            label="Payload JSON"
            value={jobPayloadJson}
            onChange={(e) => setJobPayloadJson(e.target.value)}
            multiline
            minRows={4}
            fullWidth
            sx={{ fontFamily: 'monospace' }}
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setJobOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={() => void submitJob()}>
            Queue
          </Button>
        </DialogActions>
      </Dialog>

      {/* Artifact dialog */}
      <Dialog open={artOpen} onClose={() => setArtOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle sx={{ fontWeight: 700 }}>Register artifact</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 1 }}>
          <TextField label="Type" value={artType} onChange={(e) => setArtType(e.target.value)} fullWidth />
          <TextField label="URI" value={artUri} onChange={(e) => setArtUri(e.target.value)} fullWidth required />
          <TextField select label="Run (optional)" value={artRunId} onChange={(e) => setArtRunId(e.target.value)} fullWidth>
            <MenuItem value="">— none —</MenuItem>
            {(detail?.runs ?? []).map((r) => (
              <MenuItem key={r.id} value={r.id}>
                {r.id}
              </MenuItem>
            ))}
          </TextField>
          <TextField select label="Job (optional)" value={artJobId} onChange={(e) => setArtJobId(e.target.value)} fullWidth>
            <MenuItem value="">— none —</MenuItem>
            {(detail?.jobs ?? []).map((j) => (
              <MenuItem key={j.id} value={j.id}>
                {j.id} ({j.job_type})
              </MenuItem>
            ))}
          </TextField>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setArtOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={() => void submitArtifact()}>
            Register
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={!!toast}
        autoHideDuration={4000}
        onClose={() => setToast(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity={toast?.sev === 'success' ? 'success' : toast?.sev === 'info' ? 'info' : 'error'} onClose={() => setToast(null)}>
          {toast?.msg}
        </Alert>
      </Snackbar>
    </Box>
  );
}
