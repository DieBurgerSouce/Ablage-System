/**
 * Admin Mahnungen - Aktive Mahnungen
 *
 * Zeigt nur aktive (nicht abgeschlossene) Mahnvorgänge
 */

import { createFileRoute } from '@tanstack/react-router';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { AlertTriangle } from 'lucide-react';
import { DunningTable } from '@/features/banking/components/DunningTable';
import { useDunningRecords } from '@/features/banking/hooks/use-banking-queries';
import { Skeleton } from '@/components/ui/skeleton';

export const Route = createFileRoute('/admin/mahnungen/aktiv')({
    component: AktiveMahnungenPage,
});

function AktiveMahnungenPage() {
    const { data: records, isLoading } = useDunningRecords({ status: 'active' });

    if (isLoading) {
        return (
            <Card>
                <CardHeader>
                    <Skeleton className="h-6 w-48" />
                    <Skeleton className="h-4 w-64" />
                </CardHeader>
                <CardContent>
                    <Skeleton className="h-[400px] w-full" />
                </CardContent>
            </Card>
        );
    }

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <AlertTriangle className="h-5 w-5 text-destructive" />
                    Aktive Mahnungen
                </CardTitle>
                <CardDescription>
                    {records?.items?.length ?? 0} aktive Mahnvorgänge, die Bearbeitung erfordern.
                </CardDescription>
            </CardHeader>
            <CardContent>
                <DunningTable data={records?.items ?? []} isLoading={isLoading} />
            </CardContent>
        </Card>
    );
}
