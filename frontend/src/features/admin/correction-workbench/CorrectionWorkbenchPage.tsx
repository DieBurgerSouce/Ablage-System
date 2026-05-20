/**
 * Correction Workbench Page
 * Hauptseite für die OCR-Korrektur-Workbench
 *
 * Features:
 * - Queue mit Dokumenten niedriger Confidence
 * - Side-by-Side Korrektur-Panel
 * - Training-Daten Export
 * - Statistik-Dashboard
 */

import { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  CorrectionStatsCards,
  LowConfidenceQueue,
  BatchCorrectionPanel,
  TrainingDataExport,
} from './components';
import type { LowConfidenceDocument } from './types';

export function CorrectionWorkbenchPage() {
  const [selectedDocument, setSelectedDocument] = useState<LowConfidenceDocument | null>(null);
  const [activeTab, setActiveTab] = useState('queue');

  const handleDocumentSelect = (doc: LowConfidenceDocument) => {
    setSelectedDocument(doc);
    // Switch to correction tab when document is selected
    if (activeTab === 'export') {
      setActiveTab('queue');
    }
  };

  const handleCorrectionComplete = () => {
    setSelectedDocument(null);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex-shrink-0 p-6 border-b">
        <h1 className="text-2xl font-bold tracking-tight">
          OCR-Korrektur Workbench
        </h1>
        <p className="text-muted-foreground mt-1">
          Korrigieren Sie OCR-Ergebnisse und exportieren Sie Training-Daten
        </p>
      </div>

      {/* Stats Cards */}
      <div className="flex-shrink-0 p-6 border-b bg-muted/30">
        <CorrectionStatsCards />
      </div>

      {/* Main Content */}
      <div className="flex-1 min-h-0 p-6">
        <Tabs
          value={activeTab}
          onValueChange={setActiveTab}
          className="h-full flex flex-col"
        >
          <TabsList className="grid w-full max-w-md grid-cols-2">
            <TabsTrigger value="queue">Korrektur-Queue</TabsTrigger>
            <TabsTrigger value="export">Training Export</TabsTrigger>
          </TabsList>

          <TabsContent value="queue" className="flex-1 mt-4">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 h-full">
              {/* Left: Queue */}
              <div className="h-[600px] lg:h-full">
                <LowConfidenceQueue
                  onSelectDocument={handleDocumentSelect}
                  selectedDocumentId={selectedDocument?.id}
                />
              </div>

              {/* Right: Correction Panel */}
              <div className="h-[600px] lg:h-full">
                <BatchCorrectionPanel
                  document={selectedDocument}
                  onCorrectionComplete={handleCorrectionComplete}
                />
              </div>
            </div>
          </TabsContent>

          <TabsContent value="export" className="flex-1 mt-4">
            <div className="h-[600px] lg:h-full max-w-2xl">
              <TrainingDataExport />
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
