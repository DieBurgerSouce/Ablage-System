import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"

export function BusinessEntityForm() {
    return (
        <Card>
            <CardHeader>
                <CardTitle>Neuen Geschäftspartner anlegen</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                        <Label htmlFor="type">Typ</Label>
                        <Select defaultValue="company">
                            <SelectTrigger>
                                <SelectValue placeholder="Typ auswählen" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="company">Firma</SelectItem>
                                <SelectItem value="person">Privatperson</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="status">Status</Label>
                        <Select defaultValue="active">
                            <SelectTrigger>
                                <SelectValue placeholder="Status" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="active">Aktiv</SelectItem>
                                <SelectItem value="inactive">Inaktiv</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                </div>

                <div className="space-y-2">
                    <Label htmlFor="name">Name / Firmenbezeichnung</Label>
                    <Input id="name" placeholder="z.B. Muster GmbH" />
                </div>

                <div className="space-y-2">
                    <Label htmlFor="taxId">Steuernummer / USt-ID</Label>
                    <Input id="taxId" placeholder="DE..." />
                </div>

                <div className="space-y-2">
                    <Label htmlFor="address">Anschrift</Label>
                    <Input id="address" placeholder="Straße, Hausnummer" />
                    <div className="grid grid-cols-3 gap-4 mt-2">
                        <Input placeholder="PLZ" className="col-span-1" />
                        <Input placeholder="Ort" className="col-span-2" />
                    </div>
                </div>
            </CardContent>
            <CardFooter className="flex justify-end gap-2">
                <Button variant="outline">Abbrechen</Button>
                <Button>Speichern</Button>
            </CardFooter>
        </Card>
    )
}
