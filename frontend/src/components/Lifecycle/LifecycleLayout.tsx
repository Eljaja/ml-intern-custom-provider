import type { ReactNode } from 'react';
import { Box, IconButton, Avatar, Tooltip, Button } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';
import DarkModeOutlinedIcon from '@mui/icons-material/DarkModeOutlined';
import LightModeOutlinedIcon from '@mui/icons-material/LightModeOutlined';
import ChatIcon from '@mui/icons-material/Chat';
import DeveloperBoardOutlinedIcon from '@mui/icons-material/DeveloperBoardOutlined';
import HubIcon from '@mui/icons-material/Hub';
import { useLayoutStore } from '@/store/layoutStore';
import { useAgentStore } from '@/store/agentStore';
import { useAuth } from '@/hooks/useAuth';

export default function LifecycleLayout({ children }: { children: ReactNode }) {
  useAuth();
  const { themeMode, toggleTheme } = useLayoutStore();
  const user = useAgentStore((s) => s.user);

  return (
    <Box
      sx={{
        width: '100%',
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        bgcolor: 'background.default',
        background: 'var(--body-gradient)',
      }}
    >
      <Box
        component="header"
        sx={{
          height: { xs: 56, md: 64 },
          px: { xs: 1.5, md: 2.5 },
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          borderBottom: 1,
          borderColor: 'divider',
          bgcolor: 'var(--panel)',
          flexShrink: 0,
          boxShadow: 'var(--shadow-1)',
        }}
      >
        <Box
          component={RouterLink}
          to="/tasks"
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            textDecoration: 'none',
            color: 'text.primary',
            mr: 1,
          }}
        >
          <HubIcon sx={{ color: 'primary.main', fontSize: 28 }} />
          <Box sx={{ display: { xs: 'none', sm: 'block' } }}>
            <Box sx={{ fontWeight: 800, fontSize: '0.95rem', letterSpacing: '-0.02em', lineHeight: 1.2 }}>
              ML Control Plane
            </Box>
            <Box sx={{ fontSize: '0.68rem', color: 'text.secondary', fontWeight: 500 }}>
              Tasks · Runs · Jobs · Artifacts
            </Box>
          </Box>
        </Box>

        <Button
          component={RouterLink}
          to="/tasks/board"
          size="small"
          startIcon={<DeveloperBoardOutlinedIcon />}
          variant="outlined"
          sx={{
            borderColor: 'var(--border)',
            color: 'text.secondary',
            fontWeight: 600,
            display: { xs: 'none', sm: 'inline-flex' },
            '&:hover': { borderColor: 'primary.main', color: 'primary.main' },
          }}
        >
          Board
        </Button>

        <Button
          component={RouterLink}
          to="/"
          size="small"
          startIcon={<ChatIcon />}
          variant="outlined"
          sx={{
            borderColor: 'var(--border)',
            color: 'text.secondary',
            fontWeight: 600,
            '&:hover': { borderColor: 'primary.main', color: 'primary.main' },
          }}
        >
          Chat
        </Button>

        <Box sx={{ flex: 1 }} />

        <Tooltip title={themeMode === 'dark' ? 'Light mode' : 'Dark mode'}>
          <IconButton onClick={toggleTheme} size="small" sx={{ color: 'text.secondary' }}>
            {themeMode === 'dark' ? <LightModeOutlinedIcon /> : <DarkModeOutlinedIcon />}
          </IconButton>
        </Tooltip>

        {user?.picture ? (
          <Avatar src={user.picture} alt={user.username || 'User'} sx={{ width: 30, height: 30 }} />
        ) : user?.username ? (
          <Avatar sx={{ width: 30, height: 30, bgcolor: 'primary.main', fontSize: '0.8rem', fontWeight: 700 }}>
            {user.username[0].toUpperCase()}
          </Avatar>
        ) : null}
      </Box>

      <Box
        component="main"
        sx={{
          flex: 1,
          overflow: 'auto',
          p: { xs: 2, md: 3 },
          width: '100%',
          maxWidth: '100%',
          mx: 'auto',
        }}
      >
        {children}
      </Box>
    </Box>
  );
}
