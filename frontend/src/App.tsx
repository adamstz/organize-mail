import React, { useState } from 'react';
import { ThemeProvider, CssBaseline, Container, AppBar, Toolbar, Typography, Box } from '@mui/material';
import { createTheme } from '@mui/material/styles';
import EmailList from './components/EmailList';
import EmailToolbar from './components/EmailToolbar';

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1976d2',
    },
  },
});

const App: React.FC = () => {
  const [filter, setFilter] = useState<{ type: 'priority' | 'label' | 'status' | null; value: string | null }>({
    type: null,
    value: null,
  });
  const [classificationStatus, setClassificationStatus] = useState<'all' | 'classified' | 'unclassified'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortOrder, setSortOrder] = useState<'recent' | 'oldest'>('recent');
  const [selectedModel, setSelectedModel] = useState<string>('gemma:2b');

  const handleStatusChange = (_event: React.MouseEvent<HTMLElement>, newStatus: 'all' | 'classified' | 'unclassified' | null) => {
    if (newStatus !== null) {
      setClassificationStatus(newStatus);
      if (newStatus === 'all') {
        setFilter({ type: null, value: null });
      } else {
        setFilter({ type: 'status', value: newStatus });
      }
    }
  };

  const clearFilter = () => {
    setFilter({ type: null, value: null });
    setClassificationStatus('all');
  };

  const handleLabelFilter = (label: string) => {
    // Toggle label filter: if already selected, clear it; otherwise set it
    if (filter.type === 'label' && filter.value === label) {
      setFilter({ type: null, value: null });
    } else {
      setFilter({ type: 'label', value: label });
    }
  };

  const handlePriorityFilter = (priority: string) => {
    // Toggle priority filter: if already selected, clear it; otherwise set it
    if (filter.type === 'priority' && filter.value === priority) {
      setFilter({ type: null, value: null });
    } else {
      setFilter({ type: 'priority', value: priority });
    }
  };

  const toggleSortOrder = () => {
    setSortOrder(prev => prev === 'recent' ? 'oldest' : 'recent');
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AppBar position="static">
        <Toolbar>
          <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
            Organize Mail
          </Typography>
        </Toolbar>
      </AppBar>
      <Container 
        maxWidth={false} 
        disableGutters 
        sx={{ 
          height: '100vh',
          width: '100vw',
          bgcolor: 'grey.100',
          display: 'flex',
          flexDirection: 'column',
          p: 0
        }}
      >
        <Box sx={{ p: 2, flexGrow: 1, overflow: 'auto' }}>
          <EmailToolbar
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            sortOrder={sortOrder}
            onSortToggle={toggleSortOrder}
            classificationStatus={classificationStatus}
            onStatusChange={handleStatusChange}
            filter={filter}
            onClearFilter={clearFilter}
            onLabelFilter={handleLabelFilter}
            onPriorityFilter={handlePriorityFilter}
            selectedModel={selectedModel}
            onModelChange={setSelectedModel}
          />

          <EmailList filter={filter} searchQuery={searchQuery} sortOrder={sortOrder} />
        </Box>
      </Container>
    </ThemeProvider>
  );
};

export default App;