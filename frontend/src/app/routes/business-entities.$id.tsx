import { createFileRoute } from '@tanstack/react-router'
import { BusinessEntityCard } from '@/features/business-entities/components/BusinessEntityCard'
import { Button } from "@/components/ui/button"
import { ChevronLeft } from "lucide-react"
import { Link } from "@tanstack/react-router"

export const Route = createFileRoute('/business-entities/$id')({
    component: BusinessEntityDetailPage,
})

function BusinessEntityDetailPage() {
    const { id } = Route.useParams()

    // Mock data
    const entity = {
        name: "Muster GmbH",
        type: "company",
        address: "Musterstraße 1, 12345 Musterstadt",
        documentCount: 45,
        status: "active"
    }

    return (
        <div className="p-8 space-y-8">
            <div className="flex items-center gap-4">
                <Button variant="ghost" size="icon" asChild>
                    <Link to="/business-entities">
                        <ChevronLeft className="w-5 h-5" />
                    </Link>
                </Button>
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Partner Details</h1>
                    <p className="text-muted-foreground">ID: {id}</p>
                </div>
            </div>

            <div className="grid gap-8 md:grid-cols-3">
                <div className="md:col-span-1">
                    <BusinessEntityCard entity={entity} />
                </div>
                <div className="md:col-span-2 p-4 border rounded-lg bg-muted/10">
                    <h2 className="text-xl font-semibold mb-4">Verknüpfte Dokumente</h2>
                    <p className="text-muted-foreground">Liste der Dokumente hier...</p>
                </div>
            </div>
        </div>
    )
}
