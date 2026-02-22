/**
 * Product Tour Feature Exports
 *
 * Interaktive Produkttour für geführtes Onboarding
 */

// Components
export { ProductTour } from './components/ProductTour'
export { TourLauncher } from './components/TourLauncher'
export { TourSpotlight } from './components/TourSpotlight'
export { TourTooltip } from './components/TourTooltip'
export { TourProgressDots } from './components/TourProgress'
export { TourProvider, useTourContext } from './components/TourProvider'

// Hooks
export { useTour } from './hooks/use-tour'
export { useUserMode } from './hooks/use-user-mode'
export type { UserMode } from './hooks/use-user-mode'
export { emitChecklistComplete, useChecklistListener } from './hooks/use-checklist-events'

// Getting Started / Progressive Disclosure
export { GettingStartedChecklist, GettingStartedMini, useGettingStartedChecklist } from './components/GettingStartedChecklist'
export { NewBadge, NewDot, useFeatureDiscovery, NEW_FEATURES } from './components/NewBadge'
export { UserModeToggle } from './components/UserModeToggle'
export { HelpTooltip } from './components/HelpTooltip'

// Tour Definitions (modular)
export {
  documentUploadTour,
  ocrResultsTour,
  searchTour,
  invoiceWorkflowTour,
} from './tours'

// Getting Started Config
export {
  GETTING_STARTED_ITEMS,
  markGettingStartedComplete,
  isGettingStartedComplete,
  getGettingStartedProgress,
} from './getting-started-config'
export type { GettingStartedItem } from './getting-started-config'

// Help Tooltip Definitions
export { HELP_TOOLTIPS } from './help-tooltips'
export type { HelpTooltipKey } from './help-tooltips'

// Types & Data
export * from './types'
