/**
 * VersionBadge Component
 *
 * Badge fuer Version-Status mit farblicher Kennzeichnung.
 */

import { Badge } from '@/components/ui/badge';
import type { VersionStatus } from '../types/version-types';
import {
  formatVersionStatus,
  getVersionStatusVariant,
} from '@/lib/api/services/workflow-versions';
import { cn } from '@/lib/utils';

interface VersionBadgeProps {
  status: VersionStatus;
  className?: string;
}

export function VersionBadge({ status, className }: VersionBadgeProps) {
  const variant = getVersionStatusVariant(status);
  const label = formatVersionStatus(status);

  return (
    <Badge variant={variant} className={cn(className)}>
      {label}
    </Badge>
  );
}

interface VersionNumberBadgeProps {
  version: string;
  isActive?: boolean;
  isLatest?: boolean;
  className?: string;
}

export function VersionNumberBadge({
  version,
  isActive,
  isLatest,
  className,
}: VersionNumberBadgeProps) {
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <Badge variant="outline" className="font-mono">
        v{version}
      </Badge>
      {isActive && (
        <Badge variant="default" className="bg-green-600">
          Aktiv
        </Badge>
      )}
      {isLatest && !isActive && (
        <Badge variant="secondary">Neueste</Badge>
      )}
    </div>
  );
}
