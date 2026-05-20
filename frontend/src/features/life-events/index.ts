/**
 * Life Events Feature - Lebenslagen-Assistent
 *
 * Proaktiver Begleiter für wichtige Lebensereignisse.
 */

// Components
export { LifeEventsPage } from './components/LifeEventsPage';
export { LifeEventDetail } from './components/LifeEventDetail';
export { LifeEventCard, EVENT_TYPE_CONFIG } from './components/LifeEventCard';

// API & Hooks
export {
  useLifeEventTypes,
  useLifeEvents,
  useLifeEvent,
  useCreateLifeEvent,
  useToggleChecklistItem,
  useCompleteLifeEvent,
  useActiveEventsCount,
  lifeEventQueryKeys,
} from './api/life-events-api';

// Types
export type {
  LifeEventType,
  LifeEventStatus,
  LifeEvent,
  ChecklistItem,
  FinancialImpact,
  Recommendation,
} from './api/life-events-api';
