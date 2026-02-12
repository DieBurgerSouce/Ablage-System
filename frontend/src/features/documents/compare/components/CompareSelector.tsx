/**
 * CompareSelector Component
 *
 * Ermöglicht die Auswahl von zwei Dokumenten für den Vergleich.
 */

import { useState } from 'react';
import { Search, FileText, X, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { ComparisonType } from '../types';
import { COMPARISON_TYPE_LABELS } from '../types';

interface DocumentSelection {
  id: string;
  filename: string;
  documentType?: string | null;
}

interface CompareSelectorProps {
  document1: DocumentSelection | null;
  document2: DocumentSelection | null;
  comparisonType: ComparisonType;
  onDocument1Change: (doc: DocumentSelection | null) => void;
  onDocument2Change: (doc: DocumentSelection | null) => void;
  onComparisonTypeChange: (type: ComparisonType) => void;
  onCompare: () => void;
  isComparing?: boolean;
  availableDocuments?: DocumentSelection[];
}

export function CompareSelector({
  document1,
  document2,
  comparisonType,
  onDocument1Change,
  onDocument2Change,
  onComparisonTypeChange,
  onCompare,
  isComparing = false,
  availableDocuments = [],
}: CompareSelectorProps) {
  const [search1, setSearch1] = useState('');
  const [search2, setSearch2] = useState('');
  const [showDropdown1, setShowDropdown1] = useState(false);
  const [showDropdown2, setShowDropdown2] = useState(false);

  const filteredDocs1 = availableDocuments.filter(
    (doc) =>
      doc.id !== document2?.id &&
      doc.filename.toLowerCase().includes(search1.toLowerCase())
  );

  const filteredDocs2 = availableDocuments.filter(
    (doc) =>
      doc.id !== document1?.id &&
      doc.filename.toLowerCase().includes(search2.toLowerCase())
  );

  const canCompare = document1 && document2 && document1.id !== document2.id;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileText className="h-5 w-5" />
          Dokumente vergleichen
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-[1fr,auto,1fr] gap-4 items-start">
          {/* Dokument 1 */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Dokument 1</label>
            {document1 ? (
              <div className="flex items-center gap-2 p-3 bg-muted rounded-lg">
                <FileText className="h-4 w-4 text-muted-foreground" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{document1.filename}</p>
                  {document1.documentType && (
                    <Badge variant="outline" className="mt-1 text-xs">
                      {document1.documentType}
                    </Badge>
                  )}
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onDocument1Change(null)}
                  aria-label="Dokument 1 entfernen"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ) : (
              <div className="relative">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Dokument suchen..."
                    value={search1}
                    onChange={(e) => setSearch1(e.target.value)}
                    onFocus={() => setShowDropdown1(true)}
                    onBlur={() => setTimeout(() => setShowDropdown1(false), 200)}
                    className="pl-9"
                    aria-label="Dokument 1 suchen"
                  />
                </div>
                {showDropdown1 && filteredDocs1.length > 0 && (
                  <div className="absolute z-10 w-full mt-1 bg-popover border rounded-md shadow-lg max-h-60 overflow-auto">
                    {filteredDocs1.map((doc) => (
                      <button
                        key={doc.id}
                        className={cn(
                          'w-full px-3 py-2 text-left hover:bg-accent text-sm',
                          'flex items-center gap-2'
                        )}
                        onClick={() => {
                          onDocument1Change(doc);
                          setSearch1('');
                        }}
                      >
                        <FileText className="h-4 w-4 text-muted-foreground" />
                        <span className="truncate">{doc.filename}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Pfeil */}
          <div className="hidden md:flex items-center justify-center pt-8">
            <div className="p-2 bg-muted rounded-full">
              <ArrowRight className="h-5 w-5 text-muted-foreground" />
            </div>
          </div>

          {/* Dokument 2 */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Dokument 2</label>
            {document2 ? (
              <div className="flex items-center gap-2 p-3 bg-muted rounded-lg">
                <FileText className="h-4 w-4 text-muted-foreground" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{document2.filename}</p>
                  {document2.documentType && (
                    <Badge variant="outline" className="mt-1 text-xs">
                      {document2.documentType}
                    </Badge>
                  )}
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onDocument2Change(null)}
                  aria-label="Dokument 2 entfernen"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ) : (
              <div className="relative">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Dokument suchen..."
                    value={search2}
                    onChange={(e) => setSearch2(e.target.value)}
                    onFocus={() => setShowDropdown2(true)}
                    onBlur={() => setTimeout(() => setShowDropdown2(false), 200)}
                    className="pl-9"
                    aria-label="Dokument 2 suchen"
                  />
                </div>
                {showDropdown2 && filteredDocs2.length > 0 && (
                  <div className="absolute z-10 w-full mt-1 bg-popover border rounded-md shadow-lg max-h-60 overflow-auto">
                    {filteredDocs2.map((doc) => (
                      <button
                        key={doc.id}
                        className={cn(
                          'w-full px-3 py-2 text-left hover:bg-accent text-sm',
                          'flex items-center gap-2'
                        )}
                        onClick={() => {
                          onDocument2Change(doc);
                          setSearch2('');
                        }}
                      >
                        <FileText className="h-4 w-4 text-muted-foreground" />
                        <span className="truncate">{doc.filename}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Vergleichstyp und Button */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-4 mt-6 pt-4 border-t">
          <div className="flex-1 space-y-2">
            <label htmlFor="comparison-type" className="text-sm font-medium">
              Vergleichsart
            </label>
            <Select
              value={comparisonType}
              onValueChange={(value) => onComparisonTypeChange(value as ComparisonType)}
            >
              <SelectTrigger id="comparison-type" className="w-full sm:w-[200px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(COMPARISON_TYPE_LABELS) as ComparisonType[]).map((type) => (
                  <SelectItem key={type} value={type}>
                    {COMPARISON_TYPE_LABELS[type]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <Button
            onClick={onCompare}
            disabled={!canCompare || isComparing}
            className="mt-auto"
            size="lg"
          >
            {isComparing ? (
              <>
                <span className="animate-spin mr-2">⏳</span>
                Vergleiche...
              </>
            ) : (
              'Vergleich starten'
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
