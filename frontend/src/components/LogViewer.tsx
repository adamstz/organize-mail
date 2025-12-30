import React, { useState, useEffect, useRef } from 'react';
import { Box, Typography, IconButton, Tooltip, Chip, TextField } from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import DeleteSweepIcon from '@mui/icons-material/DeleteSweep';
import PauseIcon from '@mui/icons-material/Pause';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import DownloadIcon from '@mui/icons-material/Download';

interface LogEntry {
  timestamp: string;
  level: string;
  logger: string;
  message: string;
}

interface LogViewerProps {
  onClose?: () => void;
}

const LogViewer: React.FC<LogViewerProps> = ({ onClose }) => {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [isPaused, setIsPaused] = useState(false);
  const [filterText, setFilterText] = useState('');
  const [autoScroll, setAutoScroll] = useState(true);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    // Fetch initial logs
    fetch('/api/logs')
      .then(res => res.json())
      .then(data => setLogs(data))
      .catch(err => console.error('Failed to fetch logs:', err));

    // Connect to WebSocket for real-time updates
    // Determine WebSocket URL based on current location
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/logs`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      if (!isPaused) {
        const logEntry: LogEntry = JSON.parse(event.data);
        setLogs(prev => [...prev, logEntry].slice(-500)); // Keep last 500 logs
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    ws.onclose = () => {
      console.log('WebSocket connection closed');
    };

    return () => {
      ws.close();
    };
  }, [isPaused]);

  useEffect(() => {
    if (autoScroll && !isPaused) {
      logsEndRef.current?.scrollIntoView({ behavior: 'auto' });
    }
  }, [logs, autoScroll, isPaused]);

  const handleClearLogs = () => {
    setLogs([]);
  };

  const handleTogglePause = () => {
    setIsPaused(!isPaused);
  };

  const handleDownloadLogs = () => {
    const logText = logs.map(log => 
      `[${log.timestamp}] ${log.level} ${log.logger}: ${log.message}`
    ).join('\n');
    
    const blob = new Blob([logText], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `logs-${new Date().toISOString()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const getLevelColor = (level: string) => {
    switch (level.toUpperCase()) {
      case 'ERROR':
      case 'CRITICAL':
        return '#f44336';
      case 'WARNING':
        return '#ff9800';
      case 'INFO':
        return '#2196f3';
      case 'DEBUG':
        return '#9e9e9e';
      default:
        return '#757575';
    }
  };

  const filteredLogs = filterText
    ? logs.filter(log => 
        log.message.toLowerCase().includes(filterText.toLowerCase()) ||
        log.logger.toLowerCase().includes(filterText.toLowerCase()) ||
        log.level.toLowerCase().includes(filterText.toLowerCase())
      )
    : logs;

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', bgcolor: 'background.default' }}>
      {/* Header */}
      <Box sx={{ 
        p: 1.5, 
        borderBottom: 1, 
        borderColor: 'divider',
        bgcolor: 'background.paper',
        display: 'flex',
        alignItems: 'center',
        gap: 1
      }}>
        <Typography variant="h6" sx={{ flexGrow: 1, color: 'text.primary', fontSize: '1rem' }}>
          System Logs
        </Typography>
        <Chip 
          label={`${filteredLogs.length} entries`} 
          size="small" 
          sx={{ bgcolor: 'action.selected', color: 'text.primary' }}
        />
        <Tooltip title={isPaused ? "Resume" : "Pause"}>
          <IconButton size="small" onClick={handleTogglePause} sx={{ color: 'text.primary' }}>
            {isPaused ? <PlayArrowIcon /> : <PauseIcon />}
          </IconButton>
        </Tooltip>
        <Tooltip title="Download Logs">
          <IconButton size="small" onClick={handleDownloadLogs} sx={{ color: 'text.primary' }}>
            <DownloadIcon />
          </IconButton>
        </Tooltip>
        <Tooltip title="Clear Logs">
          <IconButton size="small" onClick={handleClearLogs} sx={{ color: 'text.primary' }}>
            <DeleteSweepIcon />
          </IconButton>
        </Tooltip>
        {onClose && (
          <Tooltip title="Close">
            <IconButton size="small" onClick={onClose} sx={{ color: 'text.primary' }}>
              <CloseIcon />
            </IconButton>
          </Tooltip>
        )}
      </Box>

      {/* Filter */}
      <Box sx={{ p: 1, bgcolor: 'background.paper', borderBottom: 1, borderColor: 'divider' }}>
        <TextField
          size="small"
          fullWidth
          placeholder="Filter logs..."
          value={filterText}
          onChange={(e) => setFilterText(e.target.value)}
          sx={{
            '& .MuiOutlinedInput-root': {
              color: 'text.primary',
              bgcolor: 'background.default',
              '& fieldset': { borderColor: 'divider' },
              '&:hover fieldset': { borderColor: 'text.secondary' },
              '&.Mui-focused fieldset': { borderColor: 'primary.main' },
            },
          }}
        />
      </Box>

      {/* Log Content */}
      <Box 
        sx={{ 
          flexGrow: 1, 
          overflow: 'auto', 
          p: 1,
          fontFamily: 'monospace',
          fontSize: '0.8rem',
          color: 'text.primary'
        }}
        onScroll={(e) => {
          const target = e.target as HTMLDivElement;
          const isAtBottom = target.scrollHeight - target.scrollTop <= target.clientHeight + 50;
          setAutoScroll(isAtBottom);
        }}
      >
        {filteredLogs.length === 0 ? (
          <Typography sx={{ color: 'text.secondary', textAlign: 'center', mt: 4 }}>
            No logs to display
          </Typography>
        ) : (
          filteredLogs.map((log, index) => (
            <Box
              key={index}
              sx={{
                mb: 0.5,
                p: 0.5,
                borderLeft: 3,
                borderColor: getLevelColor(log.level),
                bgcolor: 'action.hover',
                borderRadius: 0.5,
                '&:hover': { bgcolor: 'action.selected' }
              }}
            >
              <Box sx={{ display: 'flex', gap: 1, alignItems: 'baseline', flexWrap: 'wrap' }}>
                <Typography 
                  component="span" 
                  sx={{ color: 'text.secondary', fontSize: '0.75rem', minWidth: 80 }}
                >
                  {new Date(log.timestamp).toLocaleTimeString()}
                </Typography>
                <Chip
                  label={log.level}
                  size="small"
                  sx={{
                    height: 18,
                    fontSize: '0.7rem',
                    bgcolor: getLevelColor(log.level),
                    color: 'common.white',
                    fontWeight: 'bold'
                  }}
                />
                <Typography 
                  component="span" 
                  sx={{ color: 'primary.main', fontSize: '0.75rem' }}
                >
                  {log.logger}
                </Typography>
              </Box>
              <Typography sx={{ mt: 0.5, color: 'text.primary', wordBreak: 'break-word' }}>
                {log.message}
              </Typography>
            </Box>
          ))
        )}
        <div ref={logsEndRef} />
      </Box>
    </Box>
  );
};

export default LogViewer;
