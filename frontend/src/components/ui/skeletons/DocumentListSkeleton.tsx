import { Skeleton } from '../skeleton';

interface DocumentListSkeletonProps {
    rows?: number;
    variant?: 'pulse' | 'shimmer';
}

export function DocumentListSkeleton({ rows = 5, variant = 'shimmer' }: DocumentListSkeletonProps) {
    return (
        <div className="w-full space-y-1">
            {/* Header row */}
            <div className="flex items-center gap-4 px-4 py-3 border-b">
                <Skeleton variant={variant} className="h-4 w-4" />
                <Skeleton variant={variant} className="h-4 w-[180px]" />
                <Skeleton variant={variant} className="h-4 w-[100px]" />
                <Skeleton variant={variant} className="h-4 w-[80px]" />
                <Skeleton variant={variant} className="h-4 w-[60px]" />
            </div>
            {/* Data rows */}
            {Array.from({ length: rows }).map((_, i) => (
                <div key={i} className="flex items-center gap-4 px-4 py-3 border-b last:border-b-0">
                    <Skeleton variant={variant} className="h-4 w-4 rounded" />
                    <Skeleton variant={variant} className="h-4 w-[140px] flex-shrink-0" />
                    <Skeleton variant={variant} className="h-5 w-[80px] rounded-full" />
                    <Skeleton variant={variant} className="h-4 w-[70px]" />
                    <Skeleton variant={variant} className="h-5 w-[60px] rounded-full" />
                </div>
            ))}
        </div>
    );
}
