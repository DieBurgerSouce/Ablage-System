import { createFileRoute, Link } from '@tanstack/react-router';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
    Card,
    CardContent,
    CardDescription,
    CardFooter,
    CardHeader,
    CardTitle,
} from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { authService } from '@/lib/api/services/auth';
import { ArrowLeft, CheckCircle, Mail } from 'lucide-react';

export const Route = createFileRoute('/forgot-password')({
    component: ForgotPasswordPage,
});

function ForgotPasswordPage() {
    const [isLoading, setIsLoading] = useState(false);
    const [email, setEmail] = useState('');
    const [isSubmitted, setIsSubmitted] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoading(true);
        setError(null);

        try {
            await authService.requestPasswordReset(email);
            setIsSubmitted(true);
        } catch (err) {
            console.error('Password reset request failed', err);
            // Still show success message to prevent email enumeration
            setIsSubmitted(true);
        } finally {
            setIsLoading(false);
        }
    };

    if (isSubmitted) {
        return (
            <div className="h-screen w-full flex items-center justify-center bg-background relative overflow-hidden">
                <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-background to-accent/5" />
                <div className="noise-overlay absolute inset-0" />

                <Card className="w-full max-w-md glass-card relative z-10 border-white/10 shadow-2xl backdrop-blur-xl">
                    <CardHeader className="space-y-1">
                        <div className="flex justify-center mb-4">
                            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-green-500/10">
                                <CheckCircle className="h-8 w-8 text-green-500" />
                            </div>
                        </div>
                        <CardTitle className="text-2xl font-display font-bold text-center tracking-tight">
                            E-Mail gesendet
                        </CardTitle>
                        <CardDescription className="text-center text-muted-foreground/80">
                            Falls ein Konto mit dieser E-Mail-Adresse existiert, haben wir Ihnen
                            einen Link zum Zurücksetzen des Passworts gesendet.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="flex items-center gap-3 p-4 bg-muted/50 rounded-lg">
                            <Mail className="h-5 w-5 text-muted-foreground" />
                            <span className="text-sm text-muted-foreground">
                                Prüfen Sie auch Ihren Spam-Ordner.
                            </span>
                        </div>
                    </CardContent>
                    <CardFooter className="flex flex-col gap-3">
                        <Link to="/login" className="w-full">
                            <Button variant="outline" className="w-full">
                                <ArrowLeft className="h-4 w-4 mr-2" />
                                Zurück zur Anmeldung
                            </Button>
                        </Link>
                    </CardFooter>
                </Card>
            </div>
        );
    }

    return (
        <div className="h-screen w-full flex items-center justify-center bg-background relative overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-background to-accent/5" />
            <div className="noise-overlay absolute inset-0" />

            <Card className="w-full max-w-md glass-card relative z-10 border-white/10 shadow-2xl backdrop-blur-xl">
                <CardHeader className="space-y-1">
                    <CardTitle className="text-2xl font-display font-bold text-center tracking-tight">
                        Passwort vergessen?
                    </CardTitle>
                    <CardDescription className="text-center text-muted-foreground/80">
                        Geben Sie Ihre E-Mail-Adresse ein und wir senden Ihnen einen Link
                        zum Zurücksetzen Ihres Passworts.
                    </CardDescription>
                </CardHeader>
                <form onSubmit={handleSubmit}>
                    <CardContent className="space-y-4">
                        {error && (
                            <div className="p-3 text-sm text-destructive bg-destructive/10 rounded-md border border-destructive/20">
                                {error}
                            </div>
                        )}
                        <div className="space-y-2">
                            <Label htmlFor="email">E-Mail</Label>
                            <Input
                                id="email"
                                type="email"
                                placeholder="name@firma.de"
                                required
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="bg-background/50 border-white/10 focus:border-primary/50 transition-colors"
                            />
                        </div>
                    </CardContent>
                    <CardFooter className="flex flex-col gap-3">
                        <Button
                            className="w-full font-medium shadow-lg shadow-primary/20 hover:shadow-primary/30 transition-all"
                            type="submit"
                            disabled={isLoading}
                        >
                            {isLoading ? 'Wird gesendet...' : 'Link senden'}
                        </Button>
                        <Link
                            to="/login"
                            className="text-sm text-muted-foreground hover:text-primary transition-colors"
                        >
                            <ArrowLeft className="h-3 w-3 inline mr-1" />
                            Zuruck zur Anmeldung
                        </Link>
                    </CardFooter>
                </form>
            </Card>
        </div>
    );
}
