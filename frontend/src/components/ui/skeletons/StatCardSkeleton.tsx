import { Skeleton } from '../skeleton';

interface StatCardSkeletonProps {
    count?: number;
    variant?: 'pulse' | 'shimmer';
}

export function StatCardSkeleton({ count = 4, variant = 'shimmer' }: StatCardSkeletonProps) {
    return (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {Array.from({ length: count }).map((_, i) => (
                <div key={i} className="rounded-lg border bg-card p-4 space-y-3">
                    <div className="flex items-center justify-between">
                        <Skeleton variant={variant} className="h-4 w-[80px]" />
                        <Skeleton variant={variant} className="h-8 w-8 rounded-full" />
                    </div>
                    <Skeleton variant={variant} className="h-8 w-[100px]" />
                    <Skeleton variant={variant} className="h-3 w-[60px]" />
                </div>
            ))}
        </div>
    );
}
