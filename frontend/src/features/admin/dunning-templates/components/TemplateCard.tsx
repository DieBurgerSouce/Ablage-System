/**
 * Template Card Component
 * Zeigt eine einzelne Mahnbrief-Vorlage an
 */

import { FileText, AlertTriangle, Clock, Euro } from 'lucide-react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import type { DunningTemplate } from '../types';

interface TemplateCardProps {
  template: DunningTemplate;
  isSelected?: boolean;
  onClick?: () => void;
}

const toneColors: Record<string, string> = {
  freundlich: 'bg-green-100 text-green-800',
  sachlich: 'bg-blue-100 text-blue-800',
  bestimmt: 'bg-orange-100 text-orange-800',
  streng: 'bg-red-100 text-red-800',
};

const toneLabels: Record<string, string> = {
  freundlich: 'Freundlich',
  sachlich: 'Sachlich',
  bestimmt: 'Bestimmt',
  streng: 'Streng',
};

export function TemplateCard({ template, isSelected, onClick }: TemplateCardProps) {
  return (
    <Card
      className={`cursor-pointer transition-all hover:shadow-md ${
        isSelected ? 'ring-2 ring-primary' : ''
      }`}
      onClick={onClick}
    >
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-muted-foreground" />
            <CardTitle className="text-base">{template.name}</CardTitle>
          </div>
          <Badge variant="outline" className={toneColors[template.tone] || ''}>
            {toneLabels[template.tone] || template.tone}
          </Badge>
        </div>
        <CardDescription>{template.title}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div className="flex items-center gap-2">
            <Euro className="h-4 w-4 text-muted-foreground" />
            <span>
              {template.fee > 0
                ? `${template.fee.toFixed(2).replace('.', ',')} EUR`
                : 'Keine Gebuehr'}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-muted-foreground" />
            <span>{template.paymentDays} Tage Frist</span>
          </div>
        </div>
        {template.escalationWarning && (
          <div className="mt-3 flex items-start gap-2 rounded-md bg-orange-50 p-2 text-xs text-orange-800">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span className="line-clamp-2">{template.escalationWarning}</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
