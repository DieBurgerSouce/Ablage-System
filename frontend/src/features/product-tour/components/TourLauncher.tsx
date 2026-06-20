/**
 * Tour Launcher Component
 *
 * Button/Widget zum Starten von Touren.
 * Gruppiert Touren nach Kategorie, zeigt Abzeichen und geschätzte Dauer.
 */

import { useState } from 'react'
import {
  HelpCircle,
  Award,
  Play,
  Check,
  ChevronRight,
  Clock,
  Sparkles,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useTourContext } from './TourProvider'
import {
  TOURS,
  getToursByCategory,
  CATEGORY_LABELS,
  type TourCategory,
} from '../types'

interface TourLauncherProps {
  className?: string
  variant?: 'button' | 'icon' | 'fab'
}

export function TourLauncher({ className, variant = 'icon' }: TourLauncherProps) {
  const [isOpen, setIsOpen] = useState(false)
  const {
    startTour,
    badges,
    isTourCompleted,
    resetTour,
  } = useTourContext()

  const completedCount = TOURS.filter(t => isTourCompleted(t.id)).length
  const progressPercent = Math.round((completedCount / TOURS.length) * 100)
  const toursByCategory = getToursByCategory()

  const handleStartTour = (tourId: string) => {
    setIsOpen(false)
    setTimeout(() => startTour(tourId), 200)
  }

  const handleRestartTour = (tourId: string) => {
    resetTour(tourId)
    handleStartTour(tourId)
  }

  const triggerButton = (() => {
    switch (variant) {
      case 'icon':
        return (
          <Button
            variant="ghost"
            size="icon"
            className={className}
            onClick={() => setIsOpen(true)}
            aria-label="Touren und Hilfe öffnen"
          >
            <HelpCircle className="h-5 w-5" />
          </Button>
        )
      case 'fab':
        return (
          <Button
            size="lg"
            className={cn(
              'fixed bottom-6 right-6 rounded-full shadow-lg',
              'h-14 w-14 p-0',
              className
            )}
            onClick={() => setIsOpen(true)}
            aria-label="Touren und Hilfe öffnen"
          >
            <Sparkles className="h-6 w-6" />
          </Button>
        )
      default:
        return (
          <Button
            variant="outline"
            className={className}
            onClick={() => setIsOpen(true)}
          >
            <HelpCircle className="h-4 w-4 mr-2" />
            Hilfe & Touren
            {badges.length > 0 && (
              <Badge variant="secondary" className="ml-2">
                {badges.length}
              </Badge>
            )}
          </Button>
        )
    }
  })()

  return (
    <>
      {triggerButton}

      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogContent className="max-w-lg p-0">
          <DialogHeader className="p-6 pb-0">
            <DialogTitle>Hilfe & Produkttouren</DialogTitle>
            <DialogDescription>
              Lernen Sie Ablage-System interaktiv kennen
            </DialogDescription>
          </DialogHeader>

          {/* Fortschritt */}
          <div className="px-6 pb-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium">Fortschritt</span>
              <span className="text-sm text-muted-foreground">
                {completedCount} von {TOURS.length} abgeschlossen
              </span>
            </div>
            <Progress value={progressPercent} className="h-2" />
          </div>

          {/* Touren nach Kategorie */}
          <ScrollArea className="max-h-[360px] px-6">
            {(Object.entries(toursByCategory) as [TourCategory, typeof TOURS][]).map(
              ([category, tours]) => {
                if (tours.length === 0) return null
                return (
                  <div key={category} className="mb-4">
                    <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                      {CATEGORY_LABELS[category]}
                    </h4>
                    <div className="space-y-1">
                      {tours.map((tour) => {
                        const isCompleted = isTourCompleted(tour.id)
                        return (
                          <div
                            key={tour.id}
                            className={cn(
                              'flex items-center justify-between p-3 rounded-lg',
                              'hover:bg-muted/50 transition-colors',
                              isCompleted && 'opacity-60'
                            )}
                          >
                            <div className="flex items-center gap-3 min-w-0">
                              <div
                                className={cn(
                                  'flex items-center justify-center w-8 h-8 rounded-full flex-shrink-0',
                                  isCompleted
                                    ? 'bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400'
                                    : 'bg-primary/10 text-primary'
                                )}
                              >
                                {isCompleted ? (
                                  <Check className="h-4 w-4" />
                                ) : (
                                  <Play className="h-4 w-4" />
                                )}
                              </div>
                              <div className="min-w-0">
                                <p className="font-medium text-sm truncate">{tour.name}</p>
                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                  <span>{tour.steps.length} Schritte</span>
                                  <span className="flex items-center gap-0.5">
                                    <Clock className="h-3 w-3" />
                                    ~{tour.estimatedMinutes} Min.
                                  </span>
                                  {isCompleted && <span>Abgeschlossen</span>}
                                </div>
                              </div>
                            </div>
                            <div className="flex-shrink-0 ml-2">
                              {isCompleted ? (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleRestartTour(tour.id)}
                                >
                                  Wiederholen
                                </Button>
                              ) : (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleStartTour(tour.id)}
                                >
                                  Starten
                                  <ChevronRight className="h-4 w-4 ml-1" />
                                </Button>
                              )}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )
              }
            )}

            {/* Abzeichen */}
            {badges.length > 0 && (
              <div className="mb-4 pt-2 border-t">
                <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2 flex items-center gap-1">
                  <Award className="h-3 w-3" />
                  Verdiente Abzeichen
                </h4>
                <div className="flex flex-wrap gap-2">
                  {badges.map((badge) => (
                    <Badge
                      key={badge.id}
                      variant="secondary"
                      className="py-1.5 px-3"
                    >
                      <Award className="h-3 w-3 mr-1 text-yellow-500" />
                      {badge.name}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </ScrollArea>

          {/* Footer */}
          <div className="p-4 border-t bg-muted/30">
            <p className="text-xs text-muted-foreground text-center">
              Tastenkürzel: Pfeil rechts/links zum Navigieren, ESC zum Beenden
            </p>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
