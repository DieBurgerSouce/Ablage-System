/**
 * AddressCard - Zeigt eine Adresse (Sender/Empfaenger) an.
 */

import { Building2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ExtractedAddress } from "../types/extracted-data.types";

interface AddressCardProps {
    title: string;
    address?: ExtractedAddress | null;
    className?: string;
}

export function AddressCard({ title, address, className }: AddressCardProps) {
    if (!address) {
        return (
            <Card className={className}>
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <Building2 className="h-4 w-4" />
                        {title}
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <p className="text-sm text-muted-foreground">Nicht verfuegbar</p>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className={className}>
            <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <Building2 className="h-4 w-4" />
                    {title}
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1">
                {address.company && (
                    <p className="text-sm font-medium">{address.company}</p>
                )}
                {address.name && (
                    <p className="text-sm">{address.name}</p>
                )}
                {address.street && (
                    <p className="text-sm text-muted-foreground">{address.street}</p>
                )}
                {(address.zip_code || address.city) && (
                    <p className="text-sm text-muted-foreground">
                        {address.zip_code} {address.city}
                    </p>
                )}
                {address.country && address.country !== "DE" && (
                    <p className="text-sm text-muted-foreground">{address.country}</p>
                )}
            </CardContent>
        </Card>
    );
}
