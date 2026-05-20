/**
 * Graph Search Component
 * Suchfeld mit Ergebnis-Dropdown für Graph-Entitäten
 */

import { useState } from 'react';
import { Search, FileText, Building2, Receipt, ArrowRightLeft, CreditCard } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useGraphSearch } from '../hooks/use-knowledge-graph-queries';
import type { SearchResult, NodeType } from '../types';

interface GraphSearchProps {
  onSelect: (result: SearchResult) => void;
}

const NODE_TYPE_CONFIG: Record<NodeType, { label: string; icon: typeof FileText; color: string }> = {
  entity: { label: 'Entität', icon: Building2, color: 'blue' },
  document: { label: 'Dokument', icon: FileText, color: 'green' },
  invoice: { label: 'Rechnung', icon: Receipt, color: 'orange' },
  transaction: { label: 'Transaktion', icon: ArrowRightLeft, color: 'purple' },
  payment: { label: 'Zahlung', icon: CreditCard, color: 'teal' },
};

export function GraphSearch({ onSelect }: GraphSearchProps) {
  const [query, setQuery] = useState('');
  const [showResults, setShowResults] = useState(false);
  const { data: results, isLoading } = useGraphSearch(query);

  const handleSelect = (result: SearchResult) => {
    onSelect(result);
    setQuery('');
    setShowResults(false);
  };

  return (
    <div className="relative w-full max-w-md">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          type="text"
          placeholder="Entität oder Dokument suchen..."
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setShowResults(true);
          }}
          onFocus={() => setShowResults(true)}
          onBlur={() => {
            // Verzögerung, damit Klick auf Ergebnis noch registriert wird
            setTimeout(() => setShowResults(false), 200);
          }}
          className="pl-10"
        />
      </div>

      {showResults && query.length >= 2 && (
        <Card className="absolute z-10 mt-2 w-full overflow-hidden shadow-lg">
          {isLoading ? (
            <div className="p-4 text-center text-sm text-muted-foreground">Suche läuft...</div>
          ) : results && results.length > 0 ? (
            <div className="max-h-96 overflow-y-auto">
              {results.map((result) => {
                const config = NODE_TYPE_CONFIG[result.type];
                const Icon = config.icon;

                return (
                  <button
                    key={result.id}
                    onClick={() => handleSelect(result)}
                    className="flex w-full items-center gap-3 border-b border-border p-3 text-left transition-colors hover:bg-accent"
                  >
                    <Icon className="h-5 w-5 flex-shrink-0 text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-medium">{result.label}</div>
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Badge variant="outline" className="text-xs">
                          {config.label}
                        </Badge>
                        <span>Relevanz: {Math.round(result.score * 100)}%</span>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="p-4 text-center text-sm text-muted-foreground">Keine Ergebnisse gefunden</div>
          )}
        </Card>
      )}
    </div>
  );
}
