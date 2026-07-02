import { useEffect, useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { AlertCircle } from 'lucide-react';

export function SessionExpiredModal() {
    const [isOpen, setIsOpen] = useState(false);
    const navigate = useNavigate();

    useEffect(() => {
        const handleSessionExpired = () => {
            setIsOpen(true);
        };

        window.addEventListener('session-expired', handleSessionExpired);

        return () => {
            window.removeEventListener('session-expired', handleSessionExpired);
        };
    }, []);

    const handleLogin = () => {
        setIsOpen(false);
        navigate({ to: '/login' });
    };

    return (
        // W2-22/F2: Modal ist bewusst NICHT dismissbar. Bei abgelaufener Session
        // ist die App-Shell tot (kein gueltiger Token) -> ein Schliessen ohne
        // Aktion wuerde auf einer toten Oberflaeche enden. Einziger Ausgang ist
        // "Erneut anmelden" (-> /login). Schliessen via Klick ausserhalb,
        // Escape-Taste oder X-Button wird daher unterbunden.
        <Dialog
            open={isOpen}
            onOpenChange={(open) => {
                // Nur das (programmatische) Oeffnen erlauben; Schliessen ignorieren.
                if (open) setIsOpen(true);
            }}
        >
            <DialogContent
                className="sm:max-w-md [&>button]:hidden"
                onPointerDownOutside={(e) => e.preventDefault()}
                onInteractOutside={(e) => e.preventDefault()}
                onEscapeKeyDown={(e) => e.preventDefault()}
            >
                <DialogHeader>
                    <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-destructive/10">
                            <AlertCircle className="h-5 w-5 text-destructive" />
                        </div>
                        <div>
                            <DialogTitle>Sitzung abgelaufen</DialogTitle>
                            <DialogDescription>
                                Ihre Sitzung ist abgelaufen. Bitte melden Sie sich erneut an.
                            </DialogDescription>
                        </div>
                    </div>
                </DialogHeader>
                <DialogFooter className="mt-4">
                    <Button onClick={handleLogin} className="w-full">
                        Erneut anmelden
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
