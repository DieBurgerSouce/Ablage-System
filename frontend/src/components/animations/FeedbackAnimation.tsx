import { motion } from 'framer-motion';
import { successPulse } from '@/lib/animations';
import { motionTokens } from '@/lib/motion-tokens';
import { useReducedMotion } from '@/hooks/use-reduced-motion';
import { Check, X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface FeedbackAnimationProps {
  className?: string;
}

/** Green checkmark with success pulse */
export function SuccessAnimation({ className }: FeedbackAnimationProps) {
  const reducedMotion = useReducedMotion();
  return (
    <motion.div
      className={cn(
        'inline-flex items-center justify-center rounded-full bg-green-100 p-2 text-green-600',
        className,
      )}
      {...(reducedMotion ? {} : successPulse)}
    >
      <Check className="h-5 w-5" />
    </motion.div>
  );
}

/** Red X with shake spring */
export function ErrorAnimation({ className }: FeedbackAnimationProps) {
  const reducedMotion = useReducedMotion();
  return (
    <motion.div
      className={cn(
        'inline-flex items-center justify-center rounded-full bg-red-100 p-2 text-red-600',
        className,
      )}
      initial={reducedMotion ? undefined : { x: 0 }}
      animate={
        reducedMotion
          ? undefined
          : {
              x: [0, -6, 6, -4, 4, -2, 2, 0],
              transition: {
                duration: 0.4,
                type: 'spring',
                ...motionTokens.spring.snappy,
              },
            }
      }
    >
      <X className="h-5 w-5" />
    </motion.div>
  );
}

/** Skeleton to content transition */
export function LoadingComplete({
  children,
  isLoaded,
  className,
}: {
  children: React.ReactNode;
  isLoaded: boolean;
  className?: string;
}) {
  const reducedMotion = useReducedMotion();

  if (reducedMotion) {
    return <div className={className}>{children}</div>;
  }

  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, filter: 'blur(4px)' }}
      animate={
        isLoaded
          ? { opacity: 1, filter: 'blur(0px)' }
          : { opacity: 0.5 }
      }
      transition={{ duration: motionTokens.duration.normal }}
    >
      {children}
    </motion.div>
  );
}
