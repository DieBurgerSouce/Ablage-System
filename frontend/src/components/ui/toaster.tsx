import { useToast } from './use-toast';
import { cn } from '@/lib/utils';
import { X, CheckCircle, AlertCircle, Info } from 'lucide-react';

export function Toaster() {
    const { toasts, dismiss } = useToast();

    if (toasts.length === 0) return null;

    return (
        <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
            {toasts.map((toast) => (
                <div
                    key={toast.id}
                    className={cn(
                        "relative flex items-start gap-3 p-4 rounded-lg border shadow-lg bg-background",
                        "animate-in slide-in-from-right-full duration-300",
                        toast.variant === 'destructive' && "border-destructive/50 bg-destructive/5",
                        toast.variant === 'success' && "border-emerald-500/50 bg-emerald-500/5"
                    )}
                >
                    {/* Icon */}
                    <div className="flex-shrink-0 mt-0.5">
                        {toast.variant === 'destructive' && (
                            <AlertCircle className="w-5 h-5 text-destructive" />
                        )}
                        {toast.variant === 'success' && (
                            <CheckCircle className="w-5 h-5 text-emerald-500" />
                        )}
                        {(!toast.variant || toast.variant === 'default') && (
                            <Info className="w-5 h-5 text-blue-500" />
                        )}
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                        {toast.title && (
                            <p className={cn(
                                "font-medium text-sm",
                                toast.variant === 'destructive' && "text-destructive",
                                toast.variant === 'success' && "text-emerald-600 dark:text-emerald-400"
                            )}>
                                {toast.title}
                            </p>
                        )}
                        {toast.description && (
                            <p className="text-sm text-muted-foreground mt-0.5">
                                {toast.description}
                            </p>
                        )}
                    </div>

                    {/* Close button */}
                    <button
                        onClick={() => dismiss(toast.id)}
                        className="flex-shrink-0 p-1 rounded hover:bg-muted transition-colors"
                    >
                        <X className="w-4 h-4 text-muted-foreground" />
                    </button>
                </div>
            ))}
        </div>
    );
}
