import React, { useState } from 'react';
import {
  ListItem,
  ListItemText,
  IconButton,
  Collapse,
  Typography,
  Box,
  Chip,
  CircularProgress,
  Snackbar,
  Alert,
  Tooltip,
} from '@mui/material';
import {
  Delete as DeleteIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';
import { Email } from '../types/email';
import { logger } from '../utils/logger';
import EmailBodyRenderer from './EmailBodyRenderer';

const getPriorityColor = (priority: Email['priority']): 'error' | 'warning' | 'success' | 'default' => {
  switch (priority.toLowerCase()) {
    case 'high':
      return 'error';
    case 'normal':
      return 'warning';
    case 'low':
      return 'success';
    case 'unclassified':
      return 'default';
    default:
      return 'default';
  }
};

interface EmailItemProps {
  email: Email;
  isExpanded: boolean;
  onExpand: (id: string) => void;
  onDelete: (id: string) => void;
  onReclassify?: (id: string) => void;
  selectedModel?: string;
}

const EmailItem: React.FC<EmailItemProps> = ({ email, isExpanded, onExpand, onDelete, onReclassify, selectedModel = 'gemma:2b' }) => {
  const [isReclassifying, setIsReclassifying] = useState(false);
  const [snackbar, setSnackbar] = useState<{
    open: boolean;
    message: string;
    severity: 'success' | 'error' | 'warning' | 'info';
  }>({
    open: false,
    message: '',
    severity: 'info',
  });

  const handleCloseSnackbar = () => {
    setSnackbar({ ...snackbar, open: false });
  };

  const showMessage = (message: string, severity: 'success' | 'error' | 'warning' | 'info') => {
    setSnackbar({ open: true, message, severity });
  };

  const handleReclassify = async () => {
    // Check if model is selected
    if (!selectedModel || selectedModel.trim() === '') {
      showMessage('Please select an LLM model first', 'warning');
      return;
    }

    setIsReclassifying(true);
    showMessage('Classifying message...', 'info');
    logger.info(`Reclassifying email ${email.id} with model ${selectedModel}`);

    try {
      const response = await fetch(`/messages/${email.id}/reclassify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: selectedModel })
      });

      if (response.ok) {
        const result = await response.json();
        logger.info(`Email ${email.id} reclassified successfully: ${result.priority}`);
        showMessage(`Successfully classified! Priority: ${result.priority || 'N/A'}`, 'success');

        // Trigger parent refresh after a short delay to show success message
        setTimeout(() => {
          if (onReclassify) {
            onReclassify(email.id);
          }
        }, 1000);
      } else {
        const errorText = await response.text();
        let errorMessage = 'Classification failed';

        try {
          const errorJson = JSON.parse(errorText);
          if (errorJson.detail) {
            errorMessage = errorJson.detail;
          }
        } catch {
          // If not JSON, use the text directly if it's not too long
          if (errorText.length < 100) {
            errorMessage = errorText;
          }
        }

        // Check for common errors
        if (response.status === 503 || errorMessage.includes('LLM') || errorMessage.includes('provider')) {
          showMessage('LLM service is not available. Please ensure your LLM server is running.', 'error');
        } else if (response.status === 404) {
          showMessage('Message not found', 'error');
        } else {
          showMessage(errorMessage, 'error');
        }
      }
    } catch (error) {
      // Network or connection error
      if (error instanceof TypeError && error.message.includes('fetch')) {
        showMessage('Cannot connect to backend server. Please ensure the API is running.', 'error');
      } else {
        showMessage('An unexpected error occurred during classification', 'error');
      }
      console.error('Reclassification error:', error);
    } finally {
      setIsReclassifying(false);
    }
  };

  return (
    <React.Fragment>
      <ListItem
        alignItems="flex-start"
        sx={{
          cursor: 'pointer',
          '&:hover': { backgroundColor: 'action.hover' },
          borderBottom: '1px solid',
          borderColor: 'divider',
          bgcolor: 'background.paper',
          mb: 2,
          borderRadius: 1,
          p: 2,
          boxShadow: 1,
          display: 'flex',
          alignItems: 'center',
        }}
      >
        <Box sx={{ display: 'flex', flexDirection: 'column', flexGrow: 1 }}>
          <Box
            sx={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              width: '100%',
            }}
            onClick={() => onExpand(email.id)}
            data-testid="email-item-clickable"
          >
            <ListItemText
              primary={
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                  <Typography variant="subtitle1">{email.subject}</Typography>
                  <Chip
                    label={email.priority}
                    size="small"
                    color={getPriorityColor(email.priority)}
                  />
                  {email.classificationLabels && email.classificationLabels.length > 0 && (
                    <>
                      {email.classificationLabels.map((label, idx) => (
                        <Chip
                          key={idx}
                          label={label}
                          size="small"
                          variant="outlined"
                          sx={{ fontSize: '0.7rem' }}
                        />
                      ))}
                    </>
                  )}
                </Box>
              }
              secondary={
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{ mt: 1 }}
                >
                  {email.summary}
                </Typography>
              }
            />
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography variant="caption" color="text.secondary">
                {email.date}
              </Typography>
              {isExpanded ? (
                <ExpandLessIcon />
              ) : (
                <ExpandMoreIcon />
              )}
            </Box>
          </Box>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, ml: 2 }}>
          <Tooltip title={isReclassifying ? 'Classifying...' : `Classify with ${selectedModel}`}>
            <span>
              <IconButton
                size="small"
                aria-label="reclassify"
                onClick={(e) => {
                  e.stopPropagation();
                  handleReclassify();
                }}
                disabled={isReclassifying}
                sx={{ color: 'primary.main' }}
              >
                {isReclassifying ? <CircularProgress size={20} /> : <RefreshIcon />}
              </IconButton>
            </span>
          </Tooltip>
          <IconButton
            edge="end"
            aria-label="delete"
            onClick={(e) => {
              e.stopPropagation();
              onDelete(email.id);
            }}
            sx={{ ml: 1 }}
          >
            <DeleteIcon />
          </IconButton>
        </Box>
      </ListItem>
      <Collapse in={isExpanded} timeout="auto" unmountOnExit>
        <Box sx={{ p: 3, backgroundColor: 'action.hover', borderLeft: 3, borderColor: 'primary.main', ml: 2, mr: 2, mb: 2, borderRadius: 1 }}>
          <Box sx={{ mb: 2 }}>
            <Typography variant="subtitle2" color="text.secondary" sx={{ fontWeight: 'bold' }}>
              Subject:
            </Typography>
            <Typography variant="body1" sx={{ mb: 1 }}>
              {email.subject}
            </Typography>
          </Box>

          <Box sx={{ mb: 2 }}>
            <Typography variant="subtitle2" color="text.secondary" sx={{ fontWeight: 'bold' }}>
              Date:
            </Typography>
            <Typography variant="body1" sx={{ mb: 1 }}>
              {email.date}
            </Typography>
          </Box>

          <Box>
            <Typography variant="subtitle2" color="text.secondary" sx={{ fontWeight: 'bold', mb: 1 }}>
              Body:
            </Typography>
            <EmailBodyRenderer html={email.html || ''} plainText={email.plain_text || email.body || ''} />
          </Box>
        </Box>
      </Collapse>

      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={handleCloseSnackbar}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <Alert onClose={handleCloseSnackbar} severity={snackbar.severity} sx={{ width: '100%' }}>
          {snackbar.message}
        </Alert>
      </Snackbar>
    </React.Fragment>
  );
};

export default EmailItem;
