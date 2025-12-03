import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ConfidenceIndicator } from "./ConfidenceIndicator"
import { FileText, ArrowRight, Clock } from "lucide-react"
import { Link } from "@tanstack/react-router"

interface ValidationItem {
    id: string
    documentName: string
    documentType: string
    confidence: number
    status: 'pending' | 'reviewed' | 'rejected'
    createdAt: string
    fieldsToReview: number
}

interface ValidationCardProps {
    item: ValidationItem
}

export function ValidationCard({ item }: ValidationCardProps) {
    return (
        <Card className="hover:shadow-md transition-shadow">
            <CardHeader className="pb-3">
                <div className="flex justify-between items-start">
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-primary/10 rounded-lg">
                            <FileText className="w-5 h-5 text-primary" />
                        </div>
                        <div>
                            <CardTitle className="text-base font-semibold line-clamp-1" title={item.documentName}>
                                {item.documentName}
                            </CardTitle>
                            <div className="flex items-center gap-2 mt-1">
                                <Badge variant="outline" className="text-xs font-normal">
                                    {item.documentType}
                                </Badge>
                                <span className="text-xs text-muted-foreground flex items-center gap-1">
                                    <Clock className="w-3 h-3" />
                                    {new Date(item.createdAt).toLocaleDateString()}
                                </span>
                            </div>
                        </div>
                    </div>
                </div>
            </CardHeader>
            <CardContent className="pb-3">
                <div className="space-y-3">
                    <div className="flex justify-between items-center text-sm">
                        <span className="text-muted-foreground">Gesamt-Konfidenz</span>
                        <ConfidenceIndicator score={item.confidence} />
                    </div>
                    <div className="flex justify-between items-center text-sm">
                        <span className="text-muted-foreground">Zu prüfen</span>
                        <Badge variant={item.fieldsToReview > 0 ? "destructive" : "secondary"}>
                            {item.fieldsToReview} Felder
                        </Badge>
                    </div>
                </div>
            </CardContent>
            <CardFooter className="pt-3 border-t">
                <Button asChild className="w-full" variant="secondary">
                    <Link to="/validation-queue/$id" params={{ id: item.id }}>
                        Validierung starten
                        <ArrowRight className="w-4 h-4 ml-2" />
                    </Link>
                </Button>
            </CardFooter>
        </Card>
    )
}
