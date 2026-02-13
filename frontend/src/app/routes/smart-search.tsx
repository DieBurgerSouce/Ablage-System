/**
 * Smart Search Page Route - NLQ-powered Search with Entity Linking
 *
 * Features:
 * - Natural Language Query (NLQ) mit automatischer Erkennung
 * - Entity-Linking (Kunden, Lieferanten)
 * - Query-Interpretation Display
 * - Facet-basierte Filter
 * - As-you-type Autocomplete
 * - Query-Suggestions
 */

import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { AnimatedPage } from '@/components/animations';
import { SmartSearchBar } from '@/features/search/components/SmartSearchBar';
import { FileSearch, Sparkles } from 'lucide-react';

// ==================== Route Definition ====================

export const Route = createFileRoute('/smart-search')({
    component: SmartSearchPage,
});

// ==================== Page Component ====================

function SmartSearchPage() {
    const navigate = useNavigate();

    const handleResultClick = (documentId: string) => {
        navigate({ to: `/documents/${documentId}` });
    };

    return (
        <AnimatedPage>
            <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
                <div className="container mx-auto px-4 py-12 space-y-8">
                    {/* Header */}
                    <div className="text-center space-y-4 mb-12">
                        <div className="flex items-center justify-center gap-3">
                            <div className="relative">
                                <FileSearch className="h-10 w-10 text-primary" />
                                <Sparkles className="h-5 w-5 text-blue-500 absolute -top-1 -right-1 animate-pulse" />
                            </div>
                        </div>
                        <h1 className="text-4xl font-bold tracking-tight bg-gradient-to-r from-primary to-blue-600 bg-clip-text text-transparent">
                            Smart Search
                        </h1>
                        <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
                            Durchsuchen Sie Ihre Dokumente mit natürlicher Sprache.
                            Finden Sie Rechnungen, Kunden und mehr - einfach fragen!
                        </p>
                        <div className="flex flex-wrap justify-center gap-2 text-sm text-muted-foreground">
                            <span className="px-3 py-1 rounded-full bg-blue-500/10 text-blue-600">
                                „Zeige mir offene Rechnungen von Mueller"
                            </span>
                            <span className="px-3 py-1 rounded-full bg-purple-500/10 text-purple-600">
                                „Alle Lieferscheine vom letzten Monat"
                            </span>
                            <span className="px-3 py-1 rounded-full bg-green-500/10 text-green-600">
                                „Rechnungen über 1000 Euro"
                            </span>
                        </div>
                    </div>

                    {/* Smart Search Component */}
                    <SmartSearchBar onResultClick={handleResultClick} />
                </div>
            </div>
        </AnimatedPage>
    );
}
