/**
 * Admin Mahnungen - Mahnstopp
 *
 * Zeigt Mahnvorgaenge mit aktivem Mahnstopp
 */

import { createFileRoute } from '@tanstack/react-router';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { PauseCircle } from 'lucide-react';
import { DunningTable } from '@/features/banking/components/DunningTable';
import { useDunningRecords } from '@/features/banking/hooks/use-banking-queries';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';

export const Route = createFileRoute('/admin/mahnungen/mahnstopp')({
    component: MahnstoppPage,
});

function MahnstoppPage() {
    const { data: records, isLoading } = useDunningRecords({ mahnstopp: true });

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
        <div className="space-y-6">
            <Alert className="border-orange-200 bg-orange-50">
                <PauseCircle className="h-4 w-4 text-orange-600" />
                <AlertDescription className="text-orange-700">
                    Mahnvorgaenge mit Mahnstopp werden vom automatischen Mahnlauf ausgenommen.
                    Pruefen Sie regelmaessig, ob die Mahnstopp-Gruende noch bestehen.
                </AlertDescription>
            </Alert>

            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <PauseCircle className="h-5 w-5 text-orange-600" />
                        Mahnvorgaenge mit Mahnstopp
                    </CardTitle>
                    <CardDescription>
                        {records?.items?.length ?? 0} Mahnvorgaenge sind pausiert (z.B. wegen Reklamation oder Zahlungsvereinbarung).
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <DunningTable data={records?.items ?? []} isLoading={isLoading} />
                </CardContent>
            </Card>
        </div>
    );
}
