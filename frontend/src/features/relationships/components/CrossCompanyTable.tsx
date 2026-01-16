/**
 * CrossCompanyTable Component
 *
 * Zeigt Entities mit Firmen-Vergleichsinformationen in einer Tabelle.
 */

import { Link } from '@tanstack/react-router';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
    Building2,
    Factory,
    FileText,
    CheckCircle2,
    XCircle,
    ChevronRight,
    Users,
    Truck,
} from 'lucide-react';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import type { CrossCompanyEntity, CompanyStats } from '../api/relationships-api';

interface CrossCompanyTableProps {
    entities: CrossCompanyEntity[];
    isLoading?: boolean;
}

function CompanyCell({ company, stats }: { company: 'folie' | 'messer'; stats: CompanyStats }) {
    const Icon = company === 'folie' ? Building2 : Factory;
    const label = company === 'folie' ? 'Folie' : 'Messer';
    const colorClass = company === 'folie'
        ? 'text-blue-600 bg-blue-50 border-blue-200'
        : 'text-amber-600 bg-amber-50 border-amber-200';

    if (!stats.isPresent) {
        return (
            <div className="flex items-center gap-2 text-muted-foreground">
                <XCircle className="h-4 w-4" />
                <span className="text-sm">-</span>
            </div>
        );
    }

    return (
        <TooltipProvider>
            <Tooltip>
                <TooltipTrigger asChild>
                    <div className="flex items-center gap-2">
                        <Badge
                            variant="outline"
                            className={cn('gap-1', colorClass)}
                        >
                            <Icon className="h-3 w-3" />
                            <span>{label}</span>
                        </Badge>
                        <span className="text-sm text-muted-foreground">
                            {stats.documentCount} Dok.
                        </span>
                    </div>
                </TooltipTrigger>
                <TooltipContent side="top" className="max-w-xs">
                    <div className="space-y-1 text-sm">
                        {stats.customerNumber && (
                            <p>Kd-Nr.: {stats.customerNumber}</p>
                        )}
                        {stats.supplierNumber && (
                            <p>Lief-Nr.: {stats.supplierNumber}</p>
                        )}
                        {stats.matchcode && (
                            <p>Matchcode: {stats.matchcode}</p>
                        )}
                        {stats.lastActivity && (
                            <p>
                                Letzte Aktivitaet:{' '}
                                {new Date(stats.lastActivity).toLocaleDateString('de-DE')}
                            </p>
                        )}
                    </div>
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
}

function EntityTypeIcon({ type }: { type: string }) {
    switch (type) {
        case 'customer':
            return <Users className="h-4 w-4 text-blue-500" />;
        case 'supplier':
            return <Truck className="h-4 w-4 text-amber-500" />;
        case 'both':
            return (
                <div className="flex -space-x-1">
                    <Users className="h-4 w-4 text-blue-500" />
                    <Truck className="h-4 w-4 text-amber-500" />
                </div>
            );
        default:
            return <Building2 className="h-4 w-4 text-gray-500" />;
    }
}

function PresenceBadge({ presence }: { presence: string[] }) {
    const hasBoth = presence.includes('folie') && presence.includes('messer');
    const folieOnly = presence.includes('folie') && !presence.includes('messer');
    const messerOnly = !presence.includes('folie') && presence.includes('messer');

    if (hasBoth) {
        return (
            <Badge
                variant="outline"
                className="bg-emerald-50 text-emerald-700 border-emerald-200"
            >
                <CheckCircle2 className="h-3 w-3 mr-1" />
                Beide
            </Badge>
        );
    }

    if (folieOnly) {
        return (
            <Badge
                variant="outline"
                className="bg-blue-50 text-blue-700 border-blue-200"
            >
                <Building2 className="h-3 w-3 mr-1" />
                Nur Folie
            </Badge>
        );
    }

    if (messerOnly) {
        return (
            <Badge
                variant="outline"
                className="bg-amber-50 text-amber-700 border-amber-200"
            >
                <Factory className="h-3 w-3 mr-1" />
                Nur Messer
            </Badge>
        );
    }

    return (
        <Badge variant="outline" className="text-muted-foreground">
            Keine Praesenz
        </Badge>
    );
}

/**
 * Tabelle mit Cross-Company Entity-Daten.
 */
export function CrossCompanyTable({ entities, isLoading }: CrossCompanyTableProps) {
    if (isLoading) {
        return (
            <div className="flex items-center justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
        );
    }

    if (entities.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                <Building2 className="h-12 w-12 mb-4 opacity-50" />
                <p className="text-lg font-medium">Keine Geschaeftspartner gefunden</p>
                <p className="text-sm">Passen Sie Ihre Filterkriterien an.</p>
            </div>
        );
    }

    return (
        <div className="rounded-lg border bg-card">
            <Table>
                <TableHeader>
                    <TableRow>
                        <TableHead className="w-8">Typ</TableHead>
                        <TableHead>Name</TableHead>
                        <TableHead className="w-32">Praesenz</TableHead>
                        <TableHead>Spargelfolie</TableHead>
                        <TableHead>Spargelmesser</TableHead>
                        <TableHead className="text-right w-24">Dokumente</TableHead>
                        <TableHead className="w-12"></TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {entities.map((entity) => (
                        <TableRow key={entity.id} className="group">
                            <TableCell>
                                <EntityTypeIcon type={entity.entityType} />
                            </TableCell>
                            <TableCell>
                                <div className="flex flex-col">
                                    <span className="font-medium">{entity.name}</span>
                                    {(entity.primaryCustomerNumber || entity.primarySupplierNumber) && (
                                        <span className="text-xs text-muted-foreground">
                                            {entity.primaryCustomerNumber && `Kd: ${entity.primaryCustomerNumber}`}
                                            {entity.primaryCustomerNumber && entity.primarySupplierNumber && ' | '}
                                            {entity.primarySupplierNumber && `Lief: ${entity.primarySupplierNumber}`}
                                        </span>
                                    )}
                                </div>
                            </TableCell>
                            <TableCell>
                                <PresenceBadge presence={entity.companyPresence} />
                            </TableCell>
                            <TableCell>
                                <CompanyCell
                                    company="folie"
                                    stats={entity.companyStats.folie}
                                />
                            </TableCell>
                            <TableCell>
                                <CompanyCell
                                    company="messer"
                                    stats={entity.companyStats.messer}
                                />
                            </TableCell>
                            <TableCell className="text-right">
                                <div className="flex items-center justify-end gap-1.5">
                                    <FileText className="h-4 w-4 text-muted-foreground" />
                                    <span className="font-medium">{entity.totalDocuments}</span>
                                </div>
                            </TableCell>
                            <TableCell>
                                <Link
                                    to={
                                        entity.entityType === 'supplier'
                                            ? '/lieferanten/$supplierId'
                                            : '/kunden/$customerId'
                                    }
                                    params={
                                        entity.entityType === 'supplier'
                                            ? { supplierId: entity.id }
                                            : { customerId: entity.id }
                                    }
                                >
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        className="opacity-0 group-hover:opacity-100 transition-opacity"
                                    >
                                        <ChevronRight className="h-4 w-4" />
                                    </Button>
                                </Link>
                            </TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
        </div>
    );
}

export default CrossCompanyTable;
