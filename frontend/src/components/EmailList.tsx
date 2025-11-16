import React, { useState, useEffect } from 'react';
import {
  List,
  Paper,
  Typography,
  Box,
  CircularProgress,
  Pagination,
} from '@mui/material';
import { Email } from '../types/email';
import EmailItem from './EmailItem';
import { parseBackendMessage } from '../utils/emailParser';
import exampleEmails from '../test/exampleEmails';

interface EmailListProps {
  filter?: { type: 'priority' | 'label' | 'status' | null; value: string | null };
  searchQuery?: string;
  sortOrder?: 'recent' | 'oldest';
  selectedModel?: string;
}

const EmailList: React.FC<EmailListProps> = ({ filter, searchQuery = '', sortOrder = 'recent', selectedModel = 'gemma:2b' }) => {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [emails, setEmails] = useState<Email[]>(exampleEmails);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState<number>(1); // MUI Pagination is 1-indexed
  const [totalCount, setTotalCount] = useState<number>(0);
  const pageSize = 50;

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const offset = (page - 1) * pageSize; // Convert 1-indexed page to 0-indexed offset
        let url = `/messages?limit=${pageSize}&offset=${offset}`;
        
        // Use filter endpoints if filter is active
        if (filter?.type && filter?.value) {
          if (filter.type === 'priority') {
            url = `/messages/filter/priority/${filter.value}?limit=${pageSize}&offset=${offset}`;
          } else if (filter.type === 'label') {
            url = `/messages/filter/label/${encodeURIComponent(filter.value)}?limit=${pageSize}&offset=${offset}`;
          } else if (filter.type === 'status') {
            if (filter.value === 'classified') {
              url = `/messages/filter/classified?limit=${pageSize}&offset=${offset}`;
            } else if (filter.value === 'unclassified') {
              url = `/messages/filter/unclassified?limit=${pageSize}&offset=${offset}`;
            }
          }
        }
        
        const res = await fetch(url);
        
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const ct = res.headers.get('content-type') || '';
        
        let data: unknown[] = [];
        if (ct.includes('application/json')) {
          const text = await res.text();
          
          const parsed = JSON.parse(text);
            
          // Handle new paginated response format: {data: [...], total: N}
          if (parsed && typeof parsed === 'object' && 'data' in parsed && 'total' in parsed) {
            data = parsed.data;
            setTotalCount(parsed.total);
          } else if (Array.isArray(parsed)) {
            // Fallback for old format (direct array)
            data = parsed;
            setTotalCount(parsed.length);
          }
        } else {
          // backend not available or returned HTML (e.g. index.html) — handle gracefully
          await res.text();
          throw new Error('Unexpected response from server');
        }

        // map backend message dict to Email type
        const mapped: Email[] = [];
        for (let idx = 0; idx < (data as Record<string, unknown>[]).length; idx++) {
          const email = parseBackendMessage((data as Record<string, unknown>[])[idx], idx);
          if (email) {
            mapped.push(email);
          }
        }
        
        // Apply client-side search filter
        let filtered = mapped;
        if (searchQuery && searchQuery.trim().length > 0) {
          const query = searchQuery.toLowerCase();
          filtered = mapped.filter(email => 
            email.subject.toLowerCase().includes(query) ||
            email.summary.toLowerCase().includes(query) ||
            email.body.toLowerCase().includes(query) ||
            (email._raw?.from && String(email._raw.from).toLowerCase().includes(query)) ||
            (email._raw?.to && String(email._raw.to).toLowerCase().includes(query)) ||
            (email.classificationLabels && email.classificationLabels.some(l => l.toLowerCase().includes(query)))
          );
        }
        
        // Apply sort order
        if (sortOrder === 'oldest') {
          filtered = [...filtered].reverse();
        }
        
        setEmails(filtered);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        setEmails(exampleEmails);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [filter, searchQuery, sortOrder, page]);

  // Reset to page 1 when filter or search changes
  useEffect(() => {
    setPage(1);
  }, [filter, searchQuery]);

  const handleExpand = (id: string): void => {
    setExpandedId(expandedId === id ? null : id);
  };

  const handleDelete = (id: string): void => {
    setEmails(emails.filter(email => email.id !== id));
  };

  const handleReclassify = async (id: string) => {
    // Fetch the updated message and update it in the list
    console.log('[RECLASSIFY] Fetching updated message:', id);
    
    // Log BEFORE state
    const beforeEmail = emails.find(e => e.id === id);
    console.log('[RECLASSIFY] BEFORE:', {
      id: beforeEmail?.id,
      priority: beforeEmail?.priority,
      labels: beforeEmail?.classificationLabels,
      summary: beforeEmail?.summary
    });
    
    try {
      const res = await fetch(`/messages/${id}`);
      console.log('[RECLASSIFY] Fetch response status:', res.status);
      if (res.ok) {
        const messageData = await res.json();
        console.log('[RECLASSIFY] Received message data:', {
          id: messageData.id,
          priority: messageData.priority,
          labels: messageData.classification_labels,
          summary: messageData.summary
        });
        const updatedEmail = parseBackendMessage(messageData, 0);
        if (updatedEmail) {
          console.log('[RECLASSIFY] Parsed email:', {
            id: updatedEmail.id,
            priority: updatedEmail.priority,
            labels: updatedEmail.classificationLabels,
            summary: updatedEmail.summary
          });
          setEmails(prevEmails => {
            const updated = prevEmails.map(email => 
              email.id === id ? updatedEmail : email
            );
            console.log('[RECLASSIFY] Updated emails array, found match:', updated.some(e => e.id === id));
            
            // Log AFTER state
            const afterEmail = updated.find(e => e.id === id);
            console.log('[RECLASSIFY] AFTER:', {
              id: afterEmail?.id,
              priority: afterEmail?.priority,
              labels: afterEmail?.classificationLabels,
              summary: afterEmail?.summary
            });
            
            return updated;
          });
        } else {
          console.error('[RECLASSIFY] Failed to parse message data');
        }
      } else {
        console.error('[RECLASSIFY] Failed to fetch message:', res.status);
      }
    } catch (err) {
      console.error('[RECLASSIFY] Error refreshing message:', err);
    }
  };

  return (
    <Paper 
      elevation={0} 
      sx={{ 
        width: "100%", 
        flexGrow: 1,
        bgcolor: 'transparent',
        height: '100%',
        overflow: 'auto',
        p: { xs: 1, sm: 2, md: 3 },
        display: 'flex',
        flexDirection: 'column'
      }}
    >
      {/* Loading state with spinner */}
      {loading && (
        <Box 
          sx={{ 
            display: 'flex', 
            flexDirection: 'column',
            alignItems: 'center', 
            justifyContent: 'center',
            minHeight: '200px',
            gap: 2
          }}
        >
          <CircularProgress size={48} />
          <Typography variant="body1" color="text.secondary">
            Loading messages…
          </Typography>
        </Box>
      )}

      {/* Error state */}
      {error && !loading && (
        <Box sx={{ mb: 2, p: 2, bgcolor: 'error.light', borderRadius: 1 }}>
          <Typography variant="body2" color="error.dark">
            {error}
          </Typography>
        </Box>
      )}

      {/* Email list */}
      {!loading && (
        <List sx={{ 
        width: '100%',
        mx: 'auto',
        minWidth: '100%'
      }}>
        {emails.map((email) => (
          <EmailItem
            key={email.id}
            email={email}
            isExpanded={expandedId === email.id}
            onExpand={handleExpand}
            onDelete={handleDelete}
            onReclassify={handleReclassify}
            selectedModel={selectedModel}
          />
        ))}
      </List>
      )}
      
      {!loading && totalCount > pageSize && (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 2 }}>
          <Pagination 
            count={Math.ceil(totalCount / pageSize)} 
            page={page} 
            onChange={(_, value) => setPage(value)}
            color="primary"
            showFirstButton
            showLastButton
          />
        </Box>
      )}
    </Paper>
  );
};

export default EmailList;