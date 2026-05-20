/**
 * Document Hints Route
 *
 * Übersicht über unternehmensweite Dokument-Hinweise.
 */

import { createFileRoute } from '@tanstack/react-router';
import { AlertCircle } from 'lucide-react';
import { HintsSummaryCard } from '@/features/document-hints';

export const Route = createFileRoute('/document-hints')({
    component: DocumentHintsPage,
});

function DocumentHintsPage() {
    return (
        <div className="container py-8 max-w-6xl">
            {/* Header */}
            <div className="flex items-center gap-3 mb-8">
                <div className="p-2 bg-primary/10 rounded-lg">
                    <AlertCircle className="h-6 w-6 text-primary" />
                </div>
                <div>
                    <h1 className="text-2xl font-bold">Dokument-Hinweise</h1>
                    <p className="text-muted-foreground">
                        Unternehmensweite Übersicht über wichtige Dokument-Hinweise
                    </p>
                </div>
            </div>

            {/* Summary Card */}
            <div className="max-w-2xl">
                <HintsSummaryCard />
            </div>
        </div>
    );
}
