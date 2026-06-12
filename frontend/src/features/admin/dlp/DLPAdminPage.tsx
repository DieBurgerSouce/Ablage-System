/**
 * DLP Admin Page
 *
 * Hauptseite für die Verwaltung von DLP-Policies.
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Shield, Plus, Search, Settings, FileWarning, Lock, Eye } from 'lucide-react';
import { PolicyTable, PolicyFormDialog, SensitiveDataScanner } from './components';
import { useDLPPolicies } from './hooks/use-dlp';
import type { DLPPolicy } from './api/dlp-api';

export function DLPAdminPage() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingPolicy, setEditingPolicy] = useState<DLPPolicy | null>(null);

  const { data, isLoading } = useDLPPolicies();

  const handleEdit = (policy: DLPPolicy) => {
    setEditingPolicy(policy);
    setDialogOpen(true);
  };

  const handleCreate = () => {
    setEditingPolicy(null);
    setDialogOpen(true);
  };

  const handleDialogClose = (open: boolean) => {
    setDialogOpen(open);
    if (!open) {
      setEditingPolicy(null);
    }
  };

  // Stats
  const policies = data?.policies ?? [];
  const activeCount = policies.filter((p) => p.enabled).length;
  const blockingCount = policies.filter((p) => p.action === 'block').length;
  const watermarkCount = policies.filter((p) => p.require_watermark || p.action === 'watermark').length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Shield className="h-6 w-6" />
            Data Loss Prevention
          </h1>
          <p className="text-muted-foreground">
            Schützen Sie sensible Dokumente durch Zugriffskontrollen und Wasserzeichen.
          </p>
        </div>

        <Button onClick={handleCreate}>
          <Plus className="h-4 w-4 mr-2" />
          Neue Policy
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Policies gesamt
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <Settings className="h-4 w-4 text-muted-foreground" />
              <span className="text-2xl font-bold">{policies.length}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Aktive Policies
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <Eye className="h-4 w-4 text-green-500" />
              <span className="text-2xl font-bold">{activeCount}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Blockierend
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <Lock className="h-4 w-4 text-red-500" />
              <span className="text-2xl font-bold">{blockingCount}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Mit Wasserzeichen
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <FileWarning className="h-4 w-4 text-blue-500" />
              <span className="text-2xl font-bold">{watermarkCount}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="policies" className="space-y-4">
        <TabsList>
          <TabsTrigger value="policies" className="gap-2">
            <Shield className="h-4 w-4" />
            Policies
          </TabsTrigger>
          <TabsTrigger value="scanner" className="gap-2">
            <Search className="h-4 w-4" />
            Scanner
          </TabsTrigger>
        </TabsList>

        {/* Policies Tab */}
        <TabsContent value="policies">
          <Card>
            <CardHeader>
              <CardTitle>DLP-Policies</CardTitle>
              <CardDescription>
                Verwalten Sie Regeln für den Zugriff auf sensible Dokumente.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <PolicyTable
                policies={policies}
                isLoading={isLoading}
                onEdit={handleEdit}
              />
            </CardContent>
          </Card>
        </TabsContent>

        {/* Scanner Tab */}
        <TabsContent value="scanner">
          <SensitiveDataScanner />
        </TabsContent>
      </Tabs>

      {/* Policy Form Dialog */}
      <PolicyFormDialog
        open={dialogOpen}
        onOpenChange={handleDialogClose}
        policy={editingPolicy}
      />
    </div>
  );
}
