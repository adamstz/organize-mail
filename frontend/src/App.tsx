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
  const [selectedModel, setSelectedModel] = useState<string>('gemma:2b');

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
            filters={filters}
            onStatusChange={handleStatusChange}
            onClearAllFilters={clearAllFilters}
            onLabelFilter={handleLabelFilter}
            onPriorityFilter={handlePriorityFilter}
            selectedModel={selectedModel}
            onModelChange={setSelectedModel}
          />

          <EmailList filters={filters} searchQuery={searchQuery} sortOrder={sortOrder} selectedModel={selectedModel} />
        </Box>
      </Container>
    </ThemeProvider>
  );
};

export default App;