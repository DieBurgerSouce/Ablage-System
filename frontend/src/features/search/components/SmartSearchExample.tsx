/**
 * SmartSearchExample - Usage Examples for Smart Search
 *
 * Zeigt verschiedene Anwendungsfälle der Smart Search Komponente.
 */

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { SmartSearchBar } from './SmartSearchBar';
import { useSmartSearch } from '../hooks/useSmartSearch';
import { Code2 } from 'lucide-react';
import type { SmartSearchFilters } from '../api/smart-search-api';

// ==================== Example 1: Basic Usage ====================

export function BasicSmartSearchExample() {
    return (
        <div className="space-y-4">
            <h2 className="text-lg font-semibold">Basis-Verwendung</h2>
            <SmartSearchBar
                onResultClick={(docId) => console.log('Document clicked:', docId)}
            />
        </div>
    );
}

// ==================== Example 2: With Initial Filters ====================

export function FilteredSmartSearchExample() {
    const initialFilters: SmartSearchFilters = {
        document_types: ['invoice', 'order'],
        status: ['pending'],
    };

    return (
        <div className="space-y-4">
            <h2 className="text-lg font-semibold">Mit Initial-Filtern</h2>
            <SmartSearchBar
                initialFilters={initialFilters}
                onResultClick={(docId) => console.log('Document clicked:', docId)}
            />
        </div>
    );
}

// ==================== Example 3: Custom Hook Usage ====================

export function CustomHookExample() {
    const [query, setQuery] = useState('');
    const [filters, setFilters] = useState<SmartSearchFilters>({});

    const { data, isLoading, error } = useSmartSearch({
        query,
        filters,
        enabled: query.length >= 2,
    });

    return (
        <div className="space-y-4">
            <h2 className="text-lg font-semibold">Custom Hook Verwendung</h2>
            <div className="space-y-2">
                <input
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Suche eingeben..."
                    className="w-full p-2 border rounded"
                />

                {isLoading && <p className="text-sm text-muted-foreground">Lädt...</p>}
                {error && <p className="text-sm text-destructive">Fehler: {error.message}</p>}

                {data && (
                    <div className="space-y-2">
                        <div className="flex items-center gap-2">
                            <Badge>{data.search_mode}</Badge>
                            <span className="text-sm text-muted-foreground">
                                {data.total} Ergebnisse in {data.search_time_ms}ms
                            </span>
                        </div>

                        {data.interpretation && (
                            <Card>
                                <CardContent className="pt-4">
                                    <p className="text-sm font-medium">
                                        {data.interpretation.interpreted_as}
                                    </p>
                                </CardContent>
                            </Card>
                        )}

                        <div className="space-y-2">
                            {data.results.map((result) => (
                                <Card key={result.document_id}>
                                    <CardContent className="pt-4">
                                        <p className="font-medium">{result.filename}</p>
                                        <p className="text-sm text-muted-foreground">
                                            Relevanz: {Math.round(result.relevance_score * 100)}%
                                        </p>
                                    </CardContent>
                                </Card>
                            ))}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

// ==================== Example 4: All Examples in Tabs ====================

export function SmartSearchExamples() {
    return (
        <div className="container mx-auto py-8 space-y-8">
            <div className="text-center space-y-2">
                <h1 className="text-3xl font-bold">Smart Search Beispiele</h1>
                <p className="text-muted-foreground">
                    Verschiedene Verwendungsmöglichkeiten der Smart Search
                </p>
            </div>

            <Tabs defaultValue="basic" className="w-full">
                <TabsList className="grid w-full grid-cols-3">
                    <TabsTrigger value="basic">Basis</TabsTrigger>
                    <TabsTrigger value="filtered">Mit Filtern</TabsTrigger>
                    <TabsTrigger value="custom">Custom Hook</TabsTrigger>
                </TabsList>

                <TabsContent value="basic" className="space-y-4">
                    <BasicSmartSearchExample />
                    <CodeExample code={basicUsageCode} />
                </TabsContent>

                <TabsContent value="filtered" className="space-y-4">
                    <FilteredSmartSearchExample />
                    <CodeExample code={filteredUsageCode} />
                </TabsContent>

                <TabsContent value="custom" className="space-y-4">
                    <CustomHookExample />
                    <CodeExample code={customHookCode} />
                </TabsContent>
            </Tabs>
        </div>
    );
}

// ==================== Code Example Component ====================

function CodeExample({ code }: { code: string }) {
    return (
        <Card>
            <CardHeader>
                <CardTitle className="text-sm flex items-center gap-2">
                    <Code2 className="w-4 h-4" />
                    Code-Beispiel
                </CardTitle>
            </CardHeader>
            <CardContent>
                <pre className="text-xs bg-muted p-4 rounded overflow-x-auto">
                    <code>{code}</code>
                </pre>
            </CardContent>
        </Card>
    );
}

// ==================== Code Snippets ====================

const basicUsageCode = `import { SmartSearchBar } from '@/features/search/components/SmartSearchBar';

function MyComponent() {
  return (
    <SmartSearchBar
      onResultClick={(docId) => console.log('Document clicked:', docId)}
    />
  );
}`;

const filteredUsageCode = `import { SmartSearchBar } from '@/features/search/components/SmartSearchBar';
import type { SmartSearchFilters } from '@/features/search/api/smart-search-api';

function MyComponent() {
  const initialFilters: SmartSearchFilters = {
    document_types: ['invoice', 'order'],
    status: ['pending'],
  };

  return (
    <SmartSearchBar
      initialFilters={initialFilters}
      onResultClick={(docId) => navigate(\`/documents/\${docId}\`)}
    />
  );
}`;

const customHookCode = `import { useSmartSearch } from '@/features/search/hooks/useSmartSearch';
import type { SmartSearchFilters } from '@/features/search/api/smart-search-api';

function MyComponent() {
  const [query, setQuery] = useState('');
  const [filters, setFilters] = useState<SmartSearchFilters>({});

  const { data, isLoading, error } = useSmartSearch({
    query,
    filters,
    enabled: query.length >= 2,
  });

  return (
    <div>
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Suche..."
      />

      {data && (
        <div>
          <p>{data.interpretation.interpreted_as}</p>
          <p>Modus: {data.search_mode}</p>
          <p>{data.total} Ergebnisse</p>
          {data.results.map((result) => (
            <div key={result.document_id}>
              {result.filename} - {result.relevance_score}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}`;

export default SmartSearchExamples;
