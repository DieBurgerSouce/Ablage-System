/**
 * API Playground
 *
 * Interaktiver API-Tester fuer Developer Portal.
 */

import { useState, useMemo } from 'react';
import {
  Play,
  Loader2,
  Copy,
  Check,
  ChevronDown,
  Code2,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { toast } from 'sonner';
import {
  useApiEndpoints,
  useExecutePlayground,
  type ApiEndpoint,
  type PlaygroundResponse,
} from '../hooks/useDeveloperPortal';

const METHOD_COLORS: Record<string, string> = {
  GET: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
  POST: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  PUT: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200',
  PATCH: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
  DELETE: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
};

function getStatusColor(status: number): string {
  if (status >= 200 && status < 300) return 'text-green-600';
  if (status >= 400 && status < 500) return 'text-amber-600';
  return 'text-red-600';
}

export function ApiPlayground() {
  const { endpoints, isLoading } = useApiEndpoints();
  const executeMutation = useExecutePlayground();

  const [selectedEndpoint, setSelectedEndpoint] = useState<ApiEndpoint | null>(null);
  const [pathParams, setPathParams] = useState<Record<string, string>>({});
  const [queryParams, setQueryParams] = useState<Record<string, string>>({});
  const [headers, setHeaders] = useState<Record<string, string>>({});
  const [requestBody, setRequestBody] = useState('');
  const [response, setResponse] = useState<PlaygroundResponse | null>(null);
  const [copied, setCopied] = useState(false);

  // Group endpoints by tag
  const groupedEndpoints = useMemo(() => {
    const groups: Record<string, ApiEndpoint[]> = {};
    for (const endpoint of endpoints) {
      const tag = endpoint.tags[0] || 'other';
      if (!groups[tag]) groups[tag] = [];
      groups[tag].push(endpoint);
    }
    return groups;
  }, [endpoints]);

  const handleSelectEndpoint = (endpoint: ApiEndpoint) => {
    setSelectedEndpoint(endpoint);
    setPathParams({});
    setQueryParams({});
    setHeaders({});
    setRequestBody('');
    setResponse(null);
  };

  const handleExecute = async () => {
    if (!selectedEndpoint) return;

    // Build path with path params
    let path = selectedEndpoint.path;
    for (const [key, value] of Object.entries(pathParams)) {
      path = path.replace(`{${key}}`, value);
    }

    try {
      const result = await executeMutation.mutateAsync({
        method: selectedEndpoint.method,
        path,
        headers,
        query_params: queryParams,
        body: requestBody || undefined,
      });
      setResponse(result);
    } catch (error) {
      toast.error('Anfrage fehlgeschlagen');
    }
  };

  const handleCopyResponse = async () => {
    if (!response) return;
    await navigator.clipboard.writeText(response.body);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Extract path parameters from endpoint path
  const pathParameters = useMemo(() => {
    if (!selectedEndpoint) return [];
    const matches = selectedEndpoint.path.match(/\{(\w+)\}/g);
    return matches?.map((m) => m.slice(1, -1)) || [];
  }, [selectedEndpoint]);

  // Extract query parameters from endpoint definition
  const queryParameters = useMemo(() => {
    if (!selectedEndpoint?.parameters) return [];
    return selectedEndpoint.parameters.filter((p) => p.in === 'query');
  }, [selectedEndpoint]);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-40" />
          <Skeleton className="h-4 w-64 mt-2" />
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      {/* Endpoint List */}
      <Card className="lg:col-span-1">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Code2 className="h-5 w-5" />
            Endpoints
          </CardTitle>
          <CardDescription>{endpoints.length} verfuegbare Endpoints</CardDescription>
        </CardHeader>
        <CardContent className="max-h-[600px] overflow-y-auto">
          <div className="space-y-2">
            {Object.entries(groupedEndpoints).map(([tag, tagEndpoints]) => (
              <Collapsible key={tag} defaultOpen={tag === Object.keys(groupedEndpoints)[0]}>
                <CollapsibleTrigger className="flex w-full items-center justify-between py-2 font-medium hover:underline">
                  <span className="capitalize">{tag}</span>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary">{tagEndpoints.length}</Badge>
                    <ChevronDown className="h-4 w-4" />
                  </div>
                </CollapsibleTrigger>
                <CollapsibleContent className="space-y-1 pl-2">
                  {tagEndpoints.map((endpoint, idx) => (
                    <button
                      key={`${endpoint.method}-${endpoint.path}-${idx}`}
                      onClick={() => handleSelectEndpoint(endpoint)}
                      className={`w-full text-left p-2 rounded-md text-sm hover:bg-accent transition-colors ${
                        selectedEndpoint?.path === endpoint.path &&
                        selectedEndpoint?.method === endpoint.method
                          ? 'bg-accent'
                          : ''
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <Badge className={`text-xs ${METHOD_COLORS[endpoint.method]}`}>
                          {endpoint.method}
                        </Badge>
                        <span className="truncate text-xs font-mono">{endpoint.path}</span>
                      </div>
                      <p className="text-xs text-muted-foreground mt-1 truncate">
                        {endpoint.summary}
                      </p>
                    </button>
                  ))}
                </CollapsibleContent>
              </Collapsible>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Request Builder */}
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>Request Builder</CardTitle>
          <CardDescription>
            {selectedEndpoint
              ? selectedEndpoint.summary
              : 'Waehlen Sie einen Endpoint aus der Liste'}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {selectedEndpoint ? (
            <>
              {/* Endpoint Info */}
              <div className="flex items-center gap-2 p-3 bg-muted rounded-lg">
                <Badge className={METHOD_COLORS[selectedEndpoint.method]}>
                  {selectedEndpoint.method}
                </Badge>
                <code className="text-sm font-mono flex-1">{selectedEndpoint.path}</code>
              </div>

              {/* Path Parameters */}
              {pathParameters.length > 0 && (
                <div className="space-y-2">
                  <Label>Pfad-Parameter</Label>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {pathParameters.map((param) => (
                      <div key={param}>
                        <Label className="text-xs text-muted-foreground">{param}</Label>
                        <Input
                          placeholder={`{${param}}`}
                          value={pathParams[param] || ''}
                          onChange={(e) =>
                            setPathParams((prev) => ({ ...prev, [param]: e.target.value }))
                          }
                        />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Query Parameters */}
              {queryParameters.length > 0 && (
                <div className="space-y-2">
                  <Label>Query-Parameter</Label>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {queryParameters.map((param) => (
                      <div key={param.name}>
                        <Label className="text-xs text-muted-foreground">
                          {param.name}
                          {param.required && <span className="text-red-500 ml-1">*</span>}
                        </Label>
                        <Input
                          placeholder={param.description || param.name}
                          value={queryParams[param.name] || ''}
                          onChange={(e) =>
                            setQueryParams((prev) => ({ ...prev, [param.name]: e.target.value }))
                          }
                        />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Request Body */}
              {selectedEndpoint.request_body && (
                <div className="space-y-2">
                  <Label>Request Body (JSON)</Label>
                  <Textarea
                    className="font-mono text-sm min-h-[120px]"
                    placeholder='{"key": "value"}'
                    value={requestBody}
                    onChange={(e) => setRequestBody(e.target.value)}
                  />
                </div>
              )}

              {/* Execute Button */}
              <Button
                onClick={handleExecute}
                disabled={executeMutation.isPending}
                className="w-full"
              >
                {executeMutation.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Ausfuehren...
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4 mr-2" />
                    Anfrage senden
                  </>
                )}
              </Button>

              {/* Response */}
              {response && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label>Response</Label>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className={getStatusColor(response.status_code)}>
                        {response.status_code}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        {response.duration_ms} ms
                      </span>
                      <Button size="sm" variant="ghost" onClick={handleCopyResponse}>
                        {copied ? (
                          <Check className="h-4 w-4" />
                        ) : (
                          <Copy className="h-4 w-4" />
                        )}
                      </Button>
                    </div>
                  </div>
                  <pre className="p-4 bg-muted rounded-lg overflow-auto max-h-[300px] text-xs font-mono">
                    {response.body}
                  </pre>
                </div>
              )}
            </>
          ) : (
            <div className="text-center py-12 text-muted-foreground">
              <Code2 className="h-12 w-12 mx-auto mb-4 opacity-20" />
              <p>Waehlen Sie einen Endpoint aus der Liste</p>
              <p className="text-sm mt-1">
                um Anfragen zu testen und Responses zu pruefen
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
