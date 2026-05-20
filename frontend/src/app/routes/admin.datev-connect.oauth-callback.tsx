/**
 * DATEV Connect - OAuth2 Callback Handler
 *
 * Verarbeitet den OAuth2 Callback von DATEV und aktualisiert die Verbindung.
 */

import { useEffect, useState } from 'react';
import { createFileRoute, useNavigate, useSearch } from '@tanstack/react-router';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Loader2, CheckCircle, XCircle, Link2 } from 'lucide-react';
import { useOAuth2Callback } from '@/features/datev/hooks/use-datev-connect-queries';

type CallbackSearchParams = {
    code?: string;
    state?: string;
    error?: string;
    error_description?: string;
};

export const Route = createFileRoute('/admin/datev-connect/oauth-callback')({
    component: OAuthCallbackPage,
    validateSearch: (search: Record<string, unknown>): CallbackSearchParams => ({
        code: search.code as string | undefined,
        state: search.state as string | undefined,
        error: search.error as string | undefined,
        error_description: search.error_description as string | undefined,
    }),
});

function OAuthCallbackPage() {
    const navigate = useNavigate();
    const searchParams = useSearch({ from: '/admin/datev-connect/oauth-callback' });
    const [status, setStatus] = useState<'processing' | 'success' | 'error'>('processing');
    const [errorMessage, setErrorMessage] = useState<string>('');

    const oauthCallback = useOAuth2Callback();

    useEffect(() => {
        // Prüfen auf Fehler von DATEV
        if (searchParams.error) {
            setStatus('error');
            setErrorMessage(
                searchParams.error_description ||
                    `OAuth2 Fehler: ${searchParams.error}`
            );
            return;
        }

        // Prüfen auf erforderliche Parameter
        if (!searchParams.code || !searchParams.state) {
            setStatus('error');
            setErrorMessage('Ungültiger OAuth2 Callback: Code oder State fehlt.');
            return;
        }

        // State enthält connection_id:csrf_token
        const [connectionId, csrfToken] = searchParams.state.split(':');
        if (!connectionId || !csrfToken) {
            setStatus('error');
            setErrorMessage('Ungültiger State-Parameter im OAuth2 Callback.');
            return;
        }

        // Callback verarbeiten
        oauthCallback.mutate(
            {
                connectionId,
                code: searchParams.code,
                state: searchParams.state,
            },
            {
                onSuccess: () => {
                    setStatus('success');
                    // Nach 2 Sekunden zu den Verbindungen navigieren
                    setTimeout(() => {
                        navigate({ to: '/admin/datev-connect' });
                    }, 2000);
                },
                onError: (error) => {
                    setStatus('error');
                    setErrorMessage(
                        error instanceof Error
                            ? error.message
                            : 'Die OAuth2-Autorisierung konnte nicht abgeschlossen werden.'
                    );
                },
            }
        );
    }, [searchParams, oauthCallback, navigate]);

    return (
        <div className="flex items-center justify-center min-h-[60vh]">
            <Card className="w-full max-w-md">
                <CardHeader className="text-center">
                    {status === 'processing' && (
                        <>
                            <div className="mx-auto mb-4 h-12 w-12 rounded-full bg-blue-100 flex items-center justify-center">
                                <Loader2 className="h-6 w-6 text-blue-600 animate-spin" />
                            </div>
                            <CardTitle>Verbindung wird hergestellt...</CardTitle>
                            <CardDescription>
                                Bitte warten Sie, während wir Ihre DATEV-Verbindung einrichten.
                            </CardDescription>
                        </>
                    )}

                    {status === 'success' && (
                        <>
                            <div className="mx-auto mb-4 h-12 w-12 rounded-full bg-green-100 flex items-center justify-center">
                                <CheckCircle className="h-6 w-6 text-green-600" />
                            </div>
                            <CardTitle>Verbindung erfolgreich!</CardTitle>
                            <CardDescription>
                                Ihre DATEV-Verbindung wurde erfolgreich eingerichtet.
                                Sie werden gleich weitergeleitet...
                            </CardDescription>
                        </>
                    )}

                    {status === 'error' && (
                        <>
                            <div className="mx-auto mb-4 h-12 w-12 rounded-full bg-red-100 flex items-center justify-center">
                                <XCircle className="h-6 w-6 text-red-600" />
                            </div>
                            <CardTitle>Verbindung fehlgeschlagen</CardTitle>
                            <CardDescription className="text-red-600">
                                {errorMessage}
                            </CardDescription>
                        </>
                    )}
                </CardHeader>

                <CardContent>
                    {status === 'success' && (
                        <div className="text-center">
                            <Button
                                variant="outline"
                                onClick={() => navigate({ to: '/admin/datev-connect' })}
                            >
                                <Link2 className="mr-2 h-4 w-4" />
                                Zu den Verbindungen
                            </Button>
                        </div>
                    )}

                    {status === 'error' && (
                        <div className="flex flex-col gap-3">
                            <Button
                                onClick={() => navigate({ to: '/admin/datev-connect' })}
                            >
                                Zurück zu den Verbindungen
                            </Button>
                            <Button
                                variant="outline"
                                onClick={() => window.location.reload()}
                            >
                                Erneut versuchen
                            </Button>
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
