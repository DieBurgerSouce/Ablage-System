/**
 * DataSourceSelector Component
 * German Enterprise Document Platform
 */

import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { FileText, Users, Building2, CreditCard, CheckCircle2, Database } from 'lucide-react';
import type { DataSource } from '../types/adhoc-reporting-types';

interface DataSourceSelectorProps {
  dataSources: DataSource[];
  selectedSource: string | null;
  onSelectSource: (sourceKey: string) => void;
  isLoading?: boolean;
}

const DATA_SOURCE_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  rechnungen: FileText,
  dokumente: Database,
  lieferanten: Building2,
  kunden: Users,
  zahlungen: CreditCard,
  genehmigungen: CheckCircle2,
};

export function DataSourceSelector({
  dataSources,
  selectedSource,
  onSelectSource,
  isLoading = false,
}: DataSourceSelectorProps) {
  if (isLoading) {
    return (
      <div className="space-y-3">
        <Label>Datenquelle auswählen</Label>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {[...Array(6)].map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <Label>Datenquelle auswählen</Label>
      <RadioGroup value={selectedSource || ''} onValueChange={onSelectSource}>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {dataSources.map((source) => {
            const Icon = DATA_SOURCE_ICONS[source.key] || Database;
            const isSelected = selectedSource === source.key;

            return (
              <Card
                key={source.key}
                className={`relative cursor-pointer transition-all hover:shadow-md ${
                  isSelected ? 'ring-2 ring-primary' : ''
                }`}
                onClick={() => onSelectSource(source.key)}
              >
                <div className="p-4 flex items-start space-x-3">
                  <RadioGroupItem value={source.key} id={source.key} className="mt-1" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center space-x-2 mb-1">
                      <Icon className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                      <Label
                        htmlFor={source.key}
                        className="font-medium cursor-pointer text-sm"
                      >
                        {source.name}
                      </Label>
                    </div>
                    {source.description && (
                      <p className="text-xs text-muted-foreground line-clamp-2">
                        {source.description}
                      </p>
                    )}
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      </RadioGroup>
    </div>
  );
}
