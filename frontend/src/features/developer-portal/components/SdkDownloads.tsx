/**
 * SDK Downloads
 *
 * Zeigt verfügbare SDKs und Installationsanleitungen.
 */

import { useState } from 'react';
import { logger } from '@/lib/logger';
import {
  Download,
  Copy,
  Check,
  ExternalLink,
  Code,
  Terminal,
  BookOpen,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import { useSdks, type SdkInfo } from '../hooks/useDeveloperPortal';

// Language icons/colors
const LANGUAGE_CONFIG: Record<string, { color: string; bgColor: string }> = {
  Python: {
    color: 'text-blue-600',
    bgColor: 'bg-blue-100 dark:bg-blue-900',
  },
  'JavaScript/TypeScript': {
    color: 'text-yellow-600',
    bgColor: 'bg-yellow-100 dark:bg-yellow-900',
  },
};

function SdkCard({ sdk }: { sdk: SdkInfo }) {
  const [copied, setCopied] = useState<'install' | 'code' | null>(null);

  const config = LANGUAGE_CONFIG[sdk.language] || {
    color: 'text-gray-600',
    bgColor: 'bg-gray-100 dark:bg-gray-900',
  };

  const handleCopy = async (text: string, type: 'install' | 'code') => {
    await navigator.clipboard.writeText(text);
    setCopied(type);
    toast.success('In Zwischenablage kopiert');
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <div className={`p-2 rounded-lg ${config.bgColor}`}>
                <Code className={`h-5 w-5 ${config.color}`} />
              </div>
              {sdk.name}
            </CardTitle>
            <CardDescription className="mt-2">{sdk.description}</CardDescription>
          </div>
          <Badge variant="outline">v{sdk.version}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Installation */}
        {sdk.install_command && (
          <div className="space-y-2">
            <label className="text-sm font-medium flex items-center gap-2">
              <Terminal className="h-4 w-4" />
              Installation
            </label>
            <div className="flex items-center gap-2">
              <code className="flex-1 p-3 bg-muted rounded-lg font-mono text-sm">
                {sdk.install_command}
              </code>
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleCopy(sdk.install_command!, 'install')}
              >
                {copied === 'install' ? (
                  <Check className="h-4 w-4" />
                ) : (
                  <Copy className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>
        )}

        {/* Example Code */}
        {sdk.example_code && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium flex items-center gap-2">
                <Code className="h-4 w-4" />
                Beispiel
              </label>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => handleCopy(sdk.example_code!, 'code')}
              >
                {copied === 'code' ? (
                  <Check className="h-4 w-4" />
                ) : (
                  <Copy className="h-4 w-4" />
                )}
              </Button>
            </div>
            <pre className="p-4 bg-muted rounded-lg overflow-x-auto text-xs font-mono">
              {sdk.example_code}
            </pre>
          </div>
        )}

        {/* Links */}
        <div className="flex gap-2 pt-2">
          <Button variant="outline" size="sm" asChild>
            <a href={sdk.download_url} target="_blank" rel="noopener noreferrer">
              <Download className="h-4 w-4 mr-2" />
              Herunterladen
              <ExternalLink className="h-3 w-3 ml-1" />
            </a>
          </Button>
          <Button variant="outline" size="sm" asChild>
            <a href={sdk.documentation_url} target="_blank" rel="noopener noreferrer">
              <BookOpen className="h-4 w-4 mr-2" />
              Dokumentation
              <ExternalLink className="h-3 w-3 ml-1" />
            </a>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export function SdkDownloads() {
  const { data: sdks, isLoading } = useSdks();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <div className="grid gap-4 md:grid-cols-2">
          {Array.from({ length: 2 }).map((_, i) => (
            <Skeleton key={i} className="h-64" />
          ))}
        </div>
      </div>
    );
  }

  if (!sdks || sdks.length === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <Download className="h-12 w-12 mx-auto mb-4 opacity-20" />
          <p className="text-muted-foreground">Keine SDKs verfügbar</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold">SDKs & Bibliotheken</h3>
        <p className="text-sm text-muted-foreground">
          Offizielle SDKs für die Integration in Ihre Anwendungen
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {sdks.map((sdk) => (
          <SdkCard key={sdk.name} sdk={sdk} />
        ))}
      </div>

      {/* Quick Start Section */}
      <Card>
        <CardHeader>
          <CardTitle>Schnellstart</CardTitle>
          <CardDescription>
            Wählen Sie Ihre bevorzugte Programmiersprache
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="python">
            <TabsList>
              <TabsTrigger value="python">Python</TabsTrigger>
              <TabsTrigger value="javascript">JavaScript</TabsTrigger>
              <TabsTrigger value="curl">cURL</TabsTrigger>
            </TabsList>

            <TabsContent value="python" className="mt-4">
              <pre className="p-4 bg-muted rounded-lg overflow-x-auto text-sm font-mono">
{`# Installation
pip install ablage-sdk

# Authentifizierung
from ablage import AblageClient

client = AblageClient(
    base_url="https://api.ablage-system.de",
    api_key="your-api-key"
)

# Dokument hochladen und OCR starten
doc = client.documents.upload("rechnung.pdf")
result = client.ocr.process(doc.id, backend="auto")

# Extrahierte Daten abrufen
print(f"Lieferant: {result.extracted_data.supplier}")
print(f"Betrag: {result.extracted_data.amount} EUR")`}
              </pre>
            </TabsContent>

            <TabsContent value="javascript" className="mt-4">
              <pre className="p-4 bg-muted rounded-lg overflow-x-auto text-sm font-mono">
{`// Installation
npm install @ablage/sdk

// Authentifizierung
import { AblageClient } from '@ablage/sdk';

const client = new AblageClient({
  baseUrl: 'https://api.ablage-system.de',
  apiKey: 'your-api-key'
});

// Dokument hochladen und OCR starten
const doc = await client.documents.upload(file);
const result = await client.ocr.process(doc.id, { backend: 'auto' });

// Extrahierte Daten abrufen
logger.info('Lieferant:', result.extractedData.supplier);
logger.info('Betrag:', result.extractedData.amount, 'EUR');`}
              </pre>
            </TabsContent>

            <TabsContent value="curl" className="mt-4">
              <pre className="p-4 bg-muted rounded-lg overflow-x-auto text-sm font-mono">
{`# Dokument hochladen
curl -X POST https://api.ablage-system.de/api/v1/documents \\
  -H "Authorization: Bearer your-api-key" \\
  -F "file=@rechnung.pdf"

# OCR starten
curl -X POST https://api.ablage-system.de/api/v1/ocr/process \\
  -H "Authorization: Bearer your-api-key" \\
  -H "Content-Type: application/json" \\
  -d '{"document_id": "doc-id", "backend": "auto"}'

# Status prüfen
curl https://api.ablage-system.de/api/v1/ocr/status/job-id \\
  -H "Authorization: Bearer your-api-key"`}
              </pre>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
