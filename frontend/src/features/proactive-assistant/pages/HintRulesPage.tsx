// Hint Rules Configuration Page

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { AlertCircle, Settings, ChevronDown, ChevronRight } from 'lucide-react';
import { HintRuleEditor } from '../components/HintRuleEditor';
import { useRulesQuery } from '../hooks/use-proactive-assistant-queries';
import { UI_LABELS, CATEGORY_CONFIG, PRIORITY_CONFIG } from '../types/proactive-assistant-types';

export function HintRulesPage() {
  const { data: rules, isLoading, error, refetch } = useRulesQuery();
  const [expandedRuleId, setExpandedRuleId] = useState<string | null>(null);

  const toggleRule = (ruleId: string) => {
    setExpandedRuleId(expandedRuleId === ruleId ? null : ruleId);
  };

  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Page Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <Settings className="h-8 w-8" />
            {UI_LABELS.rulesPageTitle}
          </h1>
          <p className="text-muted-foreground mt-1">
            {UI_LABELS.rulesPageSubtitle}
          </p>
        </div>
      </div>

      <Separator />

      {/* Error State */}
      {error && (
        <div className="flex items-center gap-2 p-4 bg-destructive/10 border border-destructive rounded-lg text-destructive">
          <AlertCircle className="h-5 w-5" />
          <div className="flex-1">
            <p className="text-sm font-medium">Fehler beim Laden der Regeln</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            {UI_LABELS.actions.retry}
          </Button>
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      )}

      {/* Rules List */}
      {!isLoading && rules && (
        <div className="space-y-4">
          {rules.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-muted-foreground">Keine Regeln konfiguriert</p>
            </div>
          ) : (
            rules.map((rule) => {
              const isExpanded = expandedRuleId === rule.ruleId;
              const categoryConfig = CATEGORY_CONFIG[rule.category];
              const priorityConfig = PRIORITY_CONFIG[rule.priority];

              return (
                <div key={rule.ruleId} className="border rounded-lg overflow-hidden">
                  {/* Rule Header */}
                  <button
                    className="w-full p-4 flex items-center justify-between hover:bg-muted/50 transition-colors"
                    onClick={() => toggleRule(rule.ruleId)}
                  >
                    <div className="flex items-center gap-3">
                      {isExpanded ? (
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                      ) : (
                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                      )}
                      <div className="text-left">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-semibold">{rule.name}</span>
                          <Badge
                            variant={rule.enabled ? 'default' : 'secondary'}
                          >
                            {rule.enabled ? 'Aktiv' : 'Inaktiv'}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <Badge
                            variant="outline"
                            className={categoryConfig.bgColor}
                          >
                            <span className="mr-1">{categoryConfig.icon}</span>
                            {categoryConfig.label}
                          </Badge>
                          <Badge
                            variant={priorityConfig.variant}
                            className={priorityConfig.bgColor}
                          >
                            {priorityConfig.label}
                          </Badge>
                        </div>
                      </div>
                    </div>
                  </button>

                  {/* Rule Editor (Expanded) */}
                  {isExpanded && (
                    <div className="border-t p-4 bg-muted/20">
                      <HintRuleEditor
                        rule={rule}
                        onCancel={() => setExpandedRuleId(null)}
                      />
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
