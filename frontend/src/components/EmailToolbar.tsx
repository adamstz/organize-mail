import React, { useEffect, useState } from 'react';
import { Box, ToggleButton, ToggleButtonGroup, TextField, InputAdornment, Chip, Stack, Typography, Button, Select, MenuItem, FormControl, InputLabel } from '@mui/material';
import { Search as SearchIcon, ArrowUpward as ArrowUpIcon, ArrowDownward as ArrowDownIcon, ExpandMore as ExpandMoreIcon, ExpandLess as ExpandLessIcon } from '@mui/icons-material';

interface EmailToolbarProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  sortOrder: 'recent' | 'oldest';
  onSortToggle: () => void;
  filters: {
    priority: string | null;
    labels: string[];
    status: 'all' | 'classified' | 'unclassified';
  };
  onStatusChange: (_event: React.MouseEvent<HTMLElement>, newStatus: 'all' | 'classified' | 'unclassified' | null) => void;
  onClearAllFilters: () => void;
  onLabelFilter: (label: string) => void;
  onPriorityFilter: (priority: string) => void;
  selectedModel: string;
  onModelChange: (model: string) => void;
}

interface Label {
  name: string;
  count: number;
}

const EmailToolbar: React.FC<EmailToolbarProps> = ({
  searchQuery,
  onSearchChange,
  sortOrder,
  onSortToggle,
  filters,
  onStatusChange,
  onClearAllFilters,
  onLabelFilter,
  onPriorityFilter,
  selectedModel,
  onModelChange,
}) => {
  const [labels, setLabels] = useState<Label[]>([]);
  const [loading, setLoading] = useState(false);
  const [showAllLabels, setShowAllLabels] = useState(false);
  const [models, setModels] = useState<Array<{name: string; size: number}>>([]);
  const MAX_VISIBLE_LABELS = 6; // Number of labels to show before collapsing

  useEffect(() => {
    async function fetchLabels() {
      setLoading(true);
      try {
        const res = await fetch('/labels');
        if (res.ok) {
          const data = await res.json();
          setLabels(data.labels || []);
        } else {
          setLabels([]);
        }
      } catch (err) {
        // Failed to fetch labels - backend may not be running
        setLabels([]);
      } finally {
        setLoading(false);
      }
    }
    
    async function fetchModels() {
      try {
        const res = await fetch('/models');
        if (res.ok) {
          const data = await res.json();
          setModels(data.models || []);
        }
      } catch (err) {
        console.error('Failed to fetch models:', err);
      }
    }
    
    fetchLabels();
    fetchModels();
  }, []);

  return (
    <Box sx={{ mb: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap', mb: 2 }}>
        <FormControl size="small" sx={{ minWidth: 150 }}>
          <InputLabel>LLM Model</InputLabel>
          <Select
            value={selectedModel}
            label="LLM Model"
            onChange={(e) => onModelChange(e.target.value)}
          >
            {models.map((model) => (
              <MenuItem key={model.name} value={model.name}>
                {model.name}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        
        <TextField
          size="small"
          placeholder="Search emails..."
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          sx={{ minWidth: 250 }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon />
              </InputAdornment>
            ),
          }}
        />
        
        <Chip
          icon={sortOrder === 'recent' ? <ArrowDownIcon /> : <ArrowUpIcon />}
          label={sortOrder === 'recent' ? 'Newest First' : 'Oldest First'}
          onClick={onSortToggle}
          variant="outlined"
          sx={{ 
            cursor: 'pointer',
            '&:hover': { bgcolor: 'action.hover' }
          }}
        />
        
        <ToggleButtonGroup
          value={filters.status}
          exclusive
          onChange={onStatusChange}
          size="small"
          aria-label="classification status filter"
        >
          <ToggleButton value="all" aria-label="all messages">
            All
          </ToggleButton>
          <ToggleButton value="classified" aria-label="classified messages">
            Classified
          </ToggleButton>
          <ToggleButton value="unclassified" aria-label="unclassified messages">
            Unclassified
          </ToggleButton>
        </ToggleButtonGroup>

        {/* Priority filter chips */}
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Chip
            label="🔴 High"
            onClick={() => onPriorityFilter('high')}
            variant={filters.priority === 'high' ? 'filled' : 'outlined'}
            color={filters.priority === 'high' ? 'error' : 'default'}
            size="small"
            sx={{ cursor: 'pointer', '&:hover': { bgcolor: 'action.hover' } }}
          />
          <Chip
            label="🟡 Normal"
            onClick={() => onPriorityFilter('normal')}
            variant={filters.priority === 'normal' ? 'filled' : 'outlined'}
            color={filters.priority === 'normal' ? 'primary' : 'default'}
            size="small"
            sx={{ cursor: 'pointer', '&:hover': { bgcolor: 'action.hover' } }}
          />
          <Chip
            label="🟢 Low"
            onClick={() => onPriorityFilter('low')}
            variant={filters.priority === 'low' ? 'filled' : 'outlined'}
            color={filters.priority === 'low' ? 'success' : 'default'}
            size="small"
            sx={{ cursor: 'pointer', '&:hover': { bgcolor: 'action.hover' } }}
          />
        </Box>

        {filters.labels.length > 0 && (
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            {filters.labels.map((label) => (
              <Chip
                key={label}
                label={label}
                onDelete={() => onLabelFilter(label)}
                color="primary"
                size="small"
              />
            ))}
            {filters.labels.length > 1 && (
              <Chip
                label="Clear labels"
                onClick={() => filters.labels.forEach(l => onLabelFilter(l))}
                variant="outlined"
                size="small"
              />
            )}
          </Box>
        )}
        {filters.priority && (
          <Chip
            label={`Priority: ${filters.priority}`}
            onDelete={() => onPriorityFilter(filters.priority!)}
            color="secondary"
            variant="outlined"
            size="small"
          />
        )}
        {(filters.labels.length > 0 || filters.priority || filters.status !== 'all') && (
          <Chip
            label="Clear all filters"
            onClick={onClearAllFilters}
            variant="outlined"
            color="default"
            size="small"
          />
        )}
      </Box>

      {/* Label filter chips - always show section if we've loaded */}
      {!loading && (
        <Box>
          <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: 'block' }}>
            Filter by label: {labels.length === 0 && '(no labels found)'}
          </Typography>
          {labels.length > 0 && (
            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', gap: 1, alignItems: 'center' }}>
              {/* Sort labels by count (most popular first) and show only top N if not expanded */}
              {labels
                .sort((a, b) => b.count - a.count)
                .slice(0, showAllLabels ? labels.length : MAX_VISIBLE_LABELS)
                .map((label) => {
                  const isSelected = filters.labels.includes(label.name);
                  return (
                    <Chip
                      key={label.name}
                      label={`${label.name} (${label.count})`}
                      onClick={() => onLabelFilter(label.name)}
                      variant={isSelected ? 'filled' : 'outlined'}
                      color={isSelected ? 'primary' : 'default'}
                      size="small"
                      sx={{ 
                        cursor: 'pointer',
                        '&:hover': { bgcolor: 'action.hover' }
                      }}
                    />
                  );
                })}
              
              {/* Show expand/collapse button if there are more labels than MAX_VISIBLE_LABELS */}
              {labels.length > MAX_VISIBLE_LABELS && (
                <Button
                  size="small"
                  onClick={() => setShowAllLabels(!showAllLabels)}
                  startIcon={showAllLabels ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                  sx={{ 
                    textTransform: 'none',
                    minWidth: 'auto',
                    px: 1
                  }}
                >
                  {showAllLabels ? 'Show less' : `Show ${labels.length - MAX_VISIBLE_LABELS} more`}
                </Button>
              )}
            </Stack>
          )}
        </Box>
      )}
      {loading && (
        <Typography variant="caption" color="text.secondary">
          Loading labels...
        </Typography>
      )}
    </Box>
  );
};

export default EmailToolbar;
