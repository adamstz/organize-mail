import React, { useState, useRef, useEffect } from 'react';
import {
  Box,
  Paper,
  TextField,
  IconButton,
  Typography,
  Button,
  CircularProgress,
} from '@mui/material';
import {
  Send as SendIcon,
  Delete as DeleteIcon,
  SmartToy as BotIcon,
} from '@mui/icons-material';
import ChatMessage from './ChatMessage';
import { ChatMessage as ChatMessageType, SourceEmail } from '../types/chat';

const ChatInterface: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessageType[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!inputValue.trim() || isLoading) return;

    const userMessage: ChatMessageType = {
      id: Date.now().toString(),
      type: 'user',
      content: inputValue,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    try {
      // Create AbortController with 5 minute timeout for LLM processing
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 300000); // 5 minutes

      const response = await fetch('/api/query', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          question: inputValue,
          top_k: 5,
          similarity_threshold: 0.3,
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();

      const sources: SourceEmail[] = data.sources?.map((source: any) => ({
        message_id: source.message_id,
        subject: source.subject || 'No subject',
        date: source.date || '',
        from: source.from || '',
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
      };

      setMessages((prev) => [...prev, assistantMessage]);
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

  const handleClearChat = () => {
    setMessages([]);
  };

  const exampleQuestions = [
    "What are the most important emails from this week?",
    "Summarize emails about project deadlines",
    "Find emails from my manager about meetings",
    "What action items do I have from recent emails?",
  ];

  return (
    <Paper
      elevation={0}
      sx={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        bgcolor: 'background.default',
      }}
    >
      {/* Header */}
      <Box
        sx={{
          p: 2,
          borderBottom: 1,
          borderColor: 'divider',
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
        {messages.length > 0 && (
          <Button
            startIcon={<DeleteIcon />}
            onClick={handleClearChat}
            size="small"
            color="error"
          >
            Clear
          </Button>
        )}
      </Box>

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
            onKeyPress={handleKeyPress}
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
  );
};

export default ChatInterface;
