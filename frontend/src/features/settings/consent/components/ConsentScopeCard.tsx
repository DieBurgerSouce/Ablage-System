/**
 * ConsentScopeCard Component
 *
 * Zeigt eine einzelne Einwilligung mit Toggle und Details.
 */

import { useState } from 'react';
import {
  User,
  Landmark,
  FileText,
  BarChart3,
  Mail,
  Share2,
  Bot,
  Clock,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';
import type { ConsentScopeInfo, ConsentScope } from '../types';
import {
  CONSENT_SCOPE_LABELS,
  CONSENT_SCOPE_DESCRIPTIONS,
} from '../types';

// Icon mapping
const scopeIcons: Record<string, React.ReactNode> = {
  personal_data: <User className="h-5 w-5" />,
  financial_data: <Landmark className="h-5 w-5" />,
  document_processing: <FileText className="h-5 w-5" />,
  analytics: <BarChart3 className="h-5 w-5" />,
  marketing: <Mail className="h-5 w-5" />,
  third_party_sharing: <Share2 className="h-5 w-5" />,
  automated_decisions: <Bot className="h-5 w-5" />,
};

interface ConsentScopeCardProps {
  scopeInfo: ConsentScopeInfo;
  onToggle: (scope: ConsentScope, enabled: boolean) => void;
  isLoading?: boolean;
}

export function ConsentScopeCard({
  scopeInfo,
  onToggle,
  isLoading = false,
}: ConsentScopeCardProps) {
  const [isOpen, setIsOpen] = useState(false);

  const label = CONSENT_SCOPE_LABELS[scopeInfo.scope as ConsentScope] || scopeInfo.scope;
  const description =
    CONSENT_SCOPE_DESCRIPTIONS[scopeInfo.scope as ConsentScope] ||
    scopeInfo.scope_description;
  const icon = scopeIcons[scopeInfo.scope] || <FileText className="h-5 w-5" />;

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return null;
    return new Date(dateStr).toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <Card
      className={cn(
        'transition-all',
        scopeInfo.consent_given
          ? 'border-green-200 dark:border-green-900 bg-green-50/30 dark:bg-green-950/20'
          : 'border-muted'
      )}
    >
      <CardContent className="p-4">
        <div className="flex items-start gap-4">
          {/* Icon */}
          <div
            className={cn(
              'p-2 rounded-lg',
              scopeInfo.consent_given
                ? 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300'
                : 'bg-muted text-muted-foreground'
            )}
          >
            {icon}
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <h3 className="font-semibold">{label}</h3>
                {scopeInfo.consent_given ? (
                  <Badge variant="outline" className="bg-green-100 text-green-700 border-green-200">
                    <CheckCircle2 className="h-3 w-3 mr-1" />
                    Erteilt
                  </Badge>
                ) : (
                  <Badge variant="outline" className="bg-muted text-muted-foreground">
                    <XCircle className="h-3 w-3 mr-1" />
                    Nicht erteilt
                  </Badge>
                )}
              </div>
              <Switch
                checked={scopeInfo.consent_given}
                onCheckedChange={(checked) => onToggle(scopeInfo.scope as ConsentScope, checked)}
                disabled={isLoading}
                aria-label={`Einwilligung für ${label} ${scopeInfo.consent_given ? 'widerrufen' : 'erteilen'}`}
              />
            </div>

            <p className="text-sm text-muted-foreground mt-1">{description}</p>

            <Collapsible open={isOpen} onOpenChange={setIsOpen}>
              <CollapsibleTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className="mt-2 -ml-2 h-8 text-xs"
                  aria-expanded={isOpen}
                >
                  {isOpen ? (
                    <>
                      <ChevronUp className="h-3 w-3 mr-1" />
                      Details ausblenden
                    </>
                  ) : (
                    <>
                      <ChevronDown className="h-3 w-3 mr-1" />
                      Details anzeigen
                    </>
                  )}
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent className="mt-2">
                <div className="rounded-lg bg-muted/50 p-3 space-y-2 text-sm">
                  {scopeInfo.granted_at && (
                    <div className="flex items-center gap-2 text-muted-foreground">
                      <Clock className="h-4 w-4" />
                      <span>Erteilt am: {formatDate(scopeInfo.granted_at)}</span>
                    </div>
                  )}
                  {scopeInfo.valid_until && (
                    <div className="flex items-center gap-2 text-muted-foreground">
                      <Clock className="h-4 w-4" />
                      <span>Gültig bis: {formatDate(scopeInfo.valid_until)}</span>
                    </div>
                  )}
                  {scopeInfo.consent_version && (
                    <div className="text-muted-foreground">
                      Version: {scopeInfo.consent_version}
                    </div>
                  )}
                  {!scopeInfo.granted_at && !scopeInfo.consent_given && (
                    <div className="text-muted-foreground">
                      Sie haben dieser Verarbeitung noch nicht zugestimmt.
                    </div>
                  )}
                </div>
              </CollapsibleContent>
            </Collapsible>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
