import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Building2, User, MapPin, FileText } from "lucide-react"

interface BusinessEntityCardProps {
    entity: {
        name: string
        type: string
        address?: string
        documentCount: number
        status: string
    }
}

export function BusinessEntityCard({ entity }: BusinessEntityCardProps) {
    return (
        <Card className="hover:shadow-md transition-shadow cursor-pointer">
            <CardHeader className="pb-2">
                <div className="flex justify-between items-start">
                    <div className="p-2 bg-muted rounded-lg">
                        {entity.type === 'company' ? (
                            <Building2 className="w-5 h-5 text-muted-foreground" />
                        ) : (
                            <User className="w-5 h-5 text-muted-foreground" />
                        )}
                    </div>
                    <Badge variant={entity.status === 'active' ? 'default' : 'secondary'}>
                        {entity.status}
                    </Badge>
                </div>
                <CardTitle className="text-base mt-2">{entity.name}</CardTitle>
            </CardHeader>
            <CardContent>
                <div className="space-y-2 text-sm text-muted-foreground">
                    {entity.address && (
                        <div className="flex items-center gap-2">
                            <MapPin className="w-4 h-4" />
                            <span className="truncate">{entity.address}</span>
                        </div>
                    )}
                    <div className="flex items-center gap-2">
                        <FileText className="w-4 h-4" />
                        <span>{entity.documentCount} Dokumente</span>
                    </div>
                </div>
            </CardContent>
        </Card>
    )
}
