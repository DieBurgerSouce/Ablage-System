import { useState, useRef, useEffect } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Loader2, KeyRound } from 'lucide-react';

interface TwoFactorInputProps {
    onSubmit: (code: string) => Promise<void>;
    onCancel: () => void;
    isLoading?: boolean;
    error?: string | null;
}

export function TwoFactorInput({
    onSubmit,
    onCancel,
    isLoading = false,
    error,
}: TwoFactorInputProps) {
    const [code, setCode] = useState('');
    const [useBackupCode, setUseBackupCode] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        // Auto-focus on mount
        inputRef.current?.focus();
    }, [useBackupCode]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (code.length >= 6) {
            await onSubmit(code);
        }
    };

    const handleCodeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const value = e.target.value.replace(/[^0-9a-zA-Z-]/g, '');

        if (useBackupCode) {
            // Backup codes are 8 chars with optional dash
            setCode(value.slice(0, 9));
        } else {
            // TOTP codes are 6 digits only
            const digits = value.replace(/\D/g, '');
            setCode(digits.slice(0, 6));
        }
    };

    // Auto-submit when 6 digits are entered (TOTP only)
    useEffect(() => {
        if (!useBackupCode && code.length === 6 && !isLoading) {
            // Promise rejection is handled by the parent component via error prop
            void onSubmit(code);
        }
    }, [code, useBackupCode, isLoading, onSubmit]);

    return (
        <form onSubmit={handleSubmit} className="space-y-4">
            <div className="flex justify-center mb-4">
                <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
                    <KeyRound className="h-7 w-7 text-primary" />
                </div>
            </div>

            <div className="text-center mb-4">
                <h3 className="text-lg font-semibold">
                    {useBackupCode ? 'Backup-Code eingeben' : '2FA-Code eingeben'}
                </h3>
                <p className="text-sm text-muted-foreground mt-1">
                    {useBackupCode
                        ? 'Geben Sie einen Ihrer Backup-Codes ein'
                        : 'Geben Sie den 6-stelligen Code aus Ihrer Authenticator-App ein'}
                </p>
            </div>

            {error && (
                <div className="p-3 text-sm text-destructive bg-destructive/10 rounded-md border border-destructive/20">
                    {error}
                </div>
            )}

            <div className="space-y-2">
                <Label htmlFor="2fa-code" className="sr-only">
                    {useBackupCode ? 'Backup-Code' : '2FA-Code'}
                </Label>
                <Input
                    ref={inputRef}
                    id="2fa-code"
                    type="text"
                    inputMode={useBackupCode ? 'text' : 'numeric'}
                    placeholder={useBackupCode ? 'XXXX-XXXX' : '000000'}
                    value={code}
                    onChange={handleCodeChange}
                    className="text-center text-2xl tracking-widest font-mono bg-background/50 border-white/10 focus:border-primary/50"
                    disabled={isLoading}
                    autoComplete="one-time-code"
                />
            </div>

            <div className="flex flex-col gap-2">
                <Button
                    type="submit"
                    className="w-full"
                    disabled={isLoading || (useBackupCode ? code.length < 8 : code.length < 6)}
                >
                    {isLoading ? (
                        <>
                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                            Wird überprüft...
                        </>
                    ) : (
                        'Bestätigen'
                    )}
                </Button>

                <Button
                    type="button"
                    variant="ghost"
                    className="w-full text-sm"
                    onClick={() => {
                        setCode('');
                        setUseBackupCode(!useBackupCode);
                    }}
                    disabled={isLoading}
                >
                    {useBackupCode
                        ? 'Authenticator-App verwenden'
                        : 'Backup-Code verwenden'}
                </Button>

                <Button
                    type="button"
                    variant="link"
                    className="w-full text-sm text-muted-foreground"
                    onClick={onCancel}
                    disabled={isLoading}
                >
                    Abbrechen
                </Button>
            </div>
        </form>
    );
}
