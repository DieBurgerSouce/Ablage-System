/**
 * Tour Launcher Component
 *
 * Vision 2026+ Feature: Interaktive Produkttour
 * Button/Widget zum Starten von Touren + Badge-Anzeige
 */

import * as React from 'react'
import { useState } from 'react'
import {
  HelpCircle,
  Award,
  Play,
  Check,
  ChevronRight,
  Sparkles,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useTour } from '../hooks/use-tour'
import { Tour, TOURS, TourBadge } from '../types'

interface TourLauncherProps {
  className?: string
  variant?: 'button' | 'icon' | 'fab'
}

export function TourLauncher({ className, variant = 'button' }: TourLauncherProps) {
  const [isOpen, setIsOpen] = useState(false)
  const {
    startTour,
    badges,
    isTourCompleted,
    getAvailableTours,
    resetTour,
  } = useTour()

  const availableTours = getAvailableTours()
  const completedCount = TOURS.filter(t => isTourCompleted(t.id)).length
  const progressPercent = Math.round((completedCount / TOURS.length) * 100)

  const handleStartTour = (tourId: string) => {
    setIsOpen(false)
    // Small delay to close popover smoothly
    setTimeout(() => startTour(tourId), 150)
  }

  const handleRestartTour = (tourId: string) => {
    resetTour(tourId)
    handleStartTour(tourId)
  }

  const TriggerButton = () => {
    switch (variant) {
      case 'icon':
        return (
          <Button variant="ghost" size="icon" className={className}>
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
          >
            <Sparkles className="h-6 w-6" />
          </Button>
        )
      default:
        return (
          <Button variant="outline" className={className}>
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
  }

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <TriggerButton />
      </PopoverTrigger>
      <PopoverContent className="w-96 p-0" align="end">
        {/* Header */}
        <div className="p-4 border-b bg-muted/30">
          <h3 className="font-semibold">Hilfe & Produkttouren</h3>
          <p className="text-sm text-muted-foreground">
            Lernen Sie Ablage-System interaktiv kennen
          </p>
        </div>

        {/* Progress */}
        <div className="p-4 border-b">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium">Fortschritt</span>
            <span className="text-sm text-muted-foreground">
              {completedCount} von {TOURS.length} abgeschlossen
            </span>
          </div>
          <Progress value={progressPercent} className="h-2" />
        </div>

        {/* Tours List */}
        <ScrollArea className="h-[280px]">
          <div className="p-2">
            <h4 className="text-xs font-medium text-muted-foreground px-2 py-1">
              Verfügbare Touren
            </h4>
            {TOURS.map((tour) => {
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
                  <div className="flex items-center gap-3">
                    <div
                      className={cn(
                        'flex items-center justify-center w-8 h-8 rounded-full',
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
                    <div>
                      <p className="font-medium text-sm">{tour.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {tour.steps.length} Schritte
                        {isCompleted && ' • Abgeschlossen'}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    {isCompleted ? (
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleRestartTour(tour.id)}
                            >
                              Wiederholen
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Tour neu starten</TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
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

          {/* Badges Section */}
          {badges.length > 0 && (
            <div className="p-2 border-t">
              <h4 className="text-xs font-medium text-muted-foreground px-2 py-1 flex items-center gap-1">
                <Award className="h-3 w-3" />
                Verdiente Abzeichen
              </h4>
              <div className="flex flex-wrap gap-2 p-2">
                {badges.map((badge) => (
                  <TooltipProvider key={badge.id}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Badge
                          variant="secondary"
                          className="cursor-help py-1.5 px-3"
                        >
                          <Award className="h-3 w-3 mr-1 text-yellow-500" />
                          {badge.name}
                        </Badge>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p className="font-medium">{badge.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {badge.description}
                        </p>
                        {badge.unlockedAt && (
                          <p className="text-xs text-muted-foreground mt-1">
                            Freigeschaltet: {new Date(badge.unlockedAt).toLocaleDateString('de-DE')}
                          </p>
                        )}
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                ))}
              </div>
            </div>
          )}
        </ScrollArea>

        {/* Footer */}
        <div className="p-3 border-t bg-muted/30">
          <p className="text-xs text-muted-foreground text-center">
            Tastenkürzel: ← → zum Navigieren, ESC zum Beenden
          </p>
        </div>
      </PopoverContent>
    </Popover>
  )
}
