import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { authService } from '@/lib/api/services/auth'

export const Route = createFileRoute('/login')({
    component: LoginPage,
})

function LoginPage() {
    const navigate = useNavigate()
    const [isLoading, setIsLoading] = useState(false)
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [error, setError] = useState<string | null>(null)

    const handleLogin = async (e: React.FormEvent) => {
        e.preventDefault()
        setIsLoading(true)
        setError(null)

        try {
            await authService.login(email, password)
            navigate({ to: '/' })
        } catch (err) {
            console.error('Anmeldung fehlgeschlagen', err)
            setError('Anmeldung fehlgeschlagen. Bitte überprüfen Sie Ihre Eingaben.')
        } finally {
            setIsLoading(false)
        }
    }

    return (
        <div className="h-screen w-full flex items-center justify-center bg-background relative overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-background to-accent/5" />
            <div className="noise-overlay absolute inset-0" />

            <Card className="w-full max-w-md glass-card relative z-10 border-white/10 shadow-2xl backdrop-blur-xl">
                <CardHeader className="space-y-1">
                    <CardTitle className="text-3xl font-display font-bold text-center tracking-tight">Ablage System</CardTitle>
                    <CardDescription className="text-center text-muted-foreground/80">
                        Melden Sie sich an, um auf Ihre Dokumente zuzugreifen.
                    </CardDescription>
                </CardHeader>
                <form onSubmit={handleLogin}>
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
                        <div className="space-y-2">
                            <Label htmlFor="password">Passwort</Label>
                            <Input
                                id="password"
                                type="password"
                                required
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                className="bg-background/50 border-white/10 focus:border-primary/50 transition-colors"
                            />
                        </div>
                    </CardContent>
                    <CardFooter>
                        <Button className="w-full font-medium shadow-lg shadow-primary/20 hover:shadow-primary/30 transition-all" type="submit" disabled={isLoading}>
                            {isLoading ? 'Anmeldung...' : 'Anmelden'}
                        </Button>
                    </CardFooter>
                </form>
            </Card>
        </div>
    )
}
