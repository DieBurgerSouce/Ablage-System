/**
 * Help System - Public API
 */

// Types
export * from './types';

// Hooks
export * from './hooks/useHelp';

// Components
export { HelpButton } from './components/HelpButton';
export { HelpPanel } from './components/HelpPanel';
export { OnboardingTour } from './components/OnboardingTour';
export { ContextualTooltip, InlineTooltipTrigger } from './components/ContextualTooltip';
export { FeatureHint, QuickHint } from './components/FeatureHint';
export { VideoPlayer } from './components/VideoPlayer';
export { HelpSearch, CompactHelpSearch } from './components/HelpSearch';
export { OnboardingProgress, MinimalOnboardingProgress } from './components/OnboardingProgress';

// Provider
export { HelpProvider, useHelpContext } from './providers/HelpProvider';
