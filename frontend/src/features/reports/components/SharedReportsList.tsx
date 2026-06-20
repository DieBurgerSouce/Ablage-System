/**
 * SharedReportsList Component
 *
 * Zeigt eine Liste der mit dem aktuellen Benutzer geteilten Reports.
 */

import { useQuery } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import {
    Share2,
    FileText,
    Eye,
    Play,
    Edit,
    Trash2,
    Users,
    Clock,
    ChevronRight,
    AlertCircle,
    Inbox,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { listSharedWithMe, reportKeys } from '../api';
import type { ReportShare } from '../types';

// ==================== Types ====================

interface SharedReportsListProps {
    className?: string;
    onReportClick?: (templateId: string) => void;
}

// ==================== Helper Functions ====================

function formatDate(dateStr: string): string {
    const date = new Date(dateStr);
    return date.toLocaleDateString('de-DE', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
    });
}

function formatRelativeTime(dateStr: string): string {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return 'Heute';
    if (diffDays === 1) return 'Gestern';
    if (diffDays < 7) return `Vor ${diffDays} Tagen`;
    if (diffDays < 30) return `Vor ${Math.floor(diffDays / 7)} Wochen`;
    return formatDate(dateStr);
}

// ==================== Permission Badge ====================

interface PermissionBadgeProps {
    share: ReportShare;
}

function PermissionBadges({ share }: PermissionBadgeProps) {
    const permissions = [
        { key: 'can_view', icon: Eye, label: 'Ansehen', active: share.can_view },
        { key: 'can_execute', icon: Play, label: 'Ausführen', active: share.can_execute },
        { key: 'can_edit', icon: Edit, label: 'Bearbeiten', active: share.can_edit },
        { key: 'can_delete', icon: Trash2, label: 'Löschen', active: share.can_delete },
    ];

    const activePermissions = permissions.filter((p) => p.active);

    return (
        <TooltipProvider delayDuration={300}>
            <div className="flex items-center gap-1">
                {activePermissions.map((perm) => (
                    <Tooltip key={perm.key}>
                        <TooltipTrigger asChild>
                            <div className="p-1 rounded bg-muted">
                                <perm.icon className="h-3 w-3 text-muted-foreground" />
                            </div>
                        </TooltipTrigger>
                        <TooltipContent>
                            <p>{perm.label}</p>
                        </TooltipContent>
                    </Tooltip>
                ))}
            </div>
        </TooltipProvider>
    );
}

// ==================== Shared Report Row ====================

interface SharedReportRowProps {
    share: ReportShare;
    onClick: () => void;
}

function SharedReportRow({ share, onClick }: SharedReportRowProps) {
    return (
        <div
            className={cn(
                'flex items-center gap-4 py-3 px-4 -mx-4 rounded-lg',
                'hover:bg-accent/50 cursor-pointer transition-colors group'
            )}
            onClick={onClick}
        >
            {/* Icon */}
            <div className="p-2 rounded-lg bg-primary/10">
                <FileText className="h-5 w-5 text-primary" />
            </div>

            {/* Info */}
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                    <span className="font-medium truncate">
                        {share.template_name || 'Unbenannter Report'}
                    </span>
                </div>
                <div className="flex items-center gap-3 mt-0.5 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1">
                        <Users className="h-3 w-3" />
                        {share.shared_with_name || share.shared_with_email || 'Unbekannt'}
                    </span>
                    <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {formatRelativeTime(share.created_at)}
                    </span>
                </div>
            </div>

            {/* Permissions */}
            <PermissionBadges share={share} />

            {/* Chevron */}
            <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
        </div>
    );
}

// ==================== Loading Skeleton ====================

function LoadingSkeleton() {
    return (
        <div className="space-y-3">
            {[1, 2, 3].map((i) => (
                <div key={i} className="flex items-center gap-4 py-3">
                    <Skeleton className="h-10 w-10 rounded-lg" />
                    <div className="flex-1 space-y-2">
                        <Skeleton className="h-4 w-48" />
                        <Skeleton className="h-3 w-32" />
                    </div>
                    <Skeleton className="h-6 w-20" />
                </div>
            ))}
        </div>
    );
}

// ==================== Component ====================

export function SharedReportsList({ className, onReportClick }: SharedReportsListProps) {
    const navigate = useNavigate();

    const {
        data: sharedReports,
        isLoading,
        isError,
        error,
        refetch,
    } = useQuery({
        queryKey: reportKeys.shared(),
        queryFn: listSharedWithMe,
    });

    const handleReportClick = (templateId: string) => {
        if (onReportClick) {
            onReportClick(templateId);
        } else {
            navigate({ to: '/berichte' });
        }
    };

    return (
        <Card className={className}>
            <CardHeader className="pb-3">
                <CardTitle className="text-lg flex items-center gap-2">
                    <Share2 className="h-5 w-5" />
                    Mit mir geteilte Reports
                </CardTitle>
                <CardDescription>
                    Reports, die andere Benutzer mit Ihnen geteilt haben
                </CardDescription>
            </CardHeader>
            <CardContent>
                {isLoading ? (
                    <LoadingSkeleton />
                ) : isError ? (
                    <div className="flex flex-col items-center justify-center py-8 text-center">
                        <AlertCircle className="h-10 w-10 text-destructive mb-3" />
                        <p className="text-destructive font-medium mb-1">
                            Fehler beim Laden
                        </p>
                        <p className="text-sm text-muted-foreground mb-4">
                            {error instanceof Error ? error.message : 'Unbekannter Fehler'}
                        </p>
                        <Button variant="outline" size="sm" onClick={() => refetch()}>
                            Erneut versuchen
                        </Button>
                    </div>
                ) : sharedReports && sharedReports.length > 0 ? (
                    <div className="divide-y">
                        {sharedReports.map((share) => (
                            <SharedReportRow
                                key={share.id}
                                share={share}
                                onClick={() => handleReportClick(share.template_id)}
                            />
                        ))}
                    </div>
                ) : (
                    <div className="flex flex-col items-center justify-center py-12 text-center">
                        <Inbox className="h-12 w-12 text-muted-foreground mb-4" />
                        <p className="text-muted-foreground font-medium mb-1">
                            Keine geteilten Reports
                        </p>
                        <p className="text-sm text-muted-foreground max-w-[300px]">
                            Wenn andere Benutzer Reports mit Ihnen teilen,
                            erscheinen diese hier.
                        </p>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}

export default SharedReportsList;
