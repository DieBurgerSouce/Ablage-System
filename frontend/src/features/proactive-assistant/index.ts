// Proactive Assistant Feature Module - Barrel Export

// Types
export * from './types/proactive-assistant-types';

// API
export * from './api/proactive-assistant-api';

// Hooks
export * from './hooks/use-proactive-assistant-queries';

// Components
export * from './components';

// Explizit: HintList-Komponente (Typ HintList weiterhin direkt aus types importierbar)
export { HintList } from './components/HintList';

// Pages
export { ProactiveAssistantPage } from './pages/ProactiveAssistantPage';
export { HintRulesPage } from './pages/HintRulesPage';
