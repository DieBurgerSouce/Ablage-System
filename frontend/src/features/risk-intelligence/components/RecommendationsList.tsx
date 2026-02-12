/**
 * Recommendations List Component
 *
 * Zeigt Handlungsempfehlungen basierend auf Risikoanalyse.
 */

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Lightbulb,
  AlertCircle,
  AlertTriangle,
  Info,
  ChevronRight,
  TrendingUp,
  CreditCard,
  Users,
  FileText,
  Settings,
} from 'lucide-react';
import type { Recommendation } from '../api/risk-intelligence-api';

interface RecommendationsListProps {
  recommendations: Recommendation[];
  className?: string;
  onActionClick?: (recommendation: Recommendation) => void;
}

export function RecommendationsList({
  recommendations,
  className,
  onActionClick,
}: RecommendationsListProps) {
  const getPriorityIcon = (priority: Recommendation['priority']) => {
    switch (priority) {
      case 'high':
        return <AlertCircle className="w-5 h-5 text-red-500" />;
      case 'medium':
        return <AlertTriangle className="w-5 h-5 text-orange-500" />;
      case 'low':
        return <Info className="w-5 h-5 text-blue-500" />;
    }
  };

  const getPriorityBadge = (priority: Recommendation['priority']) => {
    const variants: Record<string, { variant: 'destructive' | 'secondary' | 'default'; label: string }> = {
      high: { variant: 'destructive', label: 'Hoch' },
      medium: { variant: 'secondary', label: 'Mittel' },
      low: { variant: 'default', label: 'Niedrig' },
    };
    const { variant, label } = variants[priority] || variants.low;
    return <Badge variant={variant}>{label}</Badge>;
  };

  const getCategoryIcon = (category: string) => {
    switch (category.toLowerCase()) {
      case 'payment':
      case 'zahlung':
        return <CreditCard className="w-4 h-4" />;
      case 'trend':
        return <TrendingUp className="w-4 h-4" />;
      case 'network':
      case 'netzwerk':
        return <Users className="w-4 h-4" />;
      case 'document':
      case 'dokument':
        return <FileText className="w-4 h-4" />;
      case 'settings':
      case 'einstellungen':
        return <Settings className="w-4 h-4" />;
      default:
        return <Lightbulb className="w-4 h-4" />;
    }
  };

  // Sort by priority
  const sortedRecommendations = [...recommendations].sort((a, b) => {
    const priorityOrder = { high: 0, medium: 1, low: 2 };
    return priorityOrder[a.priority] - priorityOrder[b.priority];
  });

  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Lightbulb className="w-5 h-5 text-yellow-500" />
          <div>
            <CardTitle className="text-lg">Handlungsempfehlungen</CardTitle>
            <CardDescription>
              {recommendations.length} Empfehlung{recommendations.length !== 1 ? 'en' : ''} basierend auf der Analyse
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {recommendations.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <Lightbulb className="w-12 h-12 mx-auto mb-2 opacity-50" />
            <p>Keine Empfehlungen</p>
            <p className="text-sm">Die Entity hat ein gutes Risikoprofil.</p>
          </div>
        ) : (
          <ScrollArea className="h-80">
            <div className="space-y-4">
              {sortedRecommendations.map((rec, index) => (
                <div
                  key={index}
                  className="p-4 border rounded-lg hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5">
                      {getPriorityIcon(rec.priority)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <h4 className="font-medium">{rec.title}</h4>
                        {getPriorityBadge(rec.priority)}
                        <Badge variant="outline" className="gap-1">
                          {getCategoryIcon(rec.category)}
                          {rec.category}
                        </Badge>
                      </div>
                      <p className="text-sm text-muted-foreground mb-3">
                        {rec.description}
                      </p>
                      {onActionClick && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => onActionClick(rec)}
                          className="gap-1"
                        >
                          {rec.action}
                          <ChevronRight className="w-4 h-4" />
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        )}

        {/* Summary by Priority */}
        {recommendations.length > 0 && (
          <div className="mt-4 pt-4 border-t">
            <p className="text-sm text-muted-foreground mb-2">Nach Priorität</p>
            <div className="flex gap-2 flex-wrap">
              {(['high', 'medium', 'low'] as const).map((priority) => {
                const count = recommendations.filter((r) => r.priority === priority).length;
                if (count === 0) return null;
                return (
                  <Badge
                    key={priority}
                    variant={priority === 'high' ? 'destructive' : priority === 'medium' ? 'secondary' : 'default'}
                  >
                    {priority === 'high' ? 'Hoch' : priority === 'medium' ? 'Mittel' : 'Niedrig'}: {count}
                  </Badge>
                );
              })}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
