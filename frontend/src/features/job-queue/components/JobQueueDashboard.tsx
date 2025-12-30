/**
 * Job Queue Dashboard
 *
 * Enterprise-Level Job Queue Management Dashboard.
 * 5 Tabs: Übersicht, Aktive Jobs, Historie, Queue-Status, System Health
 */

import { useState } from 'react';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bell,
  CheckCircle2,
  Clock,
  Cpu,
  ListOrdered,
  RefreshCw,
  Server,
  Settings,
  Wifi,
  WifiOff,
  Zap,
} from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

import { useJobStats, useActiveJobs, useDLQStats } from '../hooks/use-jobs-query';
import { useJobWebSocket } from '../hooks/use-job-websocket';
import { useJobPermissions } from '../hooks/use-job-permissions';

import { OverviewTab } from './tabs/OverviewTab';
import { ActiveJobsTab } from './tabs/ActiveJobsTab';
import { JobHistoryTab } from './tabs/JobHistoryTab';
import { QueueStatusTab } from './tabs/QueueStatusTab';
import { SystemHealthTab } from './tabs/SystemHealthTab';
import { JobSettingsModal } from './modals/JobSettingsModal';

export function JobQueueDashboard() {
  const [activeTab, setActiveTab] = useState('overview');
  const [settingsOpen, setSettingsOpen] = useState(false);

  const permissions = useJobPermissions();

  // Queries für Tab-Badges
  const { data: stats } = useJobStats();
  const { data: activeJobsData } = useActiveJobs();
  const { data: dlqStats } = useDLQStats();

  // WebSocket für Live-Updates
  const { isConnected, isPolling, lastUpdate, reconnect } = useJobWebSocket({
    enabled: permissions.canView,
    onJobCompleted: (jobId) => {
      // Toast wird bereits im Mutation Hook gezeigt
    },
    onJobFailed: (jobId, error) => {
      // Toast wird bereits im Mutation Hook gezeigt
    },
  });

  // Berechne Badges
  const activeJobsCount = stats?.activeJobs ?? 0;
  const queuedJobsCount = stats?.queuedJobs ?? 0;
  const dlqCount = dlqStats?.totalTasks ?? 0;
  const hasWarnings =
    dlqCount > 0 || (stats?.successRate24h !== undefined && stats.successRate24h < 90);

  return (
    <TooltipProvider>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold">Job Queue Management</h1>
            <p className="text-muted-foreground">
              Verwaltung aller Hintergrund-Tasks und Systemressourcen
            </p>
          </div>

          <div className="flex items-center gap-3">
            {/* Connection Status */}
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="flex items-center gap-2">
                  {isConnected ? (
                    <Badge variant="outline" className="gap-1 text-green-600 border-green-600">
                      <Wifi className="h-3 w-3" />
                      Live
                    </Badge>
                  ) : isPolling ? (
                    <Badge variant="outline" className="gap-1 text-yellow-600 border-yellow-600">
                      <RefreshCw className="h-3 w-3 animate-spin" />
                      Polling
                    </Badge>
                  ) : (
                    <Badge
                      variant="outline"
                      className="gap-1 text-red-600 border-red-600 cursor-pointer"
                      onClick={reconnect}
                    >
                      <WifiOff className="h-3 w-3" />
                      Offline
                    </Badge>
                  )}
                </div>
              </TooltipTrigger>
              <TooltipContent>
                {isConnected
                  ? 'WebSocket verbunden - Live Updates'
                  : isPolling
                    ? 'WebSocket nicht verfügbar - Polling aktiv (10s)'
                    : 'Verbindung unterbrochen - Klicken zum Neuverbinden'}
                {lastUpdate && (
                  <div className="text-xs text-muted-foreground mt-1">
                    Letzte Aktualisierung:{' '}
                    {lastUpdate.toLocaleTimeString('de-DE', {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })}
                  </div>
                )}
              </TooltipContent>
            </Tooltip>

            {/* Settings Button */}
            {permissions.canConfigureNotifications && (
              <Button
                variant="outline"
                size="sm"
                className="gap-2"
                onClick={() => setSettingsOpen(true)}
              >
                <Bell className="h-4 w-4" />
                Benachrichtigungen
              </Button>
            )}
          </div>
        </div>

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
          <TabsList className="grid w-full grid-cols-5">
            <TabsTrigger value="overview" className="gap-2">
              <BarChart3 className="h-4 w-4" />
              Übersicht
            </TabsTrigger>

            <TabsTrigger value="active" className="gap-2">
              <Zap className="h-4 w-4" />
              Aktive Jobs
              {activeJobsCount > 0 && (
                <Badge variant="secondary" className="ml-1 h-5 px-1.5">
                  {activeJobsCount}
                </Badge>
              )}
            </TabsTrigger>

            <TabsTrigger value="history" className="gap-2">
              <Clock className="h-4 w-4" />
              Historie
            </TabsTrigger>

            <TabsTrigger value="queues" className="gap-2">
              <ListOrdered className="h-4 w-4" />
              Queue-Status
              {queuedJobsCount > 10 && (
                <Badge variant="secondary" className="ml-1 h-5 px-1.5">
                  {queuedJobsCount}
                </Badge>
              )}
            </TabsTrigger>

            <TabsTrigger value="health" className="gap-2">
              <Server className="h-4 w-4" />
              System Health
              {hasWarnings && (
                <Badge variant="destructive" className="ml-1 h-5 w-5 p-0 justify-center">
                  !
                </Badge>
              )}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-4">
            <OverviewTab />
          </TabsContent>

          <TabsContent value="active" className="space-y-4">
            <ActiveJobsTab />
          </TabsContent>

          <TabsContent value="history" className="space-y-4">
            <JobHistoryTab />
          </TabsContent>

          <TabsContent value="queues" className="space-y-4">
            <QueueStatusTab />
          </TabsContent>

          <TabsContent value="health" className="space-y-4">
            <SystemHealthTab />
          </TabsContent>
        </Tabs>

        {/* Settings Modal */}
        <JobSettingsModal open={settingsOpen} onOpenChange={setSettingsOpen} />
      </div>
    </TooltipProvider>
  );
}

export default JobQueueDashboard;
