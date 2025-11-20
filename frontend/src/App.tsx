import React, { useState } from 'react';
import { ThemeProvider, CssBaseline, Container, AppBar, Toolbar, Typography, Box, Grid } from '@mui/material';
import { createTheme } from '@mui/material/styles';
import EmailList from './components/EmailList';
import EmailToolbar from './components/EmailToolbar';
import ChatInterface from './components/ChatInterface';

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
          height: 'calc(100vh - 64px)', // Subtract AppBar height
          width: '100vw',
          bgcolor: 'grey.100',
          display: 'flex',
          p: 0,
          overflow: 'hidden'
        }}
      >
        <Grid container sx={{ height: '100%', overflow: 'hidden' }}>
          {/* Email List Section - Left Side */}
          <Grid 
            item 
            xs={12} 
            md={7} 
            sx={{ 
              height: '100%',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
              borderRight: { md: 1 },
              borderColor: { md: 'divider' }
            }}
          >
            <Box sx={{ p: 2, flexGrow: 1, overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
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
          </Grid>

          {/* Chat Interface Section - Right Side */}
          <Grid 
            item 
            xs={12} 
            md={5} 
            sx={{ 
              height: '100%',
              overflow: 'hidden',
              bgcolor: 'background.default',
              display: { xs: 'none', md: 'block' } // Hide on mobile, show on tablet and up
            }}
          >
            <ChatInterface />
          </Grid>
        </Grid>
      </Container>
    </ThemeProvider>
  );
};

export default App;
