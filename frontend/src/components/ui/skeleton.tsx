import { cn } from "@/lib/utils"

interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
    variant?: 'pulse' | 'shimmer';
}

function Skeleton({
    className,
    variant = 'pulse',
    ...props
}: SkeletonProps) {
    return (
        <div
            className={cn(
                "rounded-md bg-muted",
                variant === 'shimmer' ? 'skeleton-shimmer' : 'animate-pulse',
                className
            )}
            {...props}
        />
    )
}

export { Skeleton }
export type { SkeletonProps }
