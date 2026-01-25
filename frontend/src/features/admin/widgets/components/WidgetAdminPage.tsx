/**
 * Widget Admin Page
 *
 * Administrationsoberfläche für Widget-Verwaltung:
 * - Übersicht aller registrierten Widgets
 * - Rollen-basierte Berechtigungen
 * - Layout-Vorlagen verwalten
 * - Widget-Vorschau
 *
 * Phase 4.1 der Feature-Roadmap (Januar 2026)
 */

import { useState, useMemo } from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  LayoutGrid,
  Eye,
  Settings2,
  Shield,
  Search,
  RefreshCw,
  Check,
  X,
  Layers,
  Users,
  Calculator,
  User,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

import {
  getAllWidgets,
  getWidgetsByCategory,
  type WidgetRegistryEntry,
} from '@/features/dashboard/registry';
import {
  DASHBOARD_PRESETS,
  type UserRole,
} from '@/features/dashboard/stores/useDashboardStore';
import { useAvailableWidgets } from '@/features/dashboard/hooks/useDashboard';

// ==================== Types ====================

interface WidgetPermissionConfig {
  widgetType: string;
  allowedRoles: UserRole[];
  enabled: boolean;
}

// ==================== Constants ====================

const ROLE_CONFIG: Record<UserRole, { label: string; icon: React.ReactNode; color: string }> = {
  admin: { label: 'Administrator', icon: <Shield className="h-4 w-4" />, color: 'bg-red-500' },
  manager: { label: 'Manager', icon: <Users className="h-4 w-4" />, color: 'bg-blue-500' },
  accountant: { label: 'Buchhalter', icon: <Calculator className="h-4 w-4" />, color: 'bg-green-500' },
  user: { label: 'Benutzer', icon: <User className="h-4 w-4" />, color: 'bg-gray-500' },
};

const CATEGORY_LABELS: Record<string, string> = {
  info: 'Information',
  action: 'Aktionen',
  data: 'Daten',
  finance: 'Finanzen',
};

// ==================== Components ====================

interface WidgetPreviewDialogProps {
  widget: WidgetRegistryEntry;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function WidgetPreviewDialog({ widget, open, onOpenChange }: WidgetPreviewDialogProps) {
  const Widget = widget.component;
  const Icon = widget.icon;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[80vh] overflow-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Icon className="h-5 w-5" />
            {widget.label}
          </DialogTitle>
          <DialogDescription>{widget.description}</DialogDescription>
        </DialogHeader>
        <div className="mt-4 border rounded-lg p-4 bg-muted/30">
          <div className="min-h-[200px]">
            <Widget />
          </div>
        </div>
        <div className="mt-4 flex items-center gap-4 text-sm text-muted-foreground">
          <span>
            <strong>Typ:</strong> {widget.type}
          </span>
          <span>
            <strong>Kategorie:</strong> {CATEGORY_LABELS[widget.category]}
          </span>
          <span>
            <strong>Standard-Größe:</strong> {widget.defaultSize?.w}×{widget.defaultSize?.h}
          </span>
        </div>
      </DialogContent>
    </Dialog>
  );
}

interface WidgetCardProps {
  widget: WidgetRegistryEntry;
  permissions: WidgetPermissionConfig;
  onPermissionChange: (config: WidgetPermissionConfig) => void;
}

