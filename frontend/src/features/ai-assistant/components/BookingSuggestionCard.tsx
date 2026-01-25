/**
 * BookingSuggestionCard - Displays a booking suggestion from the Finance Assistant
 *
 * Vision 2.0 - Phase 1 (Januar 2026)
 *
 * Shows SKR03/SKR04 account suggestions with visual representation
 */

import { useState } from 'react';
import { motion } from 'framer-motion';
import {
  ArrowRight,
  Copy,
  Check,
  ChevronDown,
  ChevronUp,
  Calculator,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { BookingSuggestionData } from '@/lib/api/services/finance-assistant';

interface BookingSuggestionCardProps {
  suggestion: BookingSuggestionData;
  onDismiss: () => void;
  onApply?: (suggestion: BookingSuggestionData) => void;
  className?: string;
}

export function BookingSuggestionCard({
  suggestion,
  onDismiss,
  onApply,
  className,
}: BookingSuggestionCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isCopied, setIsCopied] = useState(false);

  const handleCopy = () => {
    const text = `
Soll: ${suggestion.debit_account} - ${suggestion.debit_account_name}
Haben: ${suggestion.credit_account} - ${suggestion.credit_account_name}
Betrag: ${formatCurrency(suggestion.amount)}
${suggestion.tax_code ? `Steuerschluessel: ${suggestion.tax_code}` : ''}
Beschreibung: ${suggestion.description}
    `.trim();

    navigator.clipboard.writeText(text);
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
    }).format(amount);
  };

  const confidenceColor =
    suggestion.confidence >= 0.9
      ? 'bg-green-500'
      : suggestion.confidence >= 0.7
        ? 'bg-yellow-500'
        : 'bg-orange-500';

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className={cn(
        'rounded-lg border bg-card p-4 shadow-sm',
        className
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="rounded-full bg-primary/10 p-2">
            <Calculator className="h-4 w-4 text-primary" />
          </div>
          <div>
            <h4 className="font-medium">Buchungsvorschlag</h4>
            <p className="text-sm text-muted-foreground">{suggestion.description}</p>
          </div>
        </div>
        <Button variant="ghost" size="icon" onClick={onDismiss} className="h-8 w-8">
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Booking Visual */}
      <div className="mt-4 rounded-lg bg-muted/30 p-4">
        <div className="flex items-center justify-between gap-4">
          {/* Debit Side */}
          <div className="flex-1">
            <div className="text-xs font-medium text-muted-foreground mb-1">SOLL</div>
            <div className="rounded-md border bg-background p-3">
              <div className="font-mono text-lg font-bold">{suggestion.debit_account}</div>
              <div className="text-sm text-muted-foreground">{suggestion.debit_account_name}</div>
            </div>
          </div>

          {/* Arrow */}
          <div className="flex flex-col items-center gap-1">
            <ArrowRight className="h-5 w-5 text-muted-foreground" />
            <div className="text-lg font-bold text-primary">
              {formatCurrency(suggestion.amount)}
            </div>
          </div>

          {/* Credit Side */}
          <div className="flex-1">
            <div className="text-xs font-medium text-muted-foreground mb-1">HABEN</div>
            <div className="rounded-md border bg-background p-3">
              <div className="font-mono text-lg font-bold">{suggestion.credit_account}</div>
              <div className="text-sm text-muted-foreground">{suggestion.credit_account_name}</div>
            </div>
          </div>
        </div>

        {/* Tax Code */}
        {suggestion.tax_code && (
          <div className="mt-3 flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Steuerschluessel:</span>
            <Badge variant="secondary">{suggestion.tax_code}</Badge>
          </div>
        )}
      </div>

      {/* Confidence Indicator */}
      <div className="mt-3 flex items-center gap-2">
        <div className={cn('h-2 w-2 rounded-full', confidenceColor)} />
        <span className="text-sm text-muted-foreground">
          Konfidenz: {Math.round(suggestion.confidence * 100)}%
        </span>
      </div>

      {/* Expandable Reasoning */}
      <div className="mt-3">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          {isExpanded ? (
            <ChevronUp className="h-4 w-4" />
          ) : (
            <ChevronDown className="h-4 w-4" />
          )}
          Begruendung anzeigen
        </button>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="mt-2 rounded-md bg-muted/50 p-3 text-sm"
          >
            {suggestion.reasoning}
          </motion.div>
        )}
      </div>

      {/* Actions */}
      <div className="mt-4 flex items-center gap-2">
        {onApply && (
          <Button size="sm" className="flex-1" onClick={() => onApply(suggestion)}>
            <Check className="mr-2 h-4 w-4" />
            Uebernehmen
          </Button>
        )}
        <Button variant="outline" size="sm" onClick={handleCopy}>
          {isCopied ? (
            <Check className="mr-2 h-4 w-4 text-green-500" />
          ) : (
            <Copy className="mr-2 h-4 w-4" />
          )}
          {isCopied ? 'Kopiert' : 'Kopieren'}
        </Button>
      </div>
    </motion.div>
  );
}
