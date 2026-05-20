/**
 * Loading Skeleton Components
 *
 * Progressive loading states for better UX.
 */

export { SkeletonTable, type SkeletonTableProps } from './SkeletonTable';
export {
  SkeletonCard,
  SkeletonCardGrid,
  type SkeletonCardProps,
  type SkeletonCardGridProps,
  type SkeletonCardVariant,
} from './SkeletonCard';
export {
  SkeletonList,
  SkeletonDocumentList,
  SkeletonForm,
  type SkeletonListProps,
  type SkeletonListVariant,
  type SkeletonDocumentListProps,
  type SkeletonFormProps,
} from './SkeletonList';

export { DashboardSkeleton, type DashboardSkeletonProps } from './DashboardSkeleton';
export { ChatSkeleton, type ChatSkeletonProps } from './ChatSkeleton';

// Re-export the base skeleton
export { Skeleton } from '@/components/ui/skeleton';
