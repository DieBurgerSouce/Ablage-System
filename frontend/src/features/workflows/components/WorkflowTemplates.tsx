/**
 * WorkflowTemplates Component
 *
 * Template-Galerie fuer vorgefertigte Workflows.
 */

import { useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
  FileText,
  Brain,
  Mail,
  Clock,
  Copy,
  Plus,
  Search,
  Filter,
  Webhook,
  CheckCircle,
  AlertTriangle,
  Tag,
  FolderOpen,
  Zap,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { useTemplates, useInstantiateTemplate } from '../hooks/useWorkflows';
import type { Workflow } from '../types/workflow-types';

// Template category icons
const categoryIcons: Record<string, React.ElementType> = {
  document: FileText,
  ai: Brain,
  notification: Mail,
  schedule: Clock,
  webhook: Webhook,
  approval: CheckCircle,
  organization: FolderOpen,
  default: Zap,
};

const categoryLabels: Record<string, string> = {
  document: 'Dokumente',
  ai: 'KI & Automation',
  notification: 'Benachrichtigungen',
  schedule: 'Zeitplaene',
  webhook: 'Integrationen',
  approval: 'Genehmigungen',
  organization: 'Organisation',
};

const categoryColors: Record<string, string> = {
  document: 'bg-blue-500',
  ai: 'bg-purple-500',
  notification: 'bg-pink-500',
  schedule: 'bg-orange-500',
  webhook: 'bg-indigo-500',
  approval: 'bg-green-500',
  organization: 'bg-cyan-500',
  default: 'bg-gray-500',
};

interface TemplateCardProps {
  template: Workflow;
  onInstantiate: (template: Workflow) => void;
}

function TemplateCard({ template, onInstantiate }: TemplateCardProps) {
  const category = template.trigger_config?.category || 'default';
  const Icon = categoryIcons[category] || categoryIcons.default;
  const colorClass = categoryColors[category] || categoryColors.default;

  return (
    <Card className="group hover:border-primary transition-colors">
      <CardHeader className="pb-2">
        <div className="flex items-start gap-3">
          <div className={cn('rounded-lg p-2', colorClass)}>
            <Icon className="h-5 w-5 text-white" />
          </div>
          <div className="flex-1">
            <CardTitle className="text-lg">{template.name}</CardTitle>
            <CardDescription className="line-clamp-2 mt-1">
              {template.description || 'Keine Beschreibung verfügbar'}
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pb-2">
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline">
            {template.nodes?.length || 0} Schritte
          </Badge>
          {category !== 'default' && (
            <Badge variant="secondary">
              {categoryLabels[category] || category}
            </Badge>
          )}
        </div>
      </CardContent>
      <CardFooter className="pt-2">
        <Button
          variant="outline"
          size="sm"
          className="w-full group-hover:bg-primary group-hover:text-primary-foreground"
          onClick={() => onInstantiate(template)}
        >
          <Plus className="mr-2 h-4 w-4" />
          Verwenden
        </Button>
      </CardFooter>
    </Card>
  );
}

function TemplateCardSkeleton() {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-start gap-3">
          <Skeleton className="h-9 w-9 rounded-lg" />
          <div className="flex-1">
            <Skeleton className="h-5 w-32" />
            <Skeleton className="h-4 w-48 mt-2" />
          </div>
        </div>
      </CardHeader>
      <CardContent className="pb-2">
        <div className="flex gap-2">
          <Skeleton className="h-5 w-20" />
          <Skeleton className="h-5 w-24" />
        </div>
      </CardContent>
      <CardFooter className="pt-2">
        <Skeleton className="h-9 w-full" />
      </CardFooter>
    </Card>
  );
}

interface InstantiateDialogProps {
  template: Workflow | null;
  onClose: () => void;
  onConfirm: (name: string) => void;
  isLoading: boolean;
}

