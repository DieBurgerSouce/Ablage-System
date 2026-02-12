/**
 * Tour Progress Dots Component
 *
 * Zeigt eine Reihe von Punkten für den aktuellen Tour-Fortschritt.
 * Aktiver Punkt ist hervorgehoben, abgeschlossene Punkte sind ausgefüllt.
 */

import { cn } from '@/lib/utils'

interface TourProgressProps {
  totalSteps: number
  currentStep: number
  className?: string
}

export function TourProgressDots({
  totalSteps,
  currentStep,
  className,
}: TourProgressProps) {
  return (
    <div
      className={cn('flex items-center justify-center gap-1.5', className)}
      role="progressbar"
      aria-valuenow={currentStep + 1}
      aria-valuemin={1}
      aria-valuemax={totalSteps}
      aria-label={`Schritt ${currentStep + 1} von ${totalSteps}`}
    >
      {Array.from({ length: totalSteps }, (_, i) => {
        const isActive = i === currentStep
        const isCompleted = i < currentStep

        return (
          <div
            key={i}
            className={cn(
              'rounded-full transition-all duration-300',
              isActive && 'w-6 h-2 bg-primary',
              isCompleted && 'w-2 h-2 bg-primary/60',
              !isActive && !isCompleted && 'w-2 h-2 bg-muted-foreground/30'
            )}
          />
        )
      })}
    </div>
  )
}
