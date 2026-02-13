/**
 * Quality Issue Card Component
 *
 * Displays a single quality issue with fix button.
 */

import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import type { QualityIssue } from '../types/data-quality-types';
import {
  CATEGORY_LABELS,
  SEVERITY_COLORS,
  SEVERITY_LABELS,
} from '../types/data-quality-types';
import {
  FolderX,
  Euro,
  CalendarX,
  UsersX,
  Copy,
  FileWarning,
  EyeOff,
  Info,
  Wrench,
} from 'lucide-react';

interface QualityIssueCardProps {
  issue: QualityIssue;
  onFix: () => void;
  isFixing: boolean;
}

// Icon mapping
const CATEGORY_ICON_MAP = {
  missing_category: FolderX,
  missing_amount: Euro,
  missing_date: CalendarX,
  missing_entity: UsersX,
  duplicate_detection: Copy,
  invalid_format: FileWarning,
  ocr_low_confidence: EyeOff,
  missing_metadata: Info,
};

export function QualityIssueCard({ issue, onFix, isFixing }: QualityIssueCardProps) {
  const colors = SEVERITY_COLORS[issue.severity];
  const Icon = CATEGORY_ICON_MAP[issue.category];

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-4">
          {/* Left side - Icon and content */}
          <div className="flex items-start gap-3 flex-1">
            {/* Icon */}
            <div className={`p-2 rounded-lg ${colors.bg}`}>
              <Icon className={`w-5 h-5 ${colors.text}`} />
            </div>

            {/* Content */}
            <div className="flex-1 space-y-2">
              {/* Title and badge */}
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-semibold">
                  {CATEGORY_LABELS[issue.category]}
                </span>
                <Badge
                  variant="outline"
                  className={`${colors.bg} ${colors.text} ${colors.border}`}
                >
                  {SEVERITY_LABELS[issue.severity]}
                </Badge>
              </div>

              {/* Description */}
              <p className="text-sm text-muted-foreground">
                {issue.description}
              </p>

              {/* Count */}
              <div className="text-sm">
                <span className="font-medium">{issue.count}</span>{' '}
                <span className="text-muted-foreground">
                  Dokument{issue.count !== 1 ? 'e' : ''} betroffen
                </span>
              </div>
            </div>
          </div>

          {/* Right side - Fix button */}
          {issue.fixAvailable && (
            <Button
              size="sm"
              onClick={onFix}
              disabled={isFixing}
              className="gap-2 shrink-0"
            >
              <Wrench className="w-4 h-4" />
              {isFixing ? 'Wird bereinigt...' : 'Bereinigen'}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
