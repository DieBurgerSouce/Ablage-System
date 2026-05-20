import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Sparkles, Play } from "lucide-react"

export function GroupDetectionPanel() {
    return (
        <Card className="bg-gradient-to-br from-primary/5 to-transparent border-primary/20">
            <CardHeader>
                <div className="flex items-center gap-2">
                    <Sparkles className="w-5 h-5 text-primary" />
                    <CardTitle className="text-lg">Automatische Gruppierung</CardTitle>
                </div>
                <CardDescription>
                    Lassen Sie die KI zusammengehörige Dokumente automatisch erkennen und gruppieren.
                </CardDescription>
            </CardHeader>
            <CardContent>
                <div className="text-sm text-muted-foreground">
                    <p>Analysiert:</p>
                    <ul className="list-disc list-inside mt-1 space-y-1">
                        <li>Zeitliche Nähe</li>
                        <li>Inhaltliche Zusammenhänge</li>
                        <li>Dokumententypen</li>
                    </ul>
                </div>
            </CardContent>
            <CardFooter>
                <Button className="w-full gap-2">
                    <Play className="w-4 h-4" />
                    Analyse starten
                </Button>
            </CardFooter>
        </Card>
    )
}
