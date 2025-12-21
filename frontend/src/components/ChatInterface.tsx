import React, { useState, useRef, useEffect } from 'react';
import {
  Box,
  Paper,
  TextField,
  IconButton,
  Typography,
  Button,
  CircularProgress,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Divider,
  Menu,
  MenuItem,
} from '@mui/material';
import {
  Send as SendIcon,
  Delete as DeleteIcon,
  SmartToy as BotIcon,
  Add as AddIcon,
  MoreVert as MoreVertIcon,
  ChevronLeft as ChevronLeftIcon,
  ChevronRight as ChevronRightIcon,
} from '@mui/icons-material';
import ChatMessage from './ChatMessage';
import { ChatMessage as ChatMessageType, ChatSession, SourceEmail } from '../types/chat';
import { logger } from '../utils/logger';

const ChatInterface: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessageType[]>([]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingSessions, setIsLoadingSessions] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sessionMenuAnchor, setSessionMenuAnchor] = useState<{ anchor: HTMLElement; sessionId: string } | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Load sessions on mount
  useEffect(() => {
    loadSessions();
  }, []);

  // Load messages when session changes
  useEffect(() => {
    if (currentSessionId) {
      loadSessionMessages(currentSessionId);
    }
  }, [currentSessionId]);

  const loadSessions = async () => {
    setIsLoadingSessions(true);
    try {
      const response = await fetch('/api/chat-sessions');
      if (!response.ok) throw new Error('Failed to load sessions');
      const data = await response.json();
      setSessions(data.chat_sessions || []);
      logger.info(`Loaded ${data.chat_sessions?.length || 0} chat sessions`);
    } catch (error) {
      logger.error('Failed to load sessions', error);
    } finally {
      setIsLoadingSessions(false);
    }
  };

  const loadSessionMessages = async (sessionId: string) => {
    try {
      const response = await fetch(`/api/chat-sessions/${sessionId}/messages`);
      if (!response.ok) throw new Error('Failed to load messages');
      const data = await response.json();
      
      // Extract messages array from response object
      const messagesArray = data.messages || [];
      
      // Convert backend messages to frontend format
      const convertedMessages: ChatMessageType[] = messagesArray.map((msg: {
        id: string;
        role: string;
        content: string;
        timestamp: string;
        sources?: string;
        confidence?: string;
        query_type?: string;
        chat_session_id?: string;
      }) => ({
        id: msg.id,
        type: msg.role as 'user' | 'assistant',
        content: msg.content,
        timestamp: new Date(msg.timestamp),
        sources: msg.sources,
        confidence: msg.confidence,
        chat_session_id: msg.chat_session_id,
      }));
      
      setMessages(convertedMessages);
      logger.info(`Loaded ${messagesArray.length} messages for session ${sessionId}`);
    } catch (error) {
      logger.error('Failed to load session messages', error);
    }
  };

  const createNewSession = async () => {
    try {
      const response = await fetch('/api/chat-sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: 'New Chat' }),
      });
      if (!response.ok) throw new Error('Failed to create session');
      const newSession = await response.json();
      
      setSessions((prev) => [newSession, ...prev]);
      setCurrentSessionId(newSession.id);
      setMessages([]);
      logger.info(`Created new session: ${newSession.id}`);
    } catch (error) {
      logger.error('Failed to create session', error);
    }
  };

  const deleteSession = async (sessionId: string) => {
    // Optimistically remove from UI immediately
    setSessions((prev) => prev.filter((s) => s.id !== sessionId));
    if (currentSessionId === sessionId) {
      setCurrentSessionId(null);
      setMessages([]);
    }
    
    try {
      const response = await fetch(`/api/chat-sessions/${sessionId}`, {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error('Failed to delete session');
      logger.info(`Deleted session: ${sessionId}`);
    } catch (error) {
      logger.error('Failed to delete session', error);
      // Reload sessions on error to restore correct state
      loadSessions();
    }
  };

  const handleSessionMenuOpen = (event: React.MouseEvent<HTMLElement>, sessionId: string) => {
    event.stopPropagation();
    setSessionMenuAnchor({ anchor: event.currentTarget, sessionId });
  };

  const handleSessionMenuClose = () => {
    setSessionMenuAnchor(null);
  };

  const handleDeleteFromMenu = async () => {
    if (sessionMenuAnchor) {
      await deleteSession(sessionMenuAnchor.sessionId);
      handleSessionMenuClose();
    }
  };

  const handleSend = async () => {
    if (!inputValue.trim() || isLoading) return;

    console.log('[CHAT INTERFACE] Starting new chat message');
    console.log(`[CHAT INTERFACE] User input: "${inputValue}"`);
    console.log(`[CHAT INTERFACE] Input length: ${inputValue.length} characters`);

    // Create session if none exists
    let sessionId = currentSessionId;
    if (!sessionId) {
      console.log('[CHAT INTERFACE] No session exists, creating new one');
      try {
        const response = await fetch('/api/chat-sessions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: 'New Chat' }),
        });
        if (!response.ok) throw new Error('Failed to create session');
        const newSession = await response.json();
        sessionId = newSession.id;
        setCurrentSessionId(sessionId);
        setSessions((prev) => [newSession, ...prev]);
        logger.info(`Created new session: ${sessionId}`);
      } catch (error) {
        logger.error('Failed to create session', error);
        return;
      }
    }

    const userMessage: ChatMessageType = {
      id: Date.now().toString(),
      type: 'user',
      content: inputValue,
      timestamp: new Date(),
      chat_session_id: sessionId ?? undefined,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    logger.info(`Sending chat query: ${inputValue}`);
    console.log('[CHAT INTERFACE] Query parameters: top_k=5, similarity_threshold=0.3');

    try {
      // Create AbortController with 5 minute timeout for LLM processing
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 300000); // 5 minutes

      console.log('[CHAT INTERFACE] Sending request to /api/query');
      const response = await fetch('/api/query', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          question: inputValue,
          chat_session_id: sessionId,
          top_k: 5,
          similarity_threshold: 0.3,
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      console.log(`[CHAT INTERFACE] Response received: status=${response.status}, ok=${response.ok}`);

      if (!response.ok) {
        console.error(`[CHAT INTERFACE] HTTP error: ${response.status} ${response.statusText}`);
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      console.log('[CHAT INTERFACE] Response data:', data);
      console.log(`[CHAT INTERFACE] Answer length: ${data.answer?.length || 0} characters`);
      console.log(`[CHAT INTERFACE] Sources count: ${data.sources?.length || 0}`);
      console.log(`[CHAT INTERFACE] Confidence: ${data.confidence}`);
      console.log(`[CHAT INTERFACE] Query type: ${data.query_type}`);

      logger.info(`Chat query successful: ${data.sources?.length || 0} sources, confidence: ${data.confidence}`);

      const sources: SourceEmail[] = data.sources?.map((source: Record<string, unknown>) => ({
        message_id: source.message_id as string,
        subject: (source.subject as string) || 'No subject',
        date: (source.date as string) || '',
        from: (source.from as string) || '',
        similarity: source.similarity || 0,
        snippet: source.snippet || '',
      })) || [];

      const assistantMessage: ChatMessageType = {
        id: (Date.now() + 1).toString(),
        type: 'assistant',
        content: data.answer || 'No answer available',
        timestamp: new Date(),
        sources: sources,
        confidence: data.confidence,
        chat_session_id: sessionId ?? undefined,
      };

      setMessages((prev) => [...prev, assistantMessage]);
      
      // Reload sessions to update message count and title (if it was auto-generated)
      await loadSessions();
    } catch (error) {
      let errorText = 'Failed to get response.';
      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          errorText = 'Query timed out after 5 minutes. Try a simpler question or check if Ollama is running.';
        } else {
          errorText = error.message;
        }
      }
      
      const errorMessage: ChatMessageType = {
        id: (Date.now() + 1).toString(),
        type: 'assistant',
        content: '',
        timestamp: new Date(),
        error: errorText,
      };

      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const exampleQuestions = [
    "What are the most important emails from this week?",
    "Summarize emails about project deadlines",
    "Find emails from my manager about meetings",
    "What action items do I have from recent emails?",
  ];

  return (
    <Box sx={{ display: 'flex', height: '100%' }}>
      {/* Chat Area */}
      <Paper
        elevation={0}
        sx={{
          flexGrow: 1,
          display: 'flex',
          flexDirection: 'column',
          bgcolor: 'background.default',
        }}
      >
        {/* Header */}
        <Box
          sx={{
            p: 2,
            minHeight: 68.5,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            bgcolor: 'background.paper',
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <BotIcon color="primary" />
            <Typography variant="h6">Email Assistant</Typography>
          </Box>
          <IconButton
            onClick={() => setSidebarOpen(!sidebarOpen)}
            size="small"
            sx={{ ml: 'auto' }}
          >
            {sidebarOpen ? <ChevronRightIcon /> : <ChevronLeftIcon />}
          </IconButton>
        </Box>

        <Divider />

        {/* Messages Area */}
        <Box
          sx={{
            flexGrow: 1,
            overflow: 'auto',
            p: 2,
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {messages.length === 0 ? (
            <Box
              sx={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                height: '100%',
                gap: 3,
              }}
            >
              <BotIcon sx={{ fontSize: 64, color: 'text.disabled' }} />
              <Typography variant="h6" color="text.secondary" align="center">
                Ask me anything about your emails
              </Typography>
              <Box sx={{ width: '100%', maxWidth: 400 }}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  Try asking:
                </Typography>
                {exampleQuestions.map((question, idx) => (
                  <Button
                    key={idx}
                    variant="outlined"
                    size="small"
                    fullWidth
                    sx={{ mb: 1, justifyContent: 'flex-start', textAlign: 'left' }}
                    onClick={() => setInputValue(question)}
                  >
                    {question}
                  </Button>
                ))}
              </Box>
            </Box>
          ) : (
            <>
              {messages.map((message) => (
                <ChatMessage key={message.id} message={message} />
              ))}
              {isLoading && (
                <Box sx={{ display: 'flex', justifyContent: 'flex-start', mb: 2 }}>
                  <Paper
                    elevation={1}
                    sx={{
                      p: 2,
                      bgcolor: 'grey.100',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 1,
                    }}
                  >
                    <CircularProgress size={20} />
                    <Typography variant="body2" color="text.secondary">
                      Thinking...
                    </Typography>
                  </Paper>
                </Box>
              )}
              <div ref={messagesEndRef} />
            </>
          )}
        </Box>

        {/* Input Area */}
        <Box
          sx={{
            p: 2,
            borderTop: 1,
            borderColor: 'divider',
            bgcolor: 'background.paper',
          }}
        >
          <Box sx={{ display: 'flex', gap: 1 }}>
            <TextField
              fullWidth
              multiline
              maxRows={4}
              placeholder="Ask a question about your emails..."
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyPress}
              disabled={isLoading}
              variant="outlined"
              size="small"
            />
            <IconButton
              color="primary"
              onClick={handleSend}
              disabled={!inputValue.trim() || isLoading}
              sx={{
                bgcolor: 'primary.main',
                color: 'white',
                '&:hover': {
                  bgcolor: 'primary.dark',
                },
                '&:disabled': {
                  bgcolor: 'action.disabledBackground',
                },
              }}
            >
              <SendIcon />
            </IconButton>
          </Box>
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
            Press Enter to send, Shift+Enter for new line
          </Typography>
        </Box>
      </Paper>

      {/* Session Sidebar (Right Side, Collapsible) */}
      {sidebarOpen && (
        <Paper
          elevation={0}
          sx={{
            width: 280,
            borderLeft: 1,
            borderColor: 'divider',
            display: 'flex',
            flexDirection: 'column',
            bgcolor: 'background.paper',
          }}
        >
          {/* New Chat Button */}
          <Box sx={{ p: 2, minHeight: 68.5 }}>
            <Button
              fullWidth
              variant="contained"
              startIcon={<AddIcon />}
              onClick={createNewSession}
            >
              New Chat
            </Button>
          </Box>

          <Divider />

          {/* Session List */}
          <List sx={{ flexGrow: 1, overflow: 'auto', py: 0 }}>
            {isLoadingSessions ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', py: 4 }}>
                <CircularProgress size={24} sx={{ mr: 1 }} />
                <Typography variant="body2" color="text.secondary">
                  Loading chats...
                </Typography>
              </Box>
            ) : sessions.length === 0 ? (
              <Box sx={{ py: 4, px: 2 }}>
                <Typography variant="body2" color="text.secondary" align="center">
                  No chat sessions yet
                </Typography>
              </Box>
            ) : (
              sessions.map((session) => (
              <ListItem
                key={session.id}
                disablePadding
                secondaryAction={
                  <IconButton
                    edge="end"
                    size="small"
                    onClick={(e) => handleSessionMenuOpen(e, session.id)}
                  >
                    <MoreVertIcon fontSize="small" />
                  </IconButton>
                }
              >
                <ListItemButton
                  selected={currentSessionId === session.id}
                  onClick={() => setCurrentSessionId(session.id)}
                >
                  <ListItemText
                    primary={session.title}
                    secondary={`${session.message_count} messages`}
                    primaryTypographyProps={{
                      noWrap: true,
                      fontSize: '0.875rem',
                    }}
                    secondaryTypographyProps={{
                      fontSize: '0.75rem',
                    }}
                  />
                </ListItemButton>
              </ListItem>
              ))
            )}
          </List>

          {/* Session Menu */}
          <Menu
            anchorEl={sessionMenuAnchor?.anchor}
            open={Boolean(sessionMenuAnchor)}
            onClose={handleSessionMenuClose}
          >
            <MenuItem onClick={handleDeleteFromMenu}>
              <DeleteIcon fontSize="small" sx={{ mr: 1 }} />
              Delete
            </MenuItem>
          </Menu>
        </Paper>
      )}
    </Box>
  );
};

export default ChatInterface;
