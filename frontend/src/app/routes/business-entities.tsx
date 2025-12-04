import { createFileRoute } from '@tanstack/react-router'
import { BusinessEntityTable } from '@/features/business-entities/components/BusinessEntityTable'
import { BusinessEntityForm } from '@/features/business-entities/components/BusinessEntityForm'
import { Button } from "@/components/ui/button"
import { Plus } from "lucide-react"
import {
    Dialog,
    DialogContent,
    DialogTrigger,
} from "@/components/ui/dialog"

export const Route = createFileRoute('/business-entities')({
    component: BusinessEntitiesPage,
})

function BusinessEntitiesPage() {
    return (
        <div className="p-8 space-y-8">
            <div className="flex justify-between items-start">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Geschäftspartner</h1>
                    <p className="text-muted-foreground mt-2">
                        Verwalten Sie Kunden, Lieferanten und andere Kontakte.
                    </p>
                </div>
                <Dialog>
                    <DialogTrigger asChild>
                        <Button className="gap-2">
                            <Plus className="w-4 h-4" />
                            Neuer Partner
                        </Button>
                    </DialogTrigger>
                    <DialogContent className="sm:max-w-[600px]">
                        <BusinessEntityForm />
                    </DialogContent>
                </Dialog>
            </div>

            <BusinessEntityTable />
        </div>
    )
}
