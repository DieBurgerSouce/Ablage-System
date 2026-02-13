/**
 * Smart Inbox Feature - Barrel Export
 *
 * Exportiert alle öffentlichen APIs des Smart Inbox Moduls.
 */

export * from './types';
export * from './api';
export * from './hooks/use-smart-inbox-queries';

// Components
export { InboxStatsBar } from './components/InboxStatsBar';
export { InboxFilters } from './components/InboxFilters';
export { InboxItemCard } from './components/InboxItemCard';
export { InboxInsightsPanel } from './components/InboxInsightsPanel';
export { InboxEmptyState } from './components/InboxEmptyState';

// Pages
export { SmartInboxPage } from './pages/SmartInboxPage';
