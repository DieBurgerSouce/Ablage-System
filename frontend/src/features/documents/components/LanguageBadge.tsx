/**
 * LanguageBadge Component
 *
 * Zeigt die erkannte Dokumentsprache als Badge mit Flagge und Konfidenz-Indikator.
 */

import { Badge } from '@/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

type ConfidenceLevel = 'high' | 'medium' | 'low';

interface LanguageInfo {
  code: string;
  name: string;
  flag: string;
}

const LANGUAGE_MAP: Record<string, LanguageInfo> = {
  de: { code: 'DE', name: 'Deutsch', flag: '\uD83C\uDDE9\uD83C\uDDEA' },
  en: { code: 'EN', name: 'Englisch', flag: '\uD83C\uDDEC\uD83C\uDDE7' },
  fr: { code: 'FR', name: 'Französisch', flag: '\uD83C\uDDEB\uD83C\uDDF7' },
  pl: { code: 'PL', name: 'Polnisch', flag: '\uD83C\uDDF5\uD83C\uDDF1' },
  ru: { code: 'RU', name: 'Russisch', flag: '\uD83C\uDDF7\uD83C\uDDFA' },
  it: { code: 'IT', name: 'Italienisch', flag: '\uD83C\uDDEE\uD83C\uDDF9' },
  es: { code: 'ES', name: 'Spanisch', flag: '\uD83C\uDDEA\uD83C\uDDF8' },
  nl: { code: 'NL', name: 'Niederländisch', flag: '\uD83C\uDDF3\uD83C\uDDF1' },
  pt: { code: 'PT', name: 'Portugiesisch', flag: '\uD83C\uDDF5\uD83C\uDDF9' },
  tr: { code: 'TR', name: 'Tuerkisch', flag: '\uD83C\uDDF9\uD83C\uDDF7' },
};

const CONFIDENCE_CONFIG: Record<
  ConfidenceLevel,
  { color: string; label: string }
> = {
  high: { color: 'bg-green-500', label: 'Hohe Konfidenz' },
  medium: { color: 'bg-yellow-500', label: 'Mittlere Konfidenz' },
  low: { color: 'bg-red-500', label: 'Niedrige Konfidenz' },
};

function getConfidenceLevel(confidence: number): ConfidenceLevel {
  if (confidence >= 0.8) return 'high';
  if (confidence >= 0.5) return 'medium';
  return 'low';
}

export interface LanguageBadgeProps {
  languageCode: string;
  confidence?: number;
  compact?: boolean;
  className?: string;
}

export function LanguageBadge({
  languageCode,
  confidence,
  compact = false,
  className,
}: LanguageBadgeProps) {
  const lang = LANGUAGE_MAP[languageCode.toLowerCase()] || {
    code: languageCode.toUpperCase(),
    name: languageCode,
    flag: '\uD83C\uDF10',
  };

  const confidenceLevel = confidence !== undefined
    ? getConfidenceLevel(confidence)
    : undefined;
  const confidenceConfig = confidenceLevel
    ? CONFIDENCE_CONFIG[confidenceLevel]
    : undefined;

  const badge = (
    <Badge
      variant="outline"
      className={cn(
        'gap-1.5 font-normal',
        compact && 'px-1.5 py-0',
        className
      )}
    >
      <span className="text-xs">{lang.flag}</span>
      {!compact && <span>{lang.name}</span>}
      {compact && <span className="text-xs">{lang.code}</span>}
      {confidenceLevel && (
        <span
          className={cn(
            'inline-block h-2 w-2 rounded-full shrink-0',
            confidenceConfig?.color
          )}
        />
      )}
    </Badge>
  );

  if (confidence === undefined) return badge;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>{badge}</TooltipTrigger>
        <TooltipContent>
          <div className="space-y-1">
            <p className="font-medium">
              Erkannte Sprache: {lang.name} ({lang.code})
            </p>
            <p className="text-xs">
              Konfidenz: {(confidence * 100).toFixed(0)}% ({confidenceConfig?.label})
            </p>
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export default LanguageBadge;
