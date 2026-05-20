import { cn } from "@/lib/utils"

interface ConfidenceIndicatorProps {
    score: number
    className?: string
}

export function ConfidenceIndicator({ score, className }: ConfidenceIndicatorProps) {
    // Score is 0-1
    let color = "bg-red-500"
    let label = "Niedrig"

    if (score >= 0.9) {
        color = "bg-green-500"
        label = "Hoch"
    } else if (score >= 0.7) {
        color = "bg-yellow-500"
        label = "Mittel"
    }

    return (
        <div className={cn("flex items-center gap-2", className)} title={`Konfidenz: ${(Number(score) * 100).toFixed(1)}%`}>
            <div className="h-2 w-full max-w-[100px] bg-secondary rounded-full overflow-hidden">
                <div
                    className={cn("h-full transition-all duration-500", color)}
                    style={{ width: `${Number(score) * 100}%` }}
                />
            </div>
            <span className="text-xs text-muted-foreground font-medium">{label}</span>
        </div>
    )
}
