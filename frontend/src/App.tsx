import React, { useState, useCallback, useEffect } from 'react';
import { ThemeProvider, CssBaseline, Container, AppBar, Toolbar, Typography, Box, IconButton, Tooltip } from '@mui/material';
import { createTheme } from '@mui/material/styles';
import ChatIcon from '@mui/icons-material/Chat';
import ChatBubbleOutlineIcon from '@mui/icons-material/ChatBubbleOutline';
import TerminalIcon from '@mui/icons-material/Terminal';
import EmailList from './components/EmailList';
import EmailToolbar from './components/EmailToolbar';
import SyncStatus from './components/SyncStatus';
import ChatInterface from './components/ChatInterface';
import LogViewer from './components/LogViewer';
import { logger } from './utils/logger';

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1976d2',
    },
  },
});

const App: React.FC = () => {
  const [filters, setFilters] = useState<{
    priority: string | null;
    labels: string[];
    status: 'all' | 'classified' | 'unclassified';
  }>({
    priority: null,
    labels: [],
    status: 'all',
  });
  const [searchQuery, setSearchQuery] = useState('');
  const [sortOrder, setSortOrder] = useState<'recent' | 'oldest'>('recent');
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [isChatVisible, setIsChatVisible] = useState(true);
  const [isLogsVisible, setIsLogsVisible] = useState(false);
  const [chatWidth, setChatWidth] = useState(41.67); // Default ~5/12 columns in percentage
  const [isDragging, setIsDragging] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  // Fetch available models and auto-select first one on mount
  useEffect(() => {
    const fetchAndSelectModel = async () => {
      try {
        console.log('[App] Fetching current model...');
        // First try to get current model from backend
        const currentModelRes = await fetch('/api/current-model');
        if (currentModelRes.ok) {
          const data = await currentModelRes.json();
          console.log('[App] Current model from backend:', data);
          if (data.model && data.model.trim() !== '') {
            console.log('[App] Setting model from backend:', data.model);
            setSelectedModel(data.model);
            return;
          }
        }
        
        console.log('[App] No current model, fetching available models...');
        // If no current model set, fetch available models and select first
        const modelsRes = await fetch('/models');
        if (modelsRes.ok) {
          const modelsData = await modelsRes.json();
          console.log('[App] Available models:', modelsData);
          if (modelsData.models && modelsData.models.length > 0) {
            const firstModel = modelsData.models[0].name;
            console.log('[App] Auto-selecting first model:', firstModel);
            setSelectedModel(firstModel);
            // Also set it on the backend
            const setModelRes = await fetch('/api/set-model', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ model: firstModel }),
            });
            console.log('[App] Set model response:', setModelRes.ok);
          }
        }
      } catch (error) {
        console.error('[App] Failed to fetch and select model:', error);
      }
    };
    fetchAndSelectModel();
  }, []);

  const handleModelChange = (model: string) => {
    setSelectedModel(model);
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isDragging) return;

    const container = document.querySelector('.resizable-container');
    if (!container) return;

    const containerRect = container.getBoundingClientRect();
    const newChatWidth = ((containerRect.right - e.clientX) / containerRect.width) * 100;

    // Constrain between 20% and 70%
    if (newChatWidth >= 20 && newChatWidth <= 70) {
      setChatWidth(newChatWidth);
    }
  }, [isDragging]);

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  React.useEffect(() => {
    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    } else {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isDragging, handleMouseMove, handleMouseUp]);

  const handleStatusChange = (_event: React.MouseEvent<HTMLElement>, newStatus: 'all' | 'classified' | 'unclassified' | null) => {
    if (newStatus !== null) {
      setFilters({ ...filters, status: newStatus });
    }
  };

  const clearAllFilters = () => {
    setFilters({ priority: null, labels: [], status: 'all' });
  };

  const handleLabelFilter = (label: string) => {
    // Toggle label filter: add or remove from array
    if (filters.labels.includes(label)) {
      // Remove this label
      setFilters({ ...filters, labels: filters.labels.filter(l => l !== label) });
    } else {
      // Add this label
      setFilters({ ...filters, labels: [...filters.labels, label] });
    }
  };

  const handlePriorityFilter = (priority: string) => {
    // Toggle priority filter: if already selected, clear it; otherwise set it
    if (filters.priority === priority) {
      setFilters({ ...filters, priority: null });
    } else {
      setFilters({ ...filters, priority });
    }
  };

  const toggleSortOrder = () => {
    setSortOrder(prev => prev === 'recent' ? 'oldest' : 'recent');
  };



  // Log when app loads
  React.useEffect(() => {
    logger.info('Organize Mail application started');
  }, []);

  // Handler to refresh email list after sync
  const handleSyncRefresh = () => {
    setRefreshKey(prev => prev + 1);
    logger.info('Email list refreshed after sync operation');
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AppBar position="static">
        <Toolbar>
          <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
            Organize Mail
          </Typography>
          <Tooltip title={isLogsVisible ? "Hide Logs" : "Show Logs"}>
            <IconButton
              color="inherit"
              onClick={() => setIsLogsVisible(!isLogsVisible)}
              sx={{ display: { xs: 'none', md: 'flex' } }}
            >
              <TerminalIcon />
            </IconButton>
          </Tooltip>
          <Tooltip title={isChatVisible ? "Hide Chat" : "Show Chat"}>
            <IconButton
              color="inherit"
              onClick={() => setIsChatVisible(!isChatVisible)}
              sx={{ display: { xs: 'none', md: 'flex' } }}
            >
              {isChatVisible ? <ChatIcon /> : <ChatBubbleOutlineIcon />}
            </IconButton>
          </Tooltip>
        </Toolbar>
      </AppBar>
      <Container
        maxWidth={false}
        disableGutters
        className="resizable-container"
        sx={{
          height: 'calc(100vh - 64px)', // Subtract AppBar height
          width: '100vw',
          bgcolor: 'grey.100',
          display: 'flex',
          p: 0,
          overflow: 'hidden',
          position: 'relative'
        }}
      >
        <Box sx={{
          width: (isChatVisible || isLogsVisible) ? `${100 - chatWidth}%` : '100%',
          height: '100%',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          transition: isDragging ? 'none' : 'width 0.2s ease'
        }}>
          <Box sx={{ p: 2, flexGrow: 1, overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
            <SyncStatus onRefresh={handleSyncRefresh} />

            <EmailToolbar
              searchQuery={searchQuery}
              onSearchChange={setSearchQuery}
              sortOrder={sortOrder}
              onSortToggle={toggleSortOrder}
              filters={filters}
              onStatusChange={handleStatusChange}
              onClearAllFilters={clearAllFilters}
              onLabelFilter={handleLabelFilter}
              onPriorityFilter={handlePriorityFilter}
              selectedModel={selectedModel}
              onModelChange={handleModelChange}
            />

            <EmailList
              key={refreshKey}
              filters={filters}
              searchQuery={searchQuery}
              sortOrder={sortOrder}
              selectedModel={selectedModel}
            />
          </Box>
        </Box>

        {(isChatVisible || isLogsVisible) && (
          <>
            {/* Draggable Divider */}
            <Box
              onMouseDown={handleMouseDown}
              sx={{
                width: '4px',
                height: '100%',
                bgcolor: 'divider',
                cursor: 'col-resize',
                position: 'relative',
                zIndex: 10,
                '&:hover': {
                  bgcolor: 'primary.main',
                  width: '6px',
                },
                '&:active': {
                  bgcolor: 'primary.dark',
                },
                display: { xs: 'none', md: 'block' }
              }}
            />

            {/* Right Side Panel - Chat and/or Logs */}
            <Box sx={{
              width: `${chatWidth}%`,
              height: '100%',
              overflow: 'hidden',
              bgcolor: 'background.default',
              display: { xs: 'none', md: 'flex' },
              flexDirection: 'column',
              transition: isDragging ? 'none' : 'width 0.2s ease'
            }}>
              {/* Chat Only */}
              {isChatVisible && !isLogsVisible && <ChatInterface />}

              {/* Logs Only */}
              {!isChatVisible && isLogsVisible && <LogViewer onClose={() => setIsLogsVisible(false)} />}

              {/* Split View - Chat and Logs */}
              {isChatVisible && isLogsVisible && (
                <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                  <Box sx={{ height: '50%', overflow: 'hidden', borderBottom: 1, borderColor: 'divider' }}>
                    <ChatInterface />
                  </Box>
                  <Box sx={{ height: '50%', overflow: 'hidden' }}>
                    <LogViewer onClose={() => setIsLogsVisible(false)} />
                  </Box>
                </Box>
              )}
            </Box>
          </>
        )}
      </Container>
    </ThemeProvider>
  );
};

export default App;
