import { Skeleton } from '../skeleton';

interface DetailViewSkeletonProps {
    variant?: 'pulse' | 'shimmer';
}

export function DetailViewSkeleton({ variant = 'shimmer' }: DetailViewSkeletonProps) {
    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="space-y-2">
                    <Skeleton variant={variant} className="h-7 w-[250px]" />
                    <Skeleton variant={variant} className="h-4 w-[180px]" />
                </div>
                <div className="flex gap-2">
                    <Skeleton variant={variant} className="h-9 w-[100px] rounded-md" />
                    <Skeleton variant={variant} className="h-9 w-9 rounded-md" />
                </div>
            </div>

            {/* Metadata fields */}
            <div className="grid grid-cols-2 gap-4">
                {Array.from({ length: 6 }).map((_, i) => (
                    <div key={i} className="space-y-1.5">
                        <Skeleton variant={variant} className="h-3.5 w-[80px]" />
                        <Skeleton variant={variant} className="h-5 w-[160px]" />
                    </div>
                ))}
            </div>

            {/* Content area */}
            <div className="rounded-lg border p-4 space-y-3">
                <Skeleton variant={variant} className="h-4 w-full" />
                <Skeleton variant={variant} className="h-4 w-5/6" />
                <Skeleton variant={variant} className="h-4 w-4/6" />
                <Skeleton variant={variant} className="h-4 w-full" />
                <Skeleton variant={variant} className="h-4 w-3/4" />
            </div>
        </div>
    );
}
