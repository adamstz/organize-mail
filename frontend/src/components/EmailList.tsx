import React, { useState } from 'react';
import {
  List,
  ListItem,
  ListItemText,
  IconButton,
  Collapse,
  Paper,
  Typography,
  Box,
  Chip,
} from '@mui/material';
import {
  Delete as DeleteIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
} from '@mui/icons-material';
import { Email } from '../types/email';

// Example email data
const exampleEmails: Email[] = [
  {
    id: 1,
    subject: 'Project Update Meeting',
    date: '2025-10-14',
    priority: 'High',
    summary: 'Discussion about Q4 milestones and upcoming deadlines',
    body: "Dear team,\n\nI wanted to follow up on our project status and discuss the upcoming milestones for Q4. We need to ensure we're on track with our deliverables and address any potential blockers.\n\nBest regards,\nJohn",
  },
  {
    id: 2,
    subject: 'New Feature Release',
    date: '2025-10-13',
    priority: 'Medium',
    summary: 'Announcing the release of our new dashboard features',
    body: "Hello everyone,\n\nWe're excited to announce the release of our new dashboard features. This includes improved analytics, customizable widgets, and better performance optimizations.\n\nRegards,\nProduct Team",
  },
  {
    id: 3,
    subject: 'Team Lunch Next Week',
    date: '2025-10-12',
    priority: 'Low',
    summary: 'Planning for team lunch and social gathering',
    body: "Hi all,\n\nLet's plan for a team lunch next week to celebrate our recent successes. Please fill out the preference form for restaurant options.\n\nCheers,\nHR Team",
  },
];

const getPriorityColor = (priority: Email['priority']): 'error' | 'warning' | 'success' | 'default' => {
  switch (priority.toLowerCase()) {
    case 'high':
      return 'error';
    case 'medium':
      return 'warning';
    case 'low':
      return 'success';
    default:
      return 'default';
  }
};

const EmailList: React.FC = () => {
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [emails, setEmails] = useState<Email[]>(exampleEmails);

  const handleExpand = (id: number): void => {
    setExpandedId(expandedId === id ? null : id);
  };

  const handleDelete = (id: number): void => {
    setEmails(emails.filter(email => email.id !== id));
  };

  return (
    <Paper elevation={0} sx={{ width: "100%", p: 2, bgcolor: 'transparent' }}>
      <List sx={{ width: '100%', maxWidth: 'none' }}>
        {emails.map((email) => (
          <React.Fragment key={email.id}>
            <ListItem
              alignItems="flex-start"
              sx={{
                cursor: 'pointer',
                '&:hover': { backgroundColor: 'action.hover' },
                borderBottom: '1px solid',
                borderColor: 'divider',
                bgcolor: 'background.paper',
                mb: 1,
                borderRadius: 1,
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
                  onClick={() => handleExpand(email.id)}
                >
                  <ListItemText
                    primary={
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Typography variant="subtitle1">{email.subject}</Typography>
                        <Chip
                          label={email.priority}
                          size="small"
                          color={getPriorityColor(email.priority)}
                        />
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
                    {expandedId === email.id ? (
                      <ExpandLessIcon />
                    ) : (
                      <ExpandMoreIcon />
                    )}
                  </Box>
                </Box>
              </Box>
              <IconButton
                edge="end"
                aria-label="delete"
                onClick={() => handleDelete(email.id)}
                sx={{ ml: 2 }}
              >
                <DeleteIcon />
              </IconButton>
            </ListItem>
            <Collapse in={expandedId === email.id} timeout="auto" unmountOnExit>
              <Box sx={{ p: 3, backgroundColor: 'grey.50' }}>
                <Typography variant="body1" whiteSpace="pre-line">
                  {email.body}
                </Typography>
              </Box>
            </Collapse>
          </React.Fragment>
        ))}
      </List>
    </Paper>
  );
};

export default EmailList;