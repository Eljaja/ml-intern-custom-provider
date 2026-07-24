import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  CircularProgress,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  Switch,
  Tooltip,
  Typography,
} from '@mui/material';
import AutoAwesomeOutlinedIcon from '@mui/icons-material/AutoAwesomeOutlined';
import CloseIcon from '@mui/icons-material/Close';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import { apiFetch } from '@/utils/api';
import { useSkillsStore } from '@/store/skillsStore';
import type { SkillDetail, SkillSummary } from '@/types/agent';

export default function SkillsPanel() {
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<SkillDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [updating, setUpdating] = useState<Record<string, boolean>>({});

  const loadSkills = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiFetch('/api/skills');
      if (!response.ok) throw new Error(await response.text());
      const data = await response.json();
      setSkills(Array.isArray(data) ? data : []);
    } catch {
      setError('Failed to load skills.');
    } finally {
      setLoading(false);
    }
  }, []);

  const skillsRevision = useSkillsStore((s) => s.revision);

  useEffect(() => {
    void loadSkills();
  }, [loadSkills, skillsRevision]);

  const toggleSkill = useCallback(async (skill: SkillSummary, enabled: boolean) => {
    setUpdating((prev) => ({ ...prev, [skill.name]: true }));
    // Clear any previous failure, so a successful retry doesn't leave a stale
    // banner sitting above the list.
    setError(null);
    try {
      const response = await apiFetch(`/api/skills/${encodeURIComponent(skill.name)}`, {
        method: 'PATCH',
        body: JSON.stringify({ enabled }),
      });
      if (!response.ok) throw new Error(await response.text());
      const updated = await response.json();
      setSkills((current) => current.map((item) => (
        item.name === updated.name ? updated : item
      )));
      setDetail((current) => {
        if (!current || current.name !== updated.name) return current;
        return { ...updated, content: current.content };
      });
    } catch {
      setError('Failed to update skill.');
    } finally {
      setUpdating((prev) => ({ ...prev, [skill.name]: false }));
    }
  }, []);

  const deleteSkill = useCallback(async (skill: SkillSummary) => {
    // Skills are written automatically by the post-turn reflection, so this is a
    // routine cleanup action rather than a rare destructive one — but it is still
    // irreversible, hence the confirm.
    if (!window.confirm(`Delete the skill "${skill.name}"? This cannot be undone.`)) {
      return;
    }
    setUpdating((prev) => ({ ...prev, [skill.name]: true }));
    setError(null);
    try {
      const response = await apiFetch(`/api/skills/${encodeURIComponent(skill.name)}`, {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error(await response.text());
      setSkills((current) => current.filter((item) => item.name !== skill.name));
      setDetail((current) => (current?.name === skill.name ? null : current));
    } catch {
      setError('Failed to delete skill.');
    } finally {
      setUpdating((prev) => {
        const next = { ...prev };
        delete next[skill.name];
        return next;
      });
    }
  }, []);

  const openDetail = useCallback(async (skill: SkillSummary) => {
    setDetailLoading(true);
    setError(null);
    try {
      const response = await apiFetch(`/api/skills/${encodeURIComponent(skill.name)}`);
      if (!response.ok) throw new Error(await response.text());
      setDetail(await response.json());
    } catch {
      setError('Failed to load skill details.');
    } finally {
      setDetailLoading(false);
    }
  }, []);

  return (
    <Box sx={{ px: 1.25, py: 1, borderTop: '1px solid var(--border)' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.75 }}>
        <AutoAwesomeOutlinedIcon sx={{ fontSize: 15, color: 'var(--muted-text)' }} />
        <Typography
          variant="caption"
          sx={{
            color: 'var(--muted-text)',
            fontSize: '0.65rem',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
          }}
        >
          Skills
        </Typography>
        {loading && <CircularProgress size={11} sx={{ ml: 'auto' }} />}
      </Box>

      {error && (
        <Alert severity="warning" variant="outlined" sx={{ mb: 1, py: 0, fontSize: '0.7rem' }}>
          {error}
        </Alert>
      )}

      {!loading && skills.length === 0 ? (
        <Typography
          variant="caption"
          sx={{ color: 'var(--muted-text)', opacity: 0.65, fontSize: '0.72rem' }}
        >
          No learned skills yet.
        </Typography>
      ) : (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, maxHeight: 180, overflow: 'auto' }}>
          {skills.map((skill) => (
            <Box
              key={skill.name}
              // role/tabIndex/onKeyDown: this row opens a dialog, so it has to be
              // reachable without a mouse.
              role="button"
              tabIndex={0}
              aria-label={`Open skill ${skill.name}`}
              onClick={() => void openDetail(skill)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  void openDetail(skill);
                }
              }}
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 0.75,
                p: 0.75,
                borderRadius: '9px',
                cursor: 'pointer',
                '&:hover': { bgcolor: 'var(--hover-bg)' },
                '&:focus-visible': {
                  outline: '2px solid var(--accent, #6c8cff)',
                  outlineOffset: 1,
                },
              }}
            >
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography
                  variant="body2"
                  sx={{
                    color: 'var(--text)',
                    fontSize: '0.78rem',
                    fontWeight: 600,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {skill.name}
                </Typography>
                <Tooltip title={skill.description} placement="right">
                  <Typography
                    variant="caption"
                    sx={{
                      color: 'var(--muted-text)',
                      fontSize: '0.66rem',
                      display: 'block',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {skill.description}
                  </Typography>
                </Tooltip>
              </Box>
              <Switch
                size="small"
                checked={skill.enabled}
                disabled={!!updating[skill.name]}
                onClick={(event) => event.stopPropagation()}
                onChange={(event) => void toggleSkill(skill, event.target.checked)}
                inputProps={{ 'aria-label': `Enable ${skill.name}` }}
              />
              <Tooltip title="Delete skill" placement="left">
                <IconButton
                  size="small"
                  disabled={!!updating[skill.name]}
                  aria-label={`Delete ${skill.name}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    void deleteSkill(skill);
                  }}
                  sx={{
                    color: 'var(--muted-text)',
                    '&:hover': { color: 'var(--error, #e5484d)' },
                  }}
                >
                  <DeleteOutlineIcon sx={{ fontSize: 15 }} />
                </IconButton>
              </Tooltip>
            </Box>
          ))}
        </Box>
      )}

      <Dialog
        open={!!detail || detailLoading}
        onClose={() => setDetail(null)}
        maxWidth="md"
        fullWidth
        PaperProps={{
          sx: {
            bgcolor: 'var(--panel)',
            color: 'var(--text)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
          },
        }}
      >
        <DialogTitle sx={{ pr: 6 }}>
          {detail?.name || 'Loading skill'}
          <IconButton
            onClick={() => setDetail(null)}
            size="small"
            sx={{ position: 'absolute', right: 12, top: 12, color: 'var(--muted-text)' }}
          >
            <CloseIcon fontSize="small" />
          </IconButton>
        </DialogTitle>
        <DialogContent>
          {detailLoading && !detail ? (
            <CircularProgress size={18} />
          ) : detail ? (
            <>
              <Typography sx={{ color: 'var(--muted-text)', mb: 2, fontSize: '0.85rem' }}>
                {detail.description}
              </Typography>
              <Box
                component="pre"
                sx={{
                  m: 0,
                  p: 2,
                  bgcolor: 'rgba(127,127,127,0.08)',
                  border: '1px solid var(--border)',
                  borderRadius: '8px',
                  overflow: 'auto',
                  fontSize: '0.78rem',
                  whiteSpace: 'pre-wrap',
                }}
              >
                {detail.content}
              </Box>
            </>
          ) : null}
        </DialogContent>
      </Dialog>
    </Box>
  );
}
