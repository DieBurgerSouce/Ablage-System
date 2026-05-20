/**
 * Saved Filters Feature Export
 *
 * Phase 4.5: Frontend UX Enhancement - Server-side Filter Persistence with Sharing
 *
 * Dieses Feature ersetzt die LocalStorage-basierte Implementierung durch
 * eine Server-seitige Loesung mit Multi-Tenant-Isolation und Sharing-Option.
 *
 * Usage:
 *   import { useSavedFilters, SavedFilterDropdown, SaveFilterDialog } from '@/features/saved-filters'
 *
 *   function MyComponent() {
 *     const {
 *       filters,
 *       defaultFilter,
 *       createFilter,
 *       deleteFilter,
 *       recordUsage,
 *     } = useSavedFilters({ feature: 'documents' })
 *
 *     return (
 *       <SavedFilterDropdown
 *         filters={filters}
 *         onSelectFilter={(f) => recordUsage(f.id)}
 *         onCreateFilter={() => setShowDialog(true)}
 *         // ...
 *       />
 *     )
 *   }
 */

// API
export {
  getSavedFilters,
  getSavedFilter,
  createSavedFilter,
  updateSavedFilter,
  deleteSavedFilter,
  recordFilterUsage,
  duplicateSavedFilter,
  setDefaultFilter,
  clearDefaultFilter,
  getAvailableFeatures,
  type SavedFilter,
  type SavedFilterListResponse,
  type CreateSavedFilterRequest,
  type UpdateSavedFilterRequest,
  type DuplicateFilterRequest,
} from "./api/saved-filters-api"

// Hooks
export {
  useSavedFilters,
  type UseSavedFiltersOptions,
  type UseSavedFiltersReturn,
} from "./hooks/use-saved-filters"

// Components
export {
  SaveFilterDialog,
  SavedFilterDropdown,
  SharedFiltersPanel,
  type SaveFilterDialogProps,
  type SavedFilterDropdownProps,
  type SharedFiltersPanelProps,
} from "./components"
