/**
 * ImportsPage - Haupt-Übersicht für alle Import-Konfigurationen
 *
 * Zeigt Email- und Ordner-Konfigurationen sowie Import-Statistiken.
 */

import { useState } from 'react';
import {
  Mail,
  FolderOpen,
  FileText,
  Settings,
  TrendingUp,
  Clock,
  CheckCircle,
  AlertTriangle,
  Loader2,
  TestTube2,
} from 'lucide-react';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ErrorBoundary } from '@/components/ErrorBoundary';

import { EmailConfigList } from '../components/EmailConfigList';
import { EmailConfigForm } from '../components/EmailConfigForm';
import { FolderConfigList } from '../components/FolderConfigList';
import { FolderConfigForm } from '../components/FolderConfigForm';
import { ImportLogTable } from '../components/ImportLogTable';
import { ImportRuleBuilder } from '../components/ImportRuleBuilder';
import { RuleTestingPanel } from '../components/RuleTestingPanel';
import { useImportStats, useImportRules } from '../hooks/use-import-queries';

// ==================== Stats Cards ====================

function ImportStatsCards() {
  const { data: stats, isLoading } = useImportStats();

  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-4">
        {[...Array(4)].map((_, i) => (
          <Card key={i}>
            <CardContent className="flex items-center justify-center py-6">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  const statsData = [
    {
      title: 'Heute importiert',
      value: stats?.documentsImportedToday ?? 0,
      icon: CheckCircle,
      color: 'text-green-600',
      bgColor: 'bg-green-100 dark:bg-green-900/30',
    },
    {
      title: 'Diese Woche',
      value: stats?.documentsImportedThisWeek ?? 0,
      icon: TrendingUp,
      color: 'text-blue-600',
      bgColor: 'bg-blue-100 dark:bg-blue-900/30',
    },
    {
      title: 'Ausstehend',
      value: stats?.pendingImports ?? 0,
      icon: Clock,
      color: 'text-yellow-600',
      bgColor: 'bg-yellow-100 dark:bg-yellow-900/30',
    },
    {
      title: 'Fehler (24h)',
      value: stats?.failedImportsLast24h ?? 0,
      icon: AlertTriangle,
      color: 'text-red-600',
      bgColor: 'bg-red-100 dark:bg-red-900/30',
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-4">
      {statsData.map((stat) => {
        const Icon = stat.icon;
        return (
          <Card key={stat.title}>
            <CardContent className="flex items-center gap-4 p-6">
              <div className={`rounded-lg p-3 ${stat.bgColor}`}>
                <Icon className={`h-6 w-6 ${stat.color}`} />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">{stat.title}</p>
                <p className="text-2xl font-bold">{stat.value.toLocaleString('de-DE')}</p>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

// ==================== Rules List ====================

function ImportRulesList({ onEdit }: { onEdit: (ruleId: string) => void }) {
  const { data: rules, isLoading } = useImportRules();

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (!rules || rules.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-12">
          <Settings className="h-12 w-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-medium mb-2">Keine Import-Regeln</h3>
          <p className="text-muted-foreground text-center">
            Erstellen Sie Regeln, um Importe automatisch zu kategorisieren.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Settings className="h-5 w-5" />
          Aktive Import-Regeln
        </CardTitle>
        <CardDescription>
          {rules.filter((r) => r.isActive).length} von {rules.length} Regeln aktiv
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {rules.map((rule) => (
            <div
              key={rule.id}
              className="flex items-center justify-between p-3 rounded-lg border hover:bg-muted/50 cursor-pointer transition-colors"
              onClick={() => onEdit(rule.id)}
            >
              <div className="flex items-center gap-3">
                <Badge
                  variant={rule.isActive ? 'default' : 'secondary'}
                  className={rule.isActive ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' : ''}
                >
                  {rule.isActive ? 'Aktiv' : 'Inaktiv'}
                </Badge>
                <div>
                  <p className="font-medium">{rule.name}</p>
                </div>
              </div>
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Badge variant="outline">
                  Prioritaet {rule.priority}
                </Badge>
                <Badge variant="outline">
                  {rule.matchCount} Treffer
                </Badge>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// ==================== Main Component ====================

type ViewMode = 'list' | 'create' | 'edit';
type ConfigType = 'email' | 'folder' | 'rule';

export function ImportsPage() {
  const [activeTab, setActiveTab] = useState('overview');
  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [editId, setEditId] = useState<string | null>(null);
  const [configType, setConfigType] = useState<ConfigType>('email');

  // Handlers
  const handleCreateEmail = () => {
    setConfigType('email');
    setViewMode('create');
    setEditId(null);
    setActiveTab('email');
  };

  const handleEditEmail = (configId: string) => {
    setConfigType('email');
    setViewMode('edit');
    setEditId(configId);
    setActiveTab('email');
  };

  const handleCreateFolder = () => {
    setConfigType('folder');
    setViewMode('create');
    setEditId(null);
    setActiveTab('folder');
  };

  const handleEditFolder = (configId: string) => {
    setConfigType('folder');
    setViewMode('edit');
    setEditId(configId);
    setActiveTab('folder');
  };

  const handleCreateRule = () => {
    setConfigType('rule');
    setViewMode('create');
    setEditId(null);
    setActiveTab('rules');
  };

  const handleEditRule = (ruleId: string) => {
    setConfigType('rule');
    setViewMode('edit');
    setEditId(ruleId);
    setActiveTab('rules');
  };

  const handleBack = () => {
    setViewMode('list');
    setEditId(null);
  };

  // Render form if in create/edit mode
  if (viewMode !== 'list') {
    if (configType === 'email') {
      return (
        <div className="p-8">
          <EmailConfigForm
            configId={editId ?? undefined}
            onSuccess={handleBack}
            onCancel={handleBack}
          />
        </div>
      );
    }
    if (configType === 'folder') {
      return (
        <div className="p-8">
          <FolderConfigForm
            configId={editId ?? undefined}
            onSave={handleBack}
            onCancel={handleBack}
          />
        </div>
      );
    }
    if (configType === 'rule') {
      return (
        <div className="p-8">
          <ImportRuleBuilder
            onSave={handleBack}
            onCancel={handleBack}
          />
        </div>
      );
    }
  }

  return (
    <ErrorBoundary
      errorTitle="Fehler in der Import-Verwaltung"
      errorDescription="Die Import-Konfigurationen konnten nicht geladen werden. Bitte versuchen Sie es erneut."
    >
      <div className="p-8 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Import-Verwaltung</h1>
            <p className="text-muted-foreground">
              Konfigurieren Sie automatische Dokumenten-Importe aus Email und Ordnern.
            </p>
          </div>
        </div>

      <ImportStatsCards />

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-6">
          <TabsTrigger value="overview" className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4" />
            Übersicht
          </TabsTrigger>
          <TabsTrigger value="email" className="flex items-center gap-2">
            <Mail className="h-4 w-4" />
            Email
          </TabsTrigger>
          <TabsTrigger value="folder" className="flex items-center gap-2">
            <FolderOpen className="h-4 w-4" />
            Ordner
          </TabsTrigger>
          <TabsTrigger value="rules" className="flex items-center gap-2">
            <Settings className="h-4 w-4" />
            Regeln
          </TabsTrigger>
          <TabsTrigger value="testing" className="flex items-center gap-2">
            <TestTube2 className="h-4 w-4" />
            Testen
          </TabsTrigger>
          <TabsTrigger value="logs" className="flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Protokoll
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6 pt-4">
          <div className="grid gap-6 lg:grid-cols-2">
            <EmailConfigList
              onCreateNew={handleCreateEmail}
              onEdit={handleEditEmail}
            />
            <FolderConfigList
              onCreateNew={handleCreateFolder}
              onEdit={handleEditFolder}
            />
          </div>
          <ImportRulesList onEdit={handleEditRule} />
          <ImportLogTable maxItems={10} />
        </TabsContent>

        <TabsContent value="email" className="pt-4">
          <EmailConfigList
            onCreateNew={handleCreateEmail}
            onEdit={handleEditEmail}
          />
        </TabsContent>

        <TabsContent value="folder" className="pt-4">
          <FolderConfigList
            onCreateNew={handleCreateFolder}
            onEdit={handleEditFolder}
          />
        </TabsContent>

        <TabsContent value="rules" className="pt-4">
          <ImportRuleBuilder onSave={() => {}} />
        </TabsContent>

        <TabsContent value="testing" className="pt-4">
          <RuleTestingPanel />
        </TabsContent>

        <TabsContent value="logs" className="pt-4">
          <ImportLogTable maxItems={100} />
        </TabsContent>
      </Tabs>
      </div>
    </ErrorBoundary>
  );
}

export default ImportsPage;
