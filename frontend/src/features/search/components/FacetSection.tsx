/**
 * FacetSection - Einzelne aufklappbare Facetten-Sektion
 *
 * Zeigt Checkbox-Eintraege mit Anzahl-Badges an.
 * Unterstuetzt "Mehr anzeigen" fuer lange Listen.
 * Alle Texte in Deutsch.
 */
import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { FacetBucket } from '../types/facets';

interface FacetSectionProps {
  title: string;
  buckets: FacetBucket[];
  selected: string[];
  onChange: (values: string[]) => void;
  initialExpanded?: boolean;
  maxVisible?: number;
}

/** Deutsche Bezeichnungen fuer Facetten-Werte */
const FACET_LABELS: Record<string, string> = {
  // Dokumenttypen
  'eingangsrechnung': 'Eingangsrechnung',
  'ausgangsrechnung': 'Ausgangsrechnung',
  'vertrag': 'Vertrag',
  'angebot': 'Angebot',
  'lieferschein': 'Lieferschein',
  'mahnung': 'Mahnung',
  'gutschrift': 'Gutschrift',
  'bestellung': 'Bestellung',
  'sonstiges': 'Sonstiges',
  // Status
  'completed': 'Verarbeitet',
  'pending': 'In Bearbeitung',
  'failed': 'Fehlerhaft',
  'uploaded': 'Hochgeladen',
  'processing': 'Wird verarbeitet',
  // OCR-Backends
  'deepseek': 'DeepSeek',
  'got_ocr': 'GOT-OCR',
  'surya': 'Surya',
  'surya_gpu': 'Surya GPU',
};

function getDisplayLabel(bucket: FacetBucket): string {
  return FACET_LABELS[bucket.value] || bucket.label || bucket.value;
}

export function FacetSection({
  title,
  buckets,
  selected,
  onChange,
  initialExpanded = true,
  maxVisible = 5,
}: FacetSectionProps) {
  const [expanded, setExpanded] = useState(initialExpanded);
  const [showAll, setShowAll] = useState(false);

  const visibleBuckets = showAll ? buckets : buckets.slice(0, maxVisible);
  const hasMore = buckets.length > maxVisible;

  const toggleValue = (value: string) => {
    if (selected.includes(value)) {
      onChange(selected.filter(v => v !== value));
    } else {
      onChange([...selected, value]);
    }
  };

  return (
    <div className="border-b pb-3 last:border-b-0">
      <button
        type="button"
        className="flex items-center justify-between w-full py-2 text-sm font-medium text-foreground hover:text-primary transition-colors"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
      >
        <span>{title}</span>
        {expanded
          ? <ChevronDown className="h-4 w-4" />
          : <ChevronRight className="h-4 w-4" />
        }
      </button>

      {expanded && (
        <div className="space-y-1 mt-1" role="group" aria-label={title}>
          {visibleBuckets.map((bucket) => {
            const isChecked = selected.includes(bucket.value);
            return (
              <div
                key={bucket.value}
                className="flex items-center gap-2 px-1 py-1 hover:bg-muted/50 rounded cursor-pointer"
                onClick={() => toggleValue(bucket.value)}
                role="checkbox"
                aria-checked={isChecked}
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    toggleValue(bucket.value);
                  }
                }}
              >
                <Checkbox
                  checked={isChecked}
                  className="h-3.5 w-3.5"
                  tabIndex={-1}
                />
                <span className="text-sm flex-1 truncate">
                  {getDisplayLabel(bucket)}
                </span>
                <Badge variant="secondary" className="h-5 px-1.5 text-xs font-normal">
                  {bucket.count}
                </Badge>
              </div>
            );
          })}

          {hasMore && (
            <Button
              variant="ghost"
              size="sm"
              className="w-full text-xs text-muted-foreground"
              onClick={(e) => {
                e.stopPropagation();
                setShowAll(!showAll);
              }}
            >
              {showAll
                ? 'Weniger anzeigen'
                : `Mehr anzeigen (${buckets.length - maxVisible})`
              }
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
