/**
 * Developer Portal Page
 *
 * Hauptseite für Entwickler-Ressourcen:
 * - API Playground
 * - Webhook-Verwaltung
 * - SDK-Downloads
 * - Integrations-Anleitungen
 */

import { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Code2, Webhook, Download, BookOpen, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  ApiStatsCards,
  ApiPlayground,
  WebhookTester,
  SdkDownloads,
  IntegrationGuides,
} from './components';

export function DeveloperPortalPage() {
  const [activeTab, setActiveTab] = useState('playground');

  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-primary/10 rounded-lg">
            <Code2 className="h-8 w-8 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">Developer Portal</h1>
            <p className="text-muted-foreground">
              API-Dokumentation, SDKs und Integrations-Ressourcen
            </p>
          </div>
        </div>
        <Button variant="outline" asChild>
          <a href="/docs" target="_blank" rel="noopener noreferrer">
            <BookOpen className="h-4 w-4 mr-2" />
            API-Docs
            <ExternalLink className="h-3 w-3 ml-2" />
          </a>
        </Button>
      </div>

      {/* API Stats */}
      <ApiStatsCards />

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="playground" className="gap-2">
            <Code2 className="h-4 w-4" />
            API Playground
          </TabsTrigger>
          <TabsTrigger value="webhooks" className="gap-2">
            <Webhook className="h-4 w-4" />
            Webhooks
          </TabsTrigger>
          <TabsTrigger value="sdks" className="gap-2">
            <Download className="h-4 w-4" />
            SDKs
          </TabsTrigger>
          <TabsTrigger value="guides" className="gap-2">
            <BookOpen className="h-4 w-4" />
            Anleitungen
          </TabsTrigger>
        </TabsList>

        <TabsContent value="playground" className="mt-6">
          <ApiPlayground />
        </TabsContent>

        <TabsContent value="webhooks" className="mt-6">
          <WebhookTester />
        </TabsContent>

        <TabsContent value="sdks" className="mt-6">
          <SdkDownloads />
        </TabsContent>

        <TabsContent value="guides" className="mt-6">
          <IntegrationGuides />
        </TabsContent>
      </Tabs>
    </div>
  );
}
