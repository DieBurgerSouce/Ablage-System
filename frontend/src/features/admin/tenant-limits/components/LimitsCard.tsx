/**
 * Limits Card Component
 *
 * Zeigt die aktuellen Rate-Limits und Quota einer Company.
 */

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import {
  Zap,
  Clock,
  Calendar,
  Users,
  FileText,
  HardDrive,
  Crown,
} from 'lucide-react';
import type { CompanyLimitsResponse, UsageSummaryResponse } from '../hooks/use-tenant-limits';

interface LimitsCardProps {
  limits: CompanyLimitsResponse;
  usage?: UsageSummaryResponse;
}

const TIER_COLORS: Record<string, string> = {
  free: 'bg-gray-500',
  basic: 'bg-blue-500',
  professional: 'bg-purple-500',
  enterprise: 'bg-amber-500',
};

const TIER_LABELS: Record<string, string> = {
  free: 'Free',
  basic: 'Basic',
  professional: 'Professional',
  enterprise: 'Enterprise',
};

export function LimitsCard({ limits, usage }: LimitsCardProps) {
  const tierDefaults = limits.tier_defaults;

  // Berechne Prozentsaetze fuer Quotas
  const documentsUsed = usage?.documents_processed ?? 0;
  const documentsPercent = Math.min(100, (documentsUsed / limits.max_documents_per_month) * 100);

  const storageUsedGB = (usage?.storage_used_bytes ?? 0) / (1024 ** 3);
  const storagePercent = Math.min(100, (storageUsedGB / limits.max_storage_gb) * 100);

  const usersActive = usage?.active_users ?? 0;
  const usersPercent = Math.min(100, (usersActive / limits.max_users) * 100);

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">Limits & Quotas</CardTitle>
          <Badge className={TIER_COLORS[limits.subscription_tier]}>
            <Crown className="mr-1 h-3 w-3" />
            {TIER_LABELS[limits.subscription_tier]}
          </Badge>
        </div>
        <CardDescription>{limits.company_name}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Rate Limits */}
        <div className="space-y-3">
          <h4 className="text-sm font-medium text-muted-foreground">Rate Limits</h4>
          <div className="grid grid-cols-3 gap-4">
            <LimitItem
              icon={<Zap className="h-4 w-4" />}
              label="Pro Minute"
              value={tierDefaults.requests_per_minute}
            />
            <LimitItem
              icon={<Clock className="h-4 w-4" />}
              label="Pro Stunde"
              value={tierDefaults.requests_per_hour}
            />
            <LimitItem
              icon={<Calendar className="h-4 w-4" />}
              label="Pro Tag"
              value={tierDefaults.requests_per_day}
            />
          </div>
        </div>

        {/* Quotas mit Progress */}
        <div className="space-y-4">
          <h4 className="text-sm font-medium text-muted-foreground">Quota-Nutzung</h4>

          {/* Dokumente */}
          <QuotaProgress
            icon={<FileText className="h-4 w-4" />}
            label="Dokumente/Monat"
            used={documentsUsed}
            max={limits.max_documents_per_month}
            percent={documentsPercent}
          />

          {/* Storage */}
          <QuotaProgress
            icon={<HardDrive className="h-4 w-4" />}
            label="Speicher"
            used={storageUsedGB.toFixed(2)}
            max={limits.max_storage_gb}
            percent={storagePercent}
            unit="GB"
          />

          {/* Benutzer */}
          <QuotaProgress
            icon={<Users className="h-4 w-4" />}
            label="Benutzer"
            used={usersActive}
            max={limits.max_users}
            percent={usersPercent}
          />
        </div>

        {/* Features */}
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-muted-foreground">Aktivierte Features</h4>
          <div className="flex flex-wrap gap-1">
            {limits.features_enabled.map((feature) => (
              <Badge key={feature} variant="outline" className="text-xs">
                {formatFeatureName(feature)}
              </Badge>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

interface LimitItemProps {
  icon: React.ReactNode;
  label: string;
  value: number;
}

function LimitItem({ icon, label, value }: LimitItemProps) {
  return (
    <div className="flex flex-col items-center rounded-lg border p-3">
      <div className="text-muted-foreground">{icon}</div>
      <span className="text-xl font-bold">{formatNumber(value)}</span>
      <span className="text-xs text-muted-foreground">{label}</span>
    </div>
  );
}

interface QuotaProgressProps {
  icon: React.ReactNode;
  label: string;
  used: number | string;
  max: number;
  percent: number;
  unit?: string;
}

function QuotaProgress({ icon, label, used, max, percent, unit = '' }: QuotaProgressProps) {
  const isWarning = percent >= 80;
  const isDanger = percent >= 95;

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <div className="flex items-center gap-2">
          {icon}
          <span>{label}</span>
        </div>
        <span className={isDanger ? 'text-destructive font-medium' : isWarning ? 'text-amber-500' : ''}>
          {used} / {formatNumber(max)} {unit}
        </span>
      </div>
      <Progress
        value={percent}
        className={isDanger ? '[&>div]:bg-destructive' : isWarning ? '[&>div]:bg-amber-500' : ''}
      />
    </div>
  );
}

function formatNumber(num: number): string {
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(0)}M`;
  if (num >= 1_000) return `${(num / 1_000).toFixed(0)}K`;
  return num.toString();
}

function formatFeatureName(feature: string): string {
  const mapping: Record<string, string> = {
    ocr: 'OCR',
    search: 'Suche',
    export_csv: 'CSV Export',
    export_pdf: 'PDF Export',
    api_access: 'API-Zugriff',
    advanced_analytics: 'Analytics',
    workflow: 'Workflows',
    integrations: 'Integrationen',
    sso: 'SSO',
    audit_log: 'Audit Log',
    custom_branding: 'Branding',
    priority_support: 'Priority Support',
    dedicated_resources: 'Dedizierte Ressourcen',
  };
  return mapping[feature] || feature;
}
