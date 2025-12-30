import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { FileQuestion, Home, ArrowLeft } from 'lucide-react'

export const Route = createFileRoute('/$')({
    component: NotFoundPage,
})

function NotFoundPage() {
    const navigate = useNavigate()

    return (
        <div className="h-screen w-full flex items-center justify-center bg-background relative overflow-hidden">
            {/* Background effects */}
            <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-background to-accent/5" />
            <div className="noise-overlay absolute inset-0" />

            {/* Content */}
            <Card className="w-full max-w-md glass-card relative z-10 border-white/10 shadow-2xl backdrop-blur-xl animate-in fade-in duration-500">
                <CardHeader className="space-y-4 text-center">
                    {/* 404 Icon */}
                    <div className="mx-auto w-20 h-20 rounded-full bg-muted/50 flex items-center justify-center border border-white/10">
                        <FileQuestion className="w-10 h-10 text-muted-foreground" />
                    </div>

                    {/* 404 Number */}
                    <div className="text-7xl font-bold font-display bg-gradient-to-br from-foreground to-muted-foreground bg-clip-text text-transparent">
                        404
                    </div>

                    <CardTitle className="text-2xl font-display font-semibold tracking-tight">
                        Seite nicht gefunden
                    </CardTitle>

                    <CardDescription className="text-muted-foreground/80 text-base">
                        Die angeforderte Seite existiert nicht oder wurde verschoben.
                        Bitte ueberpruefen Sie die URL oder kehren Sie zur Startseite zurueck.
                    </CardDescription>
                </CardHeader>

                <CardContent className="space-y-3">
                    {/* Current URL hint */}
                    <div className="p-3 rounded-lg bg-muted/30 border border-white/5">
                        <p className="text-xs text-muted-foreground text-center font-mono truncate">
                            {typeof window !== 'undefined' ? window.location.pathname : ''}
                        </p>
                    </div>
                </CardContent>

                <CardFooter className="flex flex-col gap-3">
                    <Button
                        className="w-full font-medium shadow-lg shadow-primary/20 hover:shadow-primary/30 transition-all"
                        onClick={() => navigate({ to: '/' })}
                    >
                        <Home className="w-4 h-4 mr-2" />
                        Zur Startseite
                    </Button>

                    <Button
                        variant="outline"
                        className="w-full border-white/10 hover:bg-white/5"
                        onClick={() => window.history.back()}
                    >
                        <ArrowLeft className="w-4 h-4 mr-2" />
                        Zurueck
                    </Button>
                </CardFooter>
            </Card>
        </div>
    )
}