function InstantiateDialog({
  template,
  onClose,
  onConfirm,
  isLoading,
}: InstantiateDialogProps) {
  const [name, setName] = useState(template?.name ? `${template.name} (Kopie)` : '');

  const handleConfirm = () => {
    if (name.trim()) {
      onConfirm(name.trim());
    }
  };

  return (
    <Dialog open={!!template} onOpenChange={() => onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Workflow aus Template erstellen</DialogTitle>
          <DialogDescription>
            Erstelle einen neuen Workflow basierend auf dem Template &quot;{template?.name}&quot;.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="workflow-name">Workflow-Name</Label>
            <Input
              id="workflow-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Mein neuer Workflow"
            />
          </div>

          {template && (
            <div className="rounded-lg border bg-muted/50 p-3 text-sm">
              <div className="font-medium mb-1">Template-Details:</div>
              <ul className="space-y-1 text-muted-foreground">
                <li>{template.nodes?.length || 0} Schritte</li>
                <li>Trigger: {template.trigger_type}</li>
                {template.description && (
                  <li className="text-xs">{template.description}</li>
                )}
              </ul>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={isLoading}>
            Abbrechen
          </Button>
          <Button onClick={handleConfirm} disabled={!name.trim() || isLoading}>
            {isLoading ? (
              <>
                <Zap className="mr-2 h-4 w-4 animate-spin" />
                Wird erstellt...
              </>
            ) : (
              <>
                <Plus className="mr-2 h-4 w-4" />
                Erstellen
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface WorkflowTemplatesProps {
  showAsGallery?: boolean;
}

export default function WorkflowTemplates({ showAsGallery = true }: WorkflowTemplatesProps) {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [templateToInstantiate, setTemplateToInstantiate] = useState<Workflow | null>(null);

  const { data: templates, isLoading, error } = useTemplates(
    selectedCategory || undefined
  );
  const instantiateTemplate = useInstantiateTemplate();

  const filteredTemplates = templates?.filter((template) => {
    if (!search) return true;
    const searchLower = search.toLowerCase();
    return (
      template.name.toLowerCase().includes(searchLower) ||
      template.description?.toLowerCase().includes(searchLower)
    );
  });

  const handleInstantiate = async (name: string) => {
    if (!templateToInstantiate) return;

    const workflow = await instantiateTemplate.mutateAsync({
      templateId: templateToInstantiate.id,
      name,
    });

    if (workflow) {
      setTemplateToInstantiate(null);
      navigate({ to: '/workflows/$workflowId', params: { workflowId: workflow.id } });
    }
  };

  // Get unique categories from templates
  const categories = Array.from(
    new Set(templates?.map((t) => t.trigger_config?.category || 'default') || [])
  );

  if (!showAsGallery) {
    // Compact list view for sidebar/dropdown
    return (
      <div className="space-y-2">
        {isLoading ? (
          <>
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </>
        ) : (
          templates?.slice(0, 5).map((template) => (
            <button
              key={template.id}
              onClick={() => setTemplateToInstantiate(template)}
              className="flex w-full items-center gap-3 rounded-lg border p-3 text-left hover:bg-muted"
            >
              <Zap className="h-5 w-5 text-primary" />
              <div>
                <div className="font-medium">{template.name}</div>
                <div className="text-xs text-muted-foreground">
                  {template.nodes?.length || 0} Schritte
                </div>
              </div>
            </button>
          ))
        )}

        <InstantiateDialog
          template={templateToInstantiate}
          onClose={() => setTemplateToInstantiate(null)}
          onConfirm={handleInstantiate}
          isLoading={instantiateTemplate.isPending}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold">Workflow-Templates</h2>
        <p className="text-muted-foreground">
          Starte mit einem vorgefertigten Workflow und passe ihn an deine Beduerfnisse an.
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Templates durchsuchen..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
          />
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            variant={selectedCategory === null ? 'default' : 'outline'}
            size="sm"
            onClick={() => setSelectedCategory(null)}
          >
            Alle
          </Button>
          {categories.map((category) => {
            const Icon = categoryIcons[category] || categoryIcons.default;
            return (
              <Button
                key={category}
                variant={selectedCategory === category ? 'default' : 'outline'}
                size="sm"
                onClick={() => setSelectedCategory(category)}
              >
                <Icon className="mr-2 h-4 w-4" />
                {categoryLabels[category] || category}
              </Button>
            );
          })}
        </div>
      </div>

      {/* Template Grid */}
      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[...Array(6)].map((_, i) => (
            <TemplateCardSkeleton key={i} />
          ))}
        </div>
      ) : error ? (
        <Card className="p-8 text-center">
          <AlertTriangle className="mx-auto h-12 w-12 text-destructive" />
          <p className="mt-4 text-lg font-medium">Fehler beim Laden der Templates</p>
          <p className="text-muted-foreground">{(error as Error).message}</p>
        </Card>
      ) : filteredTemplates?.length === 0 ? (
        <Card className="p-8 text-center">
          <Zap className="mx-auto h-12 w-12 text-muted-foreground" />
          <p className="mt-4 text-lg font-medium">Keine Templates gefunden</p>
          <p className="text-muted-foreground">
            {search
              ? 'Versuche einen anderen Suchbegriff.'
              : 'Noch keine Templates verfügbar.'}
          </p>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filteredTemplates?.map((template) => (
            <TemplateCard
              key={template.id}
              template={template}
              onInstantiate={setTemplateToInstantiate}
            />
          ))}
        </div>
      )}

      {/* Instantiate Dialog */}
      <InstantiateDialog
        template={templateToInstantiate}
        onClose={() => setTemplateToInstantiate(null)}
        onConfirm={handleInstantiate}
        isLoading={instantiateTemplate.isPending}
      />
    </div>
  );
}