function WidgetCard({ widget, permissions, onPermissionChange }: WidgetCardProps) {
  const [previewOpen, setPreviewOpen] = useState(false);
  const Icon = widget.icon;

  const toggleRole = (role: UserRole) => {
    const newRoles = permissions.allowedRoles.includes(role)
      ? permissions.allowedRoles.filter((r) => r !== role)
      : [...permissions.allowedRoles, role];
    onPermissionChange({ ...permissions, allowedRoles: newRoles });
  };

  const toggleEnabled = (enabled: boolean) => {
    onPermissionChange({ ...permissions, enabled });
  };

  return (
    <>
      <Card className={cn('transition-opacity', !permissions.enabled && 'opacity-60')}>
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <div
                className={cn(
                  'p-2 rounded-lg',
                  widget.category === 'finance' && 'bg-emerald-500/10 text-emerald-500',
                  widget.category === 'info' && 'bg-blue-500/10 text-blue-500',
                  widget.category === 'action' && 'bg-amber-500/10 text-amber-500',
                  widget.category === 'data' && 'bg-purple-500/10 text-purple-500'
                )}
              >
                <Icon className="h-5 w-5" />
              </div>
              <div>
                <CardTitle className="text-base">{widget.label}</CardTitle>
                <Badge variant="secondary" className="mt-1 text-xs">
                  {CATEGORY_LABELS[widget.category]}
                </Badge>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Switch
                checked={permissions.enabled}
                onCheckedChange={toggleEnabled}
                aria-label="Widget aktivieren"
              />
              <Button variant="ghost" size="icon" onClick={() => setPreviewOpen(true)} aria-label="Widget-Vorschau anzeigen">
                <Eye className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          <p className="text-sm text-muted-foreground mb-4">{widget.description}</p>
          <div className="space-y-2">
            <Label className="text-xs font-medium">Berechtigte Rollen</Label>
            <div className="flex flex-wrap gap-2">
              {(Object.keys(ROLE_CONFIG) as UserRole[]).map((role) => {
                const config = ROLE_CONFIG[role];
                const isActive = permissions.allowedRoles.includes(role);
                return (
                  <TooltipProvider key={role}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant={isActive ? 'default' : 'outline'}
                          size="sm"
                          className={cn('gap-1', isActive && config.color)}
                          onClick={() => toggleRole(role)}
                          disabled={!permissions.enabled}
                        >
                          {config.icon}
                          <span className="sr-only md:not-sr-only md:inline">
                            {config.label}
                          </span>
                          {isActive ? (
                            <Check className="h-3 w-3 ml-1" />
                          ) : (
                            <X className="h-3 w-3 ml-1 opacity-50" />
                          )}
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>
                        {isActive ? `${config.label} entfernen` : `${config.label} hinzufügen`}
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                );
              })}
            </div>
          </div>
        </CardContent>
      </Card>

      <WidgetPreviewDialog widget={widget} open={previewOpen} onOpenChange={setPreviewOpen} />
    </>
  );
}

function WidgetListTab() {
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<string | 'all'>('all');
  const widgets = getAllWidgets();
  const { data: availableWidgets, isLoading } = useAvailableWidgets();

  // Local state for permissions (in production, this would come from API)
  const [permissions, setPermissions] = useState<Record<string, WidgetPermissionConfig>>(() =>
    Object.fromEntries(
      widgets.map((w) => [
        w.type,
        {
          widgetType: w.type,
          allowedRoles: ['admin', 'manager', 'accountant', 'user'] as UserRole[],
          enabled: true,
        },
      ])
    )
  );

  const filteredWidgets = useMemo(() => {
    return widgets.filter((w) => {
      const matchesSearch =
        w.label.toLowerCase().includes(search.toLowerCase()) ||
        w.description.toLowerCase().includes(search.toLowerCase()) ||
        w.type.toLowerCase().includes(search.toLowerCase());
      const matchesCategory = categoryFilter === 'all' || w.category === categoryFilter;
      return matchesSearch && matchesCategory;
    });
  }, [widgets, search, categoryFilter]);

  const handlePermissionChange = (config: WidgetPermissionConfig) => {
    setPermissions((prev) => ({
      ...prev,
      [config.widgetType]: config,
    }));
    toast.success('Berechtigung aktualisiert', {
      description: `${config.widgetType} wurde aktualisiert.`,
    });
  };

  const handleSaveAll = () => {
    // In production, this would call the backend API
    toast.success('Alle Änderungen gespeichert', {
      description: 'Die Widget-Berechtigungen wurden gespeichert.',
    });
  };

  const categories = ['all', 'info', 'action', 'data', 'finance'];

  return (
    <div className="space-y-6">
      {/* Header with filters */}
      <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
        <div className="flex flex-1 gap-4 items-center">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Widgets durchsuchen..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
          <div className="flex gap-1">
            {categories.map((cat) => (
              <Button
                key={cat}
                variant={categoryFilter === cat ? 'default' : 'outline'}
                size="sm"
                onClick={() => setCategoryFilter(cat)}
              >
                {cat === 'all' ? 'Alle' : CATEGORY_LABELS[cat]}
              </Button>
            ))}
          </div>
        </div>
        <Button onClick={handleSaveAll}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Änderungen speichern
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-4">
            <div className="text-2xl font-bold">{widgets.length}</div>
            <div className="text-xs text-muted-foreground">Registrierte Widgets</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="text-2xl font-bold">
              {Object.values(permissions).filter((p) => p.enabled).length}
            </div>
            <div className="text-xs text-muted-foreground">Aktivierte Widgets</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="text-2xl font-bold">{DASHBOARD_PRESETS.length}</div>
            <div className="text-xs text-muted-foreground">Layout-Vorlagen</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="text-2xl font-bold">{availableWidgets?.length ?? '-'}</div>
            <div className="text-xs text-muted-foreground">
              {isLoading ? 'Laden...' : 'Für Sie verfügbar'}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Widget Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {filteredWidgets.map((widget) => (
          <WidgetCard
            key={widget.type}
            widget={widget}
            permissions={permissions[widget.type]}
            onPermissionChange={handlePermissionChange}
          />
        ))}
      </div>

      {filteredWidgets.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          Keine Widgets gefunden für "{search}"
        </div>
      )}
    </div>
  );
}

