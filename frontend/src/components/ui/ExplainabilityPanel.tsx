/**
 * ExplainabilityPanel - XAI "Warum?" Erklaerungspanel
 *
 * Zeigt detaillierte Erklaerungen fuer KI-Entscheidungen an.
 * Features:
 * - "Warum?"-Button zum Aufklappen
 * - Confidence-Breakdown Visualisierung
 * - Faktor-Gewichtung mit Impact-Scores
 * - Alternative Optionen Anzeige
 * - Entscheidungsbaum-Visualisierung
 */

import * as React from 'react';
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  HelpCircle,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  CheckCircle2,
  Info,
  TrendingUp,
  TrendingDown,
  Shield,
  DollarSign,
  Clock,
  Target,
  Lightbulb,
  XCircle,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

// =============================================================================
// Types
// =============================================================================

export type ConfidenceLevel = 'very_high' | 'high' | 'medium' | 'low' | 'uncertain';

export type FactorCategory =
  | 'FINANCIAL'
  | 'RISK'
  | 'COMPLIANCE'
  | 'TREND'
  | 'PATTERN'
  | 'HISTORICAL'
  | 'EXTERNAL';

export interface ExplanationFactor {
  id: string;
  name: string;
  description: string;
  impact_weight: number; // -1.0 to 1.0
  category: FactorCategory;
  value?: string | number;
  threshold?: string | number;
  contribution_percent: number;
}

export interface AlternativeOption {
  id: string;
  name: string;
  description: string;
  confidence: number;
  reason_not_chosen: string;
}

export interface ImpactBreakdown {
  financial_impact?: {
    amount: number;
    currency: string;
    timeframe: string;
    direction: 'positive' | 'negative' | 'neutral';
  };
  risk_impact?: {
    level: 'low' | 'medium' | 'high' | 'critical';
    description: string;
  };
  temporal_impact?: {
    urgency: 'immediate' | 'short_term' | 'medium_term' | 'long_term';
    deadline?: string;
  };
}

export interface DecisionExplanation {
  decision_id: string;
  decision_type: string;
  summary: string;
  detailed_explanation: string;
  confidence: number;
  confidence_level: ConfidenceLevel;
  factors: ExplanationFactor[];
  alternatives: AlternativeOption[];
  impact: ImpactBreakdown;
  recommendation: string;
  created_at: string;
}

export interface ExplainabilityPanelProps {
  /** Explanation data to display */
  explanation?: DecisionExplanation;
  /** Loading state */
  isLoading?: boolean;
  /** Error message */
  error?: string;
  /** Callback when "Warum?" button is clicked */
  onRequestExplanation?: () => void;
  /** Whether explanation is already loaded */
  hasExplanation?: boolean;
  /** Compact mode for inline use */
  compact?: boolean;
  /** Custom class name */
  className?: string;
}

// =============================================================================
// Helper Components
// =============================================================================

const ConfidenceBadge: React.FC<{ level: ConfidenceLevel; confidence: number }> = ({
  level,
  confidence,
}) => {
  const config: Record<ConfidenceLevel, { label: string; color: string; icon: React.ReactNode }> = {
    very_high: {
      label: 'Sehr hoch',
      color: 'bg-green-500/10 text-green-700 border-green-200',
      icon: <CheckCircle2 className="h-3 w-3" />,
    },
    high: {
      label: 'Hoch',
      color: 'bg-emerald-500/10 text-emerald-700 border-emerald-200',
      icon: <CheckCircle2 className="h-3 w-3" />,
    },
    medium: {
      label: 'Mittel',
      color: 'bg-yellow-500/10 text-yellow-700 border-yellow-200',
      icon: <Info className="h-3 w-3" />,
    },
    low: {
      label: 'Niedrig',
      color: 'bg-orange-500/10 text-orange-700 border-orange-200',
      icon: <AlertTriangle className="h-3 w-3" />,
    },
    uncertain: {
      label: 'Unsicher',
      color: 'bg-red-500/10 text-red-700 border-red-200',
      icon: <AlertTriangle className="h-3 w-3" />,
    },
  };

  const { label, color, icon } = config[level];

  return (
    <Badge variant="outline" className={cn('gap-1', color)}>
      {icon}
      <span>{label}</span>
      <span className="font-mono">({(confidence * 100).toFixed(0)}%)</span>
    </Badge>
  );
};

