/**
 * BPMN Process Engine - Definitions List
 *
 * Übersicht aller Prozess-Definitionen.
 */

import { createFileRoute, Link } from '@tanstack/react-router';
import { useDefinitions, useDefinitionStatistics } from '@/features/bpmn';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Plus,
  Play,
  Pause,
  GitBranch,
  Clock,
  CheckCircle2,
  AlertCircle,
  BarChart3,
} from 'lucide-react';
import type { ProcessDefinition } from '@/features/bpmn';

export const Route = createFileRoute('/prozesse/')({
  component: ProcessDefinitionsPage,
});

function ProcessDefinitionsPage() {
  const { data: definitions, isLoading } = useDefinitions();
  const { data: stats } = useDefinitionStatistics();

  return (
    <div className="container mx-auto p-6">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            Prozess-Definitionen
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            BPMN 2.0 Prozesse erstellen und verwalten
          </p>
        </div>
        <Link to="/prozesse/neu">
          <Button>
            <Plus className="mr-2 h-4 w-4" />
            Neuer Prozess
          </Button>
        </Link>
      </div>

      {/* Statistics */}
      {stats && (
        <div className="mb-6 grid gap-4 md:grid-cols-4">
          <StatCard
            title="Gesamt"
            value={stats.total_definitions}
            icon={GitBranch}
            color="blue"
          />
          <StatCard
            title="Aktiv"
            value={stats.active_definitions}
            icon={Play}
            color="green"
          />
          <StatCard
            title="Instanzen"
            value={stats.total_instances}
            icon={BarChart3}
            color="purple"
          />
          <StatCard
            title="Laufend"
            value={stats.by_status?.running || 0}
            icon={Clock}
            color="amber"
          />
        </div>
      )}

      {/* Definitions List */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {isLoading ? (
          <>
            <DefinitionCardSkeleton />
            <DefinitionCardSkeleton />
            <DefinitionCardSkeleton />
          </>
        ) : definitions && definitions.length > 0 ? (
          definitions.map((def) => (
            <DefinitionCard key={def.id} definition={def} />
          ))
        ) : (
          <Card className="col-span-full">
            <CardContent className="flex flex-col items-center justify-center py-12 text-center">
              <GitBranch className="mb-4 h-12 w-12 text-gray-400" />
              <h3 className="mb-2 text-lg font-medium text-gray-900">
                Keine Prozesse vorhanden
              </h3>
              <p className="mb-4 text-sm text-gray-500">
                Erstellen Sie Ihren ersten BPMN-Prozess.
              </p>
              <Link to="/prozesse/neu">
                <Button>
                  <Plus className="mr-2 h-4 w-4" />
                  Prozess erstellen
                </Button>
              </Link>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

interface StatCardProps {
  title: string;
  value: number;
  icon: React.ComponentType<{ className?: string }>;
  color: 'blue' | 'green' | 'purple' | 'amber';
}

function StatCard({ title, value, icon: Icon, color }: StatCardProps) {
  const colorClasses = {
    blue: 'bg-blue-50 text-blue-600',
    green: 'bg-green-50 text-green-600',
    purple: 'bg-purple-50 text-purple-600',
    amber: 'bg-amber-50 text-amber-600',
  };

  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-4">
        <div className={`rounded-lg p-2 ${colorClasses[color]}`}>
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <p className="text-sm text-gray-500">{title}</p>
          <p className="text-2xl font-bold text-gray-900">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}

interface DefinitionCardProps {
  definition: ProcessDefinition;
}

function DefinitionCard({ definition }: DefinitionCardProps) {
  return (
    <Link to="/prozesse/$definitionId" params={{ definitionId: definition.id }}>
      <Card className="cursor-pointer transition-shadow hover:shadow-md">
        <CardHeader className="pb-2">
          <div className="flex items-start justify-between">
            <div>
              <CardTitle className="text-base">{definition.name}</CardTitle>
              <p className="text-xs text-gray-500">{definition.process_key}</p>
            </div>
            <Badge variant={definition.is_active ? 'default' : 'secondary'}>
              {definition.is_active ? (
                <>
                  <Play className="mr-1 h-3 w-3" />
                  Aktiv
                </>
              ) : (
                <>
                  <Pause className="mr-1 h-3 w-3" />
                  Inaktiv
                </>
              )}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          {definition.description && (
            <p className="mb-3 line-clamp-2 text-sm text-gray-600">
              {definition.description}
            </p>
          )}
          <div className="flex items-center justify-between text-xs text-gray-500">
            <span>Version {definition.version}</span>
            <span>
              {new Date(definition.created_at).toLocaleDateString('de-DE')}
            </span>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

function DefinitionCardSkeleton() {
  return (
    <Card>
      <CardHeader className="pb-2">
        <Skeleton className="h-5 w-3/4" />
        <Skeleton className="h-3 w-1/2" />
      </CardHeader>
      <CardContent>
        <Skeleton className="mb-3 h-8 w-full" />
        <div className="flex justify-between">
          <Skeleton className="h-3 w-16" />
          <Skeleton className="h-3 w-20" />
        </div>
      </CardContent>
    </Card>
  );
}
