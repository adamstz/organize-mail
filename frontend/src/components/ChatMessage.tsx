import React, { useState } from 'react';
import {
  Box,
  Paper,
  Typography,
  IconButton,
  Collapse,
  Chip,
  Tooltip,
} from '@mui/material';
import {
  ContentCopy as CopyIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
} from '@mui/icons-material';
import { ChatMessage as ChatMessageType } from '../types/chat';

interface ChatMessageProps {
  message: ChatMessageType;
}

const ChatMessage: React.FC<ChatMessageProps> = ({ message }) => {
  const [showSources, setShowSources] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString('en-US', { 
      hour: '2-digit', 
      minute: '2-digit' 
    });
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { 
      month: 'short', 
      day: 'numeric', 
      year: 'numeric' 
    });
  };

  if (message.type === 'user') {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 2 }}>
        <Paper
          elevation={1}
          sx={{
            p: 2,
            maxWidth: '75%',
            bgcolor: 'primary.main',
            color: 'primary.contrastText',
          }}
        >
          <Typography variant="body1">{message.content}</Typography>
          <Typography variant="caption" sx={{ opacity: 0.8, mt: 0.5, display: 'block' }}>
            {formatTime(message.timestamp)}
          </Typography>
        </Paper>
      </Box>
    );
  }

  // Assistant message
  return (
    <Box sx={{ display: 'flex', justifyContent: 'flex-start', mb: 2 }}>
      <Paper
        elevation={1}
        sx={{
          p: 2,
          maxWidth: '85%',
          bgcolor: 'grey.100',
        }}
      >
        {message.error ? (
          <Typography variant="body1" color="error">
            {message.error}
          </Typography>
        ) : (
          <>
            <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
              <Typography variant="body1" sx={{ flexGrow: 1 }}>
                {message.content}
              </Typography>
              <Tooltip title={copied ? 'Copied!' : 'Copy answer'}>
                <IconButton size="small" onClick={handleCopy}>
                  <CopyIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Box>

            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1 }}>
              <Typography variant="caption" color="text.secondary">
                {formatTime(message.timestamp)}
              </Typography>
              {message.confidence && (
                <Chip 
                  label={`Confidence: ${message.confidence}`} 
                  size="small" 
                  variant="outlined"
                  sx={{ height: 20 }}
                />
              )}
            </Box>

            {message.sources && message.sources.length > 0 && (
              <Box sx={{ mt: 2 }}>
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    cursor: 'pointer',
                    mb: 1,
                  }}
                  onClick={() => setShowSources(!showSources)}
                >
                  <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 500 }}>
                    Sources ({message.sources.length})
                  </Typography>
                  <IconButton size="small">
                    {showSources ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                  </IconButton>
                </Box>

                <Collapse in={showSources}>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                    {message.sources.map((source) => (
                      <Paper
                        key={source.message_id}
                        variant="outlined"
                        sx={{
                          p: 1.5,
                          bgcolor: 'background.paper',
                          cursor: 'pointer',
                          '&:hover': {
                            bgcolor: 'action.hover',
                          },
                        }}
                      >
                        <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', mb: 0.5 }}>
                          <Typography variant="body2" sx={{ fontWeight: 500, flexGrow: 1 }}>
                            {source.subject}
                          </Typography>
                          <Chip
                            label={`${(source.similarity * 100).toFixed(0)}%`}
                            size="small"
                            color={source.similarity > 0.8 ? 'success' : source.similarity > 0.6 ? 'primary' : 'default'}
                            sx={{ ml: 1, height: 20 }}
                          />
                        </Box>
                        {source.from && (
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                            From: {source.from}
                          </Typography>
                        )}
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                          {formatDate(source.date)}
                        </Typography>
                        {source.snippet && (
                          <Typography variant="body2" color="text.secondary" sx={{ mt: 1, fontStyle: 'italic' }}>
                            "{source.snippet.length > 150 ? source.snippet.slice(0, 150) + '...' : source.snippet}"
                          </Typography>
                        )}
                      </Paper>
                    ))}
                  </Box>
                </Collapse>
              </Box>
            )}
          </>
        )}
      </Paper>
    </Box>
  );
};

export default ChatMessage;
