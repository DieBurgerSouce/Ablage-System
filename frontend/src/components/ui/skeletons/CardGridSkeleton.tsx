import { Skeleton } from '../skeleton';

interface CardGridSkeletonProps {
    count?: number;
    variant?: 'pulse' | 'shimmer';
}

export function CardGridSkeleton({ count = 6, variant = 'shimmer' }: CardGridSkeletonProps) {
    return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: count }).map((_, i) => (
                <div key={i} className="rounded-lg border bg-card p-4 space-y-3">
                    <Skeleton variant={variant} className="h-32 w-full rounded-md" />
                    <Skeleton variant={variant} className="h-5 w-3/4" />
                    <Skeleton variant={variant} className="h-4 w-full" />
                    <Skeleton variant={variant} className="h-4 w-2/3" />
                    <div className="flex justify-between items-center pt-2">
                        <Skeleton variant={variant} className="h-4 w-[60px]" />
                        <Skeleton variant={variant} className="h-8 w-[80px] rounded-md" />
                    </div>
                </div>
            ))}
        </div>
    );
}
