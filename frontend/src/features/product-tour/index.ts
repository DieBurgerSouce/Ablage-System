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

// Getting Started / Progressive Disclosure
export { GettingStartedChecklist, GettingStartedMini, useGettingStartedChecklist } from './components/GettingStartedChecklist'
export { NewBadge, NewDot, useFeatureDiscovery, NEW_FEATURES } from './components/NewBadge'

// Types & Data
export * from './types'
