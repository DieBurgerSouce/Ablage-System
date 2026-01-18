/**
 * AI Decisions Feature - Barrel Export
 */

// Types
export * from './types/ai-types';

// API
export * from './api/ai-api';

// Hooks
export * from './hooks/useAIDecisions';

// Components
export { AIDecisionDashboard } from './components/AIDecisionDashboard';
export { AIDecisionList } from './components/AIDecisionList';
export { AIThresholdSettings } from './components/AIThresholdSettings';
export { AILearningStats } from './components/AILearningStats';
export { DriftStatusCard } from './components/DriftStatusCard';
export { ExperimentsPanel } from './components/ExperimentsPanel';

// XAI Components (re-export from ui for convenience)
export {
  ExplainabilityPanel,
  WarumButton,
  type ExplainabilityPanelProps,
  type WarumButtonProps,
  type DecisionExplanation,
  type ExplanationFactor,
  type AlternativeOption,
  type ImpactBreakdown,
  type ConfidenceLevel as XAIConfidenceLevel,
  type FactorCategory,
} from '@/components/ui/ExplainabilityPanel';
