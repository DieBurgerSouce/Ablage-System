/**
 * GraphFilters Tests
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { GraphFilters } from '../components/GraphFilters';
import type { GraphFilterState } from '../types/document-graph-types';

const defaultFilters: GraphFilterState = {
  entityId: null,
  entityType: 'all',
  timeRange: '90d',
  documentTypes: [],
  viewMode: 'graph',
};

describe('GraphFilters', () => {
  it('rendert alle Filter-Elemente', () => {
    render(
      <GraphFilters filters={defaultFilters} onFiltersChange={vi.fn()} />
    );

    expect(screen.getByText('Graph')).toBeInTheDocument();
    expect(screen.getByText('Timeline')).toBeInTheDocument();
  });

  it('wechselt View-Mode bei Klick auf Timeline', () => {
    const onFiltersChange = vi.fn();
    render(
      <GraphFilters filters={defaultFilters} onFiltersChange={onFiltersChange} />
    );

    fireEvent.click(screen.getByText('Timeline'));
    expect(onFiltersChange).toHaveBeenCalledWith({ viewMode: 'timeline' });
  });

  it('wechselt View-Mode bei Klick auf Graph', () => {
    const onFiltersChange = vi.fn();
    render(
      <GraphFilters
        filters={{ ...defaultFilters, viewMode: 'timeline' }}
        onFiltersChange={onFiltersChange}
      />
    );

    fireEvent.click(screen.getByText('Graph'));
    expect(onFiltersChange).toHaveBeenCalledWith({ viewMode: 'graph' });
  });

  it('zeigt Graph-Button als aktiv wenn viewMode=graph', () => {
    render(
      <GraphFilters filters={defaultFilters} onFiltersChange={vi.fn()} />
    );

    const graphButton = screen.getByText('Graph').closest('button');
    // Default variant button should not have 'outline' class
    expect(graphButton?.className).not.toContain('ghost');
  });
});
