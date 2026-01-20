/**
 * Facet Filter Components
 *
 * Provides faceted filtering UI for data tables and lists.
 * Integrates with TanStack Table's getFacetedUniqueValues().
 */

export { FacetItem, type FacetItemProps } from './FacetItem';
export { FacetGroup, type FacetGroupProps, type FacetValue } from './FacetGroup';
export {
  FacetFilter,
  FacetFilterToggle,
  useFacetValues,
  type FacetConfig,
  type FacetFilterProps,
} from './FacetFilter';
