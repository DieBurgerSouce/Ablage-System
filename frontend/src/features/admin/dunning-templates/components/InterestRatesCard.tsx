/**
 * Interest Rates Card Component
 * Zeigt aktuelle Verzugszinssätze nach BGB §288 an
 */

import { Percent, Scale, Building2, User, Info } from 'lucide-react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { useInterestRates } from '../hooks';

export function InterestRatesCard() {
  const { data: rates, isLoading, error } = useInterestRates();

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-32" />
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error || !rates) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-destructive">Fehler</CardTitle>
          <CardDescription>
            Zinssätze konnten nicht geladen werden
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Scale className="h-5 w-5 text-muted-foreground" />
          <CardTitle>Aktuelle Verzugszinssätze</CardTitle>
        </div>
        <CardDescription>{rates.legalBasis}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Basiszinssatz */}
        <div className="rounded-lg border bg-muted/50 p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Percent className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-medium">Basiszinssatz</span>
            </div>
            <span className="text-lg font-bold">
              {rates.baseRate.toFixed(2).replace('.', ',')}%
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Bundesbank-Referenzzins (halbjährlich aktualisiert)
          </p>
        </div>

        {/* B2B Rate */}
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-900 dark:bg-blue-950">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Building2 className="h-4 w-4 text-blue-600 dark:text-blue-400" />
              <span className="text-sm font-medium">Geschäftskunden (B2B)</span>
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger>
                    <Info className="h-3 w-3 text-muted-foreground" />
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>Basiszins + 9 Prozentpunkte</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>
            <span className="text-lg font-bold text-blue-700 dark:text-blue-300">
              {rates.b2bRate.toFixed(2).replace('.', ',')}%
            </span>
          </div>
          <div className="mt-2 flex items-center justify-between text-xs">
            <span className="text-muted-foreground">
              + Verzugspauschale: {rates.b2bPauschale.toFixed(2).replace('.', ',')} EUR
            </span>
            <span className="text-muted-foreground">
              ({rates.b2bPauschaleLegalBasis})
            </span>
          </div>
        </div>

        {/* B2C Rate */}
        <div className="rounded-lg border border-green-200 bg-green-50 p-4 dark:border-green-900 dark:bg-green-950">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <User className="h-4 w-4 text-green-600 dark:text-green-400" />
              <span className="text-sm font-medium">Privatkunden (B2C)</span>
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger>
                    <Info className="h-3 w-3 text-muted-foreground" />
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>Basiszins + 5 Prozentpunkte</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>
            <span className="text-lg font-bold text-green-700 dark:text-green-300">
              {rates.b2cRate.toFixed(2).replace('.', ',')}%
            </span>
          </div>
        </div>

        {/* Note */}
        {rates.note && (
          <p className="text-xs text-muted-foreground italic">{rates.note}</p>
        )}
      </CardContent>
    </Card>
  );
}