const FactorCategoryIcon: React.FC<{ category: FactorCategory }> = ({ category }) => {
  const icons: Record<FactorCategory, React.ReactNode> = {
    FINANCIAL: <DollarSign className="h-4 w-4 text-green-600" />,
    RISK: <Shield className="h-4 w-4 text-red-600" />,
    COMPLIANCE: <CheckCircle2 className="h-4 w-4 text-blue-600" />,
    TREND: <TrendingUp className="h-4 w-4 text-purple-600" />,
    PATTERN: <Target className="h-4 w-4 text-orange-600" />,
    HISTORICAL: <Clock className="h-4 w-4 text-gray-600" />,
    EXTERNAL: <Info className="h-4 w-4 text-cyan-600" />,
  };

  return icons[category] || <Info className="h-4 w-4" />;
};

const FactorBar: React.FC<{ factor: ExplanationFactor }> = ({ factor }) => {
  const isPositive = factor.impact_weight >= 0;
  const absWeight = Math.abs(factor.impact_weight) * 100;

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <div className="flex items-center gap-2">
          <FactorCategoryIcon category={factor.category} />
          <span className="font-medium">{factor.name}</span>
        </div>
        <div className="flex items-center gap-1">
          {isPositive ? (
            <TrendingUp className="h-3 w-3 text-green-600" />
          ) : (
            <TrendingDown className="h-3 w-3 text-red-600" />
          )}
          <span className={cn('font-mono text-xs', isPositive ? 'text-green-600' : 'text-red-600')}>
            {isPositive ? '+' : '-'}
            {factor.contribution_percent.toFixed(0)}%
          </span>
        </div>
      </div>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <div className="relative h-2 bg-muted rounded-full overflow-hidden cursor-help">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${absWeight}%` }}
                transition={{ duration: 0.5, ease: 'easeOut' }}
                className={cn(
                  'absolute h-full rounded-full',
                  isPositive ? 'bg-green-500' : 'bg-red-500'
                )}
              />
            </div>
          </TooltipTrigger>
          <TooltipContent>
            <p className="max-w-xs">{factor.description}</p>
            {factor.value !== undefined && (
              <p className="text-xs text-muted-foreground mt-1">
                Wert: {factor.value}
                {factor.threshold !== undefined && ` (Schwelle: ${factor.threshold})`}
              </p>
            )}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>
  );
};

const AlternativeOptionCard: React.FC<{ option: AlternativeOption }> = ({ option }) => (
  <div className="p-3 bg-muted/50 rounded-lg border border-muted">
    <div className="flex items-center justify-between mb-1">
      <span className="font-medium text-sm">{option.name}</span>
      <Badge variant="secondary" className="text-xs">
        {(option.confidence * 100).toFixed(0)}%
      </Badge>
    </div>
    <p className="text-xs text-muted-foreground mb-2">{option.description}</p>
    <div className="flex items-start gap-1 text-xs text-orange-600">
      <XCircle className="h-3 w-3 mt-0.5 flex-shrink-0" />
      <span>{option.reason_not_chosen}</span>
    </div>
  </div>
);

const ImpactSection: React.FC<{ impact: ImpactBreakdown }> = ({ impact }) => (
  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
    {impact.financial_impact && (
      <div className="p-3 bg-green-50 dark:bg-green-950/20 rounded-lg border border-green-200 dark:border-green-900">
        <div className="flex items-center gap-2 mb-1">
          <DollarSign className="h-4 w-4 text-green-600" />
          <span className="text-sm font-medium">Finanzieller Einfluss</span>
        </div>
        <p
          className={cn(
            'text-lg font-bold',
            impact.financial_impact.direction === 'positive'
              ? 'text-green-600'
              : impact.financial_impact.direction === 'negative'
                ? 'text-red-600'
                : 'text-gray-600'
          )}
        >
          {impact.financial_impact.direction === 'positive' ? '+' : ''}
          {impact.financial_impact.amount.toLocaleString('de-DE')} {impact.financial_impact.currency}
        </p>
        <p className="text-xs text-muted-foreground">{impact.financial_impact.timeframe}</p>
      </div>
    )}

    {impact.risk_impact && (
      <div className="p-3 bg-red-50 dark:bg-red-950/20 rounded-lg border border-red-200 dark:border-red-900">
        <div className="flex items-center gap-2 mb-1">
          <Shield className="h-4 w-4 text-red-600" />
          <span className="text-sm font-medium">Risiko</span>
        </div>
        <Badge
          variant="outline"
          className={cn(
            impact.risk_impact.level === 'low' && 'bg-green-100 text-green-700',
            impact.risk_impact.level === 'medium' && 'bg-yellow-100 text-yellow-700',
            impact.risk_impact.level === 'high' && 'bg-orange-100 text-orange-700',
            impact.risk_impact.level === 'critical' && 'bg-red-100 text-red-700'
          )}
        >
          {impact.risk_impact.level === 'low' && 'Niedrig'}
          {impact.risk_impact.level === 'medium' && 'Mittel'}
          {impact.risk_impact.level === 'high' && 'Hoch'}
          {impact.risk_impact.level === 'critical' && 'Kritisch'}
        </Badge>
        <p className="text-xs text-muted-foreground mt-1">{impact.risk_impact.description}</p>
      </div>
    )}

    {impact.temporal_impact && (
      <div className="p-3 bg-blue-50 dark:bg-blue-950/20 rounded-lg border border-blue-200 dark:border-blue-900">
        <div className="flex items-center gap-2 mb-1">
          <Clock className="h-4 w-4 text-blue-600" />
          <span className="text-sm font-medium">Zeitlicher Rahmen</span>
        </div>
        <Badge variant="outline" className="bg-blue-100 text-blue-700">
          {impact.temporal_impact.urgency === 'immediate' && 'Sofort'}
          {impact.temporal_impact.urgency === 'short_term' && 'Kurzfristig'}
          {impact.temporal_impact.urgency === 'medium_term' && 'Mittelfristig'}
          {impact.temporal_impact.urgency === 'long_term' && 'Langfristig'}
        </Badge>
        {impact.temporal_impact.deadline && (
          <p className="text-xs text-muted-foreground mt-1">
            Frist: {new Date(impact.temporal_impact.deadline).toLocaleDateString('de-DE')}
          </p>
        )}
      </div>
    )}
  </div>
);

// =============================================================================
// Main Component
// =============================================================================

export function ExplainabilityPanel({
  explanation,
  isLoading = false,
  error,
  onRequestExplanation,
  hasExplanation = false,
  compact = false,
  className,
}: ExplainabilityPanelProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [showAlternatives, setShowAlternatives] = useState(false);

  // "Warum?" Button for requesting explanation
  const WarumButton = () => (
    <Button
      variant="ghost"
      size={compact ? 'sm' : 'default'}
      onClick={() => {
        if (!hasExplanation && onRequestExplanation) {
          onRequestExplanation();
        }
        setIsOpen(!isOpen);
      }}
      disabled={isLoading}
      className={cn(
        'gap-2',
        hasExplanation && 'text-blue-600 hover:text-blue-700',
        compact && 'h-7 px-2 text-xs'
      )}
    >
      <HelpCircle className={cn('h-4 w-4', compact && 'h-3 w-3')} />
      <span>Warum?</span>
      {isOpen ? (
        <ChevronUp className={cn('h-4 w-4', compact && 'h-3 w-3')} />
      ) : (
        <ChevronDown className={cn('h-4 w-4', compact && 'h-3 w-3')} />
      )}
    </Button>
  );

  // Loading state
  if (isLoading) {
    return (
      <div className={cn('flex items-center gap-2 text-muted-foreground', className)}>
        <div className="h-4 w-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
        <span className="text-sm">Erklaerung wird geladen...</span>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className={cn('flex items-center gap-2 text-red-600', className)}>
        <AlertTriangle className="h-4 w-4" />
        <span className="text-sm">{error}</span>
      </div>
    );
  }

  // Compact mode without explanation
  if (compact && !explanation) {
    return (
      <div className={className}>
        <WarumButton />
      </div>
    );
  }

  return (
    <div className={className}>
      <Collapsible open={isOpen} onOpenChange={setIsOpen}>
        <CollapsibleTrigger asChild>
          <div>
            <WarumButton />
          </div>
        </CollapsibleTrigger>

        <AnimatePresence>
          {isOpen && explanation && (
            <CollapsibleContent forceMount>
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.2 }}
              >
                <Card className="mt-3">
                  <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-lg flex items-center gap-2">
                        <Lightbulb className="h-5 w-5 text-yellow-500" />
                        KI-Erklaerung
                      </CardTitle>
                      <ConfidenceBadge
                        level={explanation.confidence_level}
                        confidence={explanation.confidence}
                      />
                    </div>
                  </CardHeader>

                  <CardContent className="space-y-4">
                    {/* Summary */}
                    <div className="p-3 bg-blue-50 dark:bg-blue-950/20 rounded-lg border border-blue-200 dark:border-blue-900">
                      <h4 className="font-medium text-sm mb-1 flex items-center gap-2">
                        <Info className="h-4 w-4 text-blue-600" />
                        Zusammenfassung
                      </h4>
                      <p className="text-sm">{explanation.summary}</p>
                    </div>

                    {/* Detailed Explanation */}
                    {explanation.detailed_explanation && (
                      <div>
                        <h4 className="font-medium text-sm mb-2">Detaillierte Erklaerung</h4>
                        <p className="text-sm text-muted-foreground">
                          {explanation.detailed_explanation}
                        </p>
                      </div>
                    )}

                    {/* Factors */}
                    {explanation.factors.length > 0 && (
                      <div>
                        <h4 className="font-medium text-sm mb-3">Einflussfaktoren</h4>
                        <div className="space-y-3">
                          {explanation.factors
                            .sort((a, b) => Math.abs(b.impact_weight) - Math.abs(a.impact_weight))
                            .slice(0, 5)
                            .map((factor) => (
                              <FactorBar key={factor.id} factor={factor} />
                            ))}
                        </div>
                      </div>
                    )}

                    {/* Impact */}
                    {(explanation.impact.financial_impact ||
                      explanation.impact.risk_impact ||
                      explanation.impact.temporal_impact) && (
                      <div>
                        <h4 className="font-medium text-sm mb-3">Auswirkungen</h4>
                        <ImpactSection impact={explanation.impact} />
                      </div>
                    )}

                    {/* Recommendation */}
                    {explanation.recommendation && (
                      <div className="p-3 bg-green-50 dark:bg-green-950/20 rounded-lg border border-green-200 dark:border-green-900">
                        <h4 className="font-medium text-sm mb-1 flex items-center gap-2">
                          <Lightbulb className="h-4 w-4 text-green-600" />
                          Empfehlung
                        </h4>
                        <p className="text-sm">{explanation.recommendation}</p>
                      </div>
                    )}

                    {/* Alternatives */}
                    {explanation.alternatives.length > 0 && (
                      <div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setShowAlternatives(!showAlternatives)}
                          className="gap-2 mb-2"
                        >
                          <span>Alternativen anzeigen ({explanation.alternatives.length})</span>
                          {showAlternatives ? (
                            <ChevronUp className="h-4 w-4" />
                          ) : (
                            <ChevronDown className="h-4 w-4" />
                          )}
                        </Button>

                        <AnimatePresence>
                          {showAlternatives && (
                            <motion.div
                              initial={{ opacity: 0, height: 0 }}
                              animate={{ opacity: 1, height: 'auto' }}
                              exit={{ opacity: 0, height: 0 }}
                              className="grid grid-cols-1 md:grid-cols-2 gap-2"
                            >
                              {explanation.alternatives.map((alt) => (
                                <AlternativeOptionCard key={alt.id} option={alt} />
                              ))}
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </div>
                    )}

                    {/* Timestamp */}
                    <div className="text-xs text-muted-foreground pt-2 border-t">
                      Erstellt:{' '}
                      {new Date(explanation.created_at).toLocaleString('de-DE', {
                        dateStyle: 'medium',
                        timeStyle: 'short',
                      })}
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            </CollapsibleContent>
          )}
        </AnimatePresence>
      </Collapsible>
    </div>
  );
}

// =============================================================================
// Compact "Warum?" Button Export
// =============================================================================

export interface WarumButtonProps {
  onClick: () => void;
  isLoading?: boolean;
  hasExplanation?: boolean;
  size?: 'sm' | 'default';
  className?: string;
}

export function WarumButton({
  onClick,
  isLoading = false,
  hasExplanation = false,
  size = 'sm',
  className,
}: WarumButtonProps) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size={size}
            onClick={onClick}
            disabled={isLoading}
            className={cn(
              'gap-1',
              hasExplanation && 'text-blue-600 hover:text-blue-700',
              size === 'sm' && 'h-7 px-2',
              className
            )}
          >
            {isLoading ? (
              <div className="h-3 w-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
            ) : (
              <HelpCircle className={cn('h-4 w-4', size === 'sm' && 'h-3 w-3')} />
            )}
            <span className={cn(size === 'sm' && 'text-xs')}>Warum?</span>
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          <p>KI-Entscheidung erklaeren</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export default ExplainabilityPanel;
