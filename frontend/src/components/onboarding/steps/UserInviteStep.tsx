/**
 * Benutzer-Einladungs-Schritt im Setup-Wizard
 *
 * Erlaubt das Einladen von Teammitgliedern:
 * - E-Mail-Adressen eingeben
 * - Dieser Schritt ist optional (kann übersprungen werden)
 *
 * Hinweis: Die eigentlichen Einladungen werden nach der Firmenerstellung versendet.
 */

import { useState } from 'react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { cn } from '@/lib/utils'
import { Plus, X, Mail, Info, Users } from 'lucide-react'
import type { CompanySetupData } from '../CompanySetupWizard'

interface UserInviteStepProps {
    data: CompanySetupData
    onChange: (updates: Partial<CompanySetupData>) => void
    errors: Record<string, string>
}

export function UserInviteStep({ data, onChange, errors }: UserInviteStepProps) {
    const [newEmail, setNewEmail] = useState('')
    const [emailError, setEmailError] = useState('')

    const handleAddEmail = () => {
        const email = newEmail.trim().toLowerCase()

        // Validierung
        if (!email) {
            setEmailError('E-Mail-Adresse eingeben')
            return
        }

        if (!isValidEmail(email)) {
            setEmailError('Ungültige E-Mail-Adresse')
            return
        }

        if (data.invite_emails.includes(email)) {
            setEmailError('Diese E-Mail wurde bereits hinzugefügt')
            return
        }

        // Hinzufügen
        onChange({ invite_emails: [...data.invite_emails, email] })
        setNewEmail('')
        setEmailError('')
    }

    const handleRemoveEmail = (emailToRemove: string) => {
        onChange({
            invite_emails: data.invite_emails.filter((e) => e !== emailToRemove),
        })
    }

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') {
            e.preventDefault()
            handleAddEmail()
        }
    }

    return (
        <div className="space-y-6">
            {/* Info */}
            <Alert>
                <Info className="h-4 w-4" aria-hidden="true" />
                <AlertDescription>
                    <strong>Dieser Schritt ist optional.</strong> Sie können später jederzeit
                    weitere Benutzer in den Einstellungen hinzufügen.
                </AlertDescription>
            </Alert>

            {/* Beschreibung */}
            <div className="text-center py-4">
                <div className="p-4 rounded-full bg-primary/10 border border-primary/20 inline-block mb-4">
                    <Users className="w-10 h-10 text-primary" aria-hidden="true" />
                </div>
                <h3 className="text-lg font-semibold">Team einladen</h3>
                <p className="text-sm text-muted-foreground mt-1 max-w-md mx-auto">
                    Laden Sie Ihre Mitarbeiter ein, um gemeinsam an Dokumenten zu arbeiten.
                    Die Einladungen werden nach der Firmenerstellung versendet.
                </p>
            </div>

            {/* E-Mail Eingabe */}
            <div className="space-y-2">
                <Label htmlFor="invite-email" className="text-sm font-medium">
                    E-Mail-Adresse
                </Label>
                <div className="flex gap-2">
                    <div className="relative flex-1">
                        <Mail
                            className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground"
                            aria-hidden="true"
                        />
                        <Input
                            id="invite-email"
                            type="email"
                            value={newEmail}
                            onChange={(e) => {
                                setNewEmail(e.target.value)
                                setEmailError('')
                            }}
                            onKeyDown={handleKeyDown}
                            placeholder="mitarbeiter@firma.de"
                            className={cn('pl-10', emailError && 'border-destructive')}
                            aria-describedby={emailError ? 'invite-email-error' : undefined}
                            aria-invalid={!!emailError}
                        />
                    </div>
                    <Button
                        type="button"
                        onClick={handleAddEmail}
                        aria-label="E-Mail-Adresse zur Einladungsliste hinzufügen"
                    >
                        <Plus className="w-4 h-4 mr-1" aria-hidden="true" />
                        Hinzufügen
                    </Button>
                </div>
                {emailError && (
                    <p id="invite-email-error" className="text-xs text-destructive">
                        {emailError}
                    </p>
                )}
            </div>

            {/* Eingeladene E-Mails */}
            {data.invite_emails.length > 0 && (
                <div className="space-y-2">
                    <Label className="text-sm font-medium">
                        Einzuladende Benutzer ({data.invite_emails.length})
                    </Label>
                    <div className="flex flex-wrap gap-2 p-3 border rounded-lg bg-muted/30">
                        {data.invite_emails.map((email) => (
                            <Badge
                                key={email}
                                variant="secondary"
                                className="gap-1 pr-1"
                            >
                                <Mail className="w-3 h-3" aria-hidden="true" />
                                {email}
                                <button
                                    type="button"
                                    onClick={() => handleRemoveEmail(email)}
                                    className="ml-1 p-0.5 rounded-full hover:bg-destructive/20 transition-colors"
                                    aria-label={`${email} aus der Einladungsliste entfernen`}
                                >
                                    <X className="w-3 h-3" aria-hidden="true" />
                                </button>
                            </Badge>
                        ))}
                    </div>
                </div>
            )}

            {/* Leerer Zustand */}
            {data.invite_emails.length === 0 && (
                <div className="text-center py-6 border rounded-lg bg-muted/20">
                    <Mail className="w-8 h-8 text-muted-foreground mx-auto mb-2" aria-hidden="true" />
                    <p className="text-sm text-muted-foreground">
                        Noch keine Einladungen hinzugefügt.
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                        Sie können diesen Schritt überspringen.
                    </p>
                </div>
            )}

            {/* Fehler aus Parent */}
            {Object.entries(errors)
                .filter(([key]) => key.startsWith('invite_email_'))
                .map(([key, message]) => (
                    <p key={key} className="text-xs text-destructive">
                        {message}
                    </p>
                ))}
        </div>
    )
}

function isValidEmail(email: string): boolean {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
}
