/**
 * Scan Route - Mobile Document Scanning
 *
 * Provides camera-based document capture for mobile devices
 * with post-capture OCR results and entity assignment flow.
 *
 * Features:
 * - Camera access and capture
 * - Gallery image selection
 * - Offline queue support
 * - Folder selection
 * - OCR result display after upload
 * - Quick entity assignment
 *
 * State Machine: idle -> scanning -> processing -> result -> assigning
 *
 * Phase 3.1 + 3.2 der Feature-Roadmap (Januar-Februar 2026)
 */

import { useState } from 'react';
import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { ArrowLeft, Wifi, WifiOff, Cloud, CloudOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { CameraScan, ScanResultPanel, QuickAssignSheet } from '@/features/mobile';
import { useScanFlow } from '@/features/mobile/hooks/use-scan-flow';
import { usePWA } from '@/context/PWAContext';
import { useQuery } from '@tanstack/react-query';
import { cn } from '@/lib/utils';

// Route definition
export const Route = createFileRoute('/scan')({
  component: ScanPage,
});

// Folder API call
async function fetchFolders(): Promise<Array<{ id: string; name: string; path: string }>> {
  const response = await fetch('/api/v1/folders', { credentials: 'include' });
  if (!response.ok) return [];
  return response.json();
}

function ScanPage() {
  const navigate = useNavigate();
  const { isOnline, isInstalled, displayMode } = usePWA();
  const [selectedFolderId, setSelectedFolderId] = useState<string | undefined>();

  // Scan flow state machine
  const {
    phase,
    documentId,
    ocrResult,
    suggestions,
    isAssigning,
    startScan,
    onUploadComplete,
    startAssigning,
    assignToEntity,
    scanAnother,
    finish,
    cancelAssigning,
    loadSuggestions,
  } = useScanFlow();

  // Fetch available folders
  const { data: folders = [] } = useQuery({
    queryKey: ['folders'],
    queryFn: fetchFolders,
    staleTime: 5 * 60 * 1000,
  });

  // Handle successful upload -> transition to processing phase
  const handleUploadSuccess = (newDocumentId: string) => {
    onUploadComplete(newDocumentId);
  };

  // Handle cancel
  const handleCancel = () => {
    navigate({ to: '/' });
  };

  // Handle assign button from result panel
  const handleStartAssign = () => {
    startAssigning();
  };

  // Determine if running as PWA
  const isPWA = displayMode === 'standalone' || displayMode === 'fullscreen';

  // Show folder selection only in idle/scanning phases
  const showFolderSelection =
    folders.length > 0 && (phase === 'idle' || phase === 'scanning');

  // Show camera in idle/scanning phases
  const showCamera = phase === 'idle' || phase === 'scanning';

  // Show result panel in processing/result phases
  const showResultPanel =
    (phase === 'processing' || phase === 'result') && documentId !== null;

  return (
    <div className={cn(
      'min-h-screen bg-background',
      isPWA && 'pt-safe-top pb-safe-bottom'
    )}>
      {/* Header */}
      <header className="sticky top-0 z-50 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 border-b">
        <div className="container flex h-14 items-center gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate({ to: '/' })}
          >
            <ArrowLeft className="h-5 w-5" />
          </Button>

          <div className="flex-1">
            <h1 className="text-lg font-semibold">Dokument scannen</h1>
          </div>

          {/* Online Status Badge */}
          <Badge
            variant={isOnline ? 'default' : 'destructive'}
            className="gap-1"
          >
            {isOnline ? (
              <>
                <Wifi className="h-3 w-3" />
                Online
              </>
            ) : (
              <>
                <WifiOff className="h-3 w-3" />
                Offline
              </>
            )}
          </Badge>
        </div>
      </header>

      {/* Main Content */}
      <main className="container py-4 space-y-4">
        {/* Offline Info Card */}
        {!isOnline && (
          <Card className="border-amber-500/50 bg-amber-500/10">
            <CardContent className="pt-4">
              <div className="flex items-start gap-3">
                <CloudOff className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
                <div>
                  <p className="font-medium text-amber-500">Offline-Modus</p>
                  <p className="text-sm text-muted-foreground">
                    Dokumente werden lokal gespeichert und hochgeladen, sobald Sie wieder online sind.
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Folder Selection (only during idle/scanning) */}
        {showFolderSelection && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Zielordner</CardTitle>
              <CardDescription>
                Waehlen Sie einen Ordner fuer das Dokument
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Select
                value={selectedFolderId || 'none'}
                onValueChange={(value) => setSelectedFolderId(value === 'none' ? undefined : value)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Ordner auswaehlen (optional)" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Kein Ordner (Posteingang)</SelectItem>
                  {folders.map((folder) => (
                    <SelectItem key={folder.id} value={folder.id}>
                      {folder.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </CardContent>
          </Card>
        )}

        {/* Camera Scan Component (idle/scanning phases) */}
        {showCamera && (
          <CameraScan
            folderId={selectedFolderId}
            onUploadSuccess={handleUploadSuccess}
            onCancel={handleCancel}
          />
        )}

        {/* OCR Result Panel (processing/result phases) */}
        {showResultPanel && (
          <ScanResultPanel
            documentId={documentId}
            phase={phase as 'processing' | 'result'}
            ocrResult={ocrResult}
            onAssign={handleStartAssign}
            onComplete={finish}
            onScanAnother={scanAnother}
          />
        )}

        {/* PWA Install Prompt (if not installed) */}
        {!isInstalled && !isPWA && phase === 'idle' && (
          <Card className="border-primary/50">
            <CardContent className="pt-4">
              <div className="flex items-start gap-3">
                <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                  <Cloud className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <p className="font-medium">Als App installieren</p>
                  <p className="text-sm text-muted-foreground">
                    Installieren Sie die App fuer schnelleren Zugriff und Offline-Unterstuetzung.
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </main>

      {/* Quick Assign Bottom Sheet */}
      <QuickAssignSheet
        open={phase === 'assigning'}
        onOpenChange={(open) => {
          if (!open) cancelAssigning();
        }}
        onAssign={assignToEntity}
        suggestions={suggestions}
        onSearch={loadSuggestions}
        ocrResult={ocrResult}
        isAssigning={isAssigning}
      />
    </div>
  );
}

export default ScanPage;
