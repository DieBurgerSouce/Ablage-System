import { cn } from "@/lib/utils"

interface QualityAmpelProps {
    score: number
    size?: "sm" | "md"
    showLabel?: boolean
    className?: string
}

export function QualityAmpel({
    score,
    size = "md",
    showLabel = true,
    className,
}: QualityAmpelProps) {
    // Score is 0-1
    let color = "bg-red-500"
    let ringColor = "ring-red-500/20"
    let textColor = "text-red-700 dark:text-red-400"
    let label = "Niedrig"

    if (score >= 0.80) {
        color = "bg-green-500"
        ringColor = "ring-green-500/20"
        textColor = "text-green-700 dark:text-green-400"
        label = "Hoch"
    } else if (score >= 0.50) {
        color = "bg-yellow-500"
        ringColor = "ring-yellow-500/20"
        textColor = "text-yellow-700 dark:text-yellow-400"
        label = "Mittel"
    }

    const dotSize = size === "sm" ? "h-2.5 w-2.5" : "h-3.5 w-3.5"
    const textSize = size === "sm" ? "text-xs" : "text-sm"

    return (
        <div
            className={cn("inline-flex items-center gap-1.5", className)}
            title={`Qualität: ${(score * 100).toFixed(0)}% - ${label}`}
        >
            <span
                className={cn(
                    "rounded-full ring-2",
                    color,
                    ringColor,
                    dotSize,
                )}
            />
            {showLabel && (
                <span className={cn("font-medium", textColor, textSize)}>
                    {label}
                </span>
            )}
        </div>
    )
}