function LayoutTemplatesTab() {
  const presets = DASHBOARD_PRESETS;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h3 className="text-lg font-semibold">Layout-Vorlagen</h3>
          <p className="text-sm text-muted-foreground">
            Vorkonfigurierte Dashboard-Layouts für verschiedene Benutzerrollen
          </p>
        </div>
        <Button variant="outline">
          <Layers className="h-4 w-4 mr-2" />
          Neue Vorlage erstellen
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {presets.map((preset) => {
          const roleConfig = ROLE_CONFIG[preset.role];
          return (
            <Card key={preset.id} className="overflow-hidden">
              <div className={cn('h-1', roleConfig.color)} />
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base flex items-center gap-2">
                    {roleConfig.icon}
                    {preset.name}
                  </CardTitle>
                  <Badge variant="secondary">{roleConfig.label}</Badge>
                </div>
                <CardDescription>{preset.description}</CardDescription>
              </CardHeader>
              <CardContent>
                {/* Mini grid preview */}
                <div className="aspect-video bg-muted rounded-md p-2 mb-4 relative">
                  <div className="grid grid-cols-12 gap-0.5 h-full">
                    {preset.widgets.map((w, i) => (
                      <div
                        key={i}
                        className="bg-primary/20 rounded-sm"
                        style={{
                          gridColumn: `${w.x + 1} / span ${w.w}`,
                          gridRow: `${w.y + 1} / span ${w.h}`,
                        }}
                      />
                    ))}
                  </div>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">{preset.widgets.length} Widgets</span>
                  <div className="flex gap-2">
                    <Button variant="ghost" size="sm">
                      <Eye className="h-4 w-4 mr-1" />
                      Vorschau
                    </Button>
                    <Button variant="ghost" size="sm">
                      <Settings2 className="h-4 w-4 mr-1" />
                      Bearbeiten
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function RolePermissionsTab() {
  const widgets = getAllWidgets();

  const roles: UserRole[] = ['admin', 'manager', 'accountant', 'user'];

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold">Rollen-Berechtigungsmatrix</h3>
        <p className="text-sm text-muted-foreground">
          Übersicht welche Widgets für welche Rollen verfügbar sind
        </p>
      </div>

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[300px]">Widget</TableHead>
              {roles.map((role) => (
                <TableHead key={role} className="text-center">
                  <div className="flex items-center justify-center gap-1">
                    {ROLE_CONFIG[role].icon}
                    <span className="hidden md:inline">{ROLE_CONFIG[role].label}</span>
                  </div>
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {widgets.map((widget) => {
              const Icon = widget.icon;
              return (
                <TableRow key={widget.type}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Icon className="h-4 w-4 text-muted-foreground" />
                      <span className="font-medium">{widget.label}</span>
                      <Badge variant="outline" className="ml-auto text-xs">
                        {widget.category}
                      </Badge>
                    </div>
                  </TableCell>
                  {roles.map((role) => (
                    <TableCell key={role} className="text-center">
                      <Switch defaultChecked aria-label={`${widget.label} für ${role}`} />
                    </TableCell>
                  ))}
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

// ==================== Main Component ====================

export function WidgetAdminPage() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
          <LayoutGrid className="h-8 w-8" />
          Widget-Verwaltung
        </h1>
        <p className="text-muted-foreground mt-2">
          Verwalten Sie Dashboard-Widgets, Berechtigungen und Layout-Vorlagen.
        </p>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="widgets" className="space-y-6">
        <TabsList>
          <TabsTrigger value="widgets" className="gap-2">
            <LayoutGrid className="h-4 w-4" />
            Widgets
          </TabsTrigger>
          <TabsTrigger value="layouts" className="gap-2">
            <Layers className="h-4 w-4" />
            Layout-Vorlagen
          </TabsTrigger>
          <TabsTrigger value="permissions" className="gap-2">
            <Shield className="h-4 w-4" />
            Rollen-Matrix
          </TabsTrigger>
        </TabsList>

        <TabsContent value="widgets">
          <WidgetListTab />
        </TabsContent>

        <TabsContent value="layouts">
          <LayoutTemplatesTab />
        </TabsContent>

        <TabsContent value="permissions">
          <RolePermissionsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default WidgetAdminPage;
