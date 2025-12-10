import { cn } from '@/lib/utils';

interface ProgressRingProps {
    /** Progress value (0-100) */
    progress: number;
    /** Size of the ring */
    size?: 'sm' | 'md' | 'lg';
    /** Color variant */
    variant?: 'amber' | 'blue' | 'emerald';
    /** Whether to show percentage text */
    showText?: boolean;
    /** Additional CSS classes */
    className?: string;
}

const sizeConfig = {
    sm: { dimension: 20, strokeWidth: 2, fontSize: 'text-[6px]' },
    md: { dimension: 32, strokeWidth: 3, fontSize: 'text-[8px]' },
    lg: { dimension: 48, strokeWidth: 4, fontSize: 'text-xs' },
};

const colorConfig = {
    amber: { track: 'stroke-amber-200 dark:stroke-amber-900', progress: 'stroke-amber-500' },
    blue: { track: 'stroke-blue-200 dark:stroke-blue-900', progress: 'stroke-blue-500' },
    emerald: { track: 'stroke-emerald-200 dark:stroke-emerald-900', progress: 'stroke-emerald-500' },
};

export function ProgressRing({
    progress,
    size = 'md',
    variant = 'amber',
    showText = true,
    className,
}: ProgressRingProps) {
    const { dimension, strokeWidth, fontSize } = sizeConfig[size];
    const { track, progress: progressColor } = colorConfig[variant];

    const radius = (dimension - strokeWidth) / 2;
    const circumference = 2 * Math.PI * radius;
    const strokeDashoffset = circumference - (progress / 100) * circumference;

    return (
        <div className={cn('relative inline-flex items-center justify-center', className)}>
            <svg
                width={dimension}
                height={dimension}
                viewBox={`0 0 ${dimension} ${dimension}`}
                className="transform -rotate-90"
            >
                {/* Background track */}
                <circle
                    cx={dimension / 2}
                    cy={dimension / 2}
                    r={radius}
                    fill="none"
                    strokeWidth={strokeWidth}
                    className={track}
                />
                {/* Progress arc */}
                <circle
                    cx={dimension / 2}
                    cy={dimension / 2}
                    r={radius}
                    fill="none"
                    strokeWidth={strokeWidth}
                    strokeLinecap="round"
                    strokeDasharray={circumference}
                    strokeDashoffset={strokeDashoffset}
                    className={cn(progressColor, 'transition-all duration-300 ease-out')}
                />
            </svg>
            {showText && (
                <span className={cn(
                    'absolute font-medium',
                    fontSize,
                    variant === 'amber' && 'text-amber-600 dark:text-amber-400',
                    variant === 'blue' && 'text-blue-600 dark:text-blue-400',
                    variant === 'emerald' && 'text-emerald-600 dark:text-emerald-400',
                )}>
                    {Math.round(progress)}
                </span>
            )}
        </div>
    );
}
