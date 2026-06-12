import { motion, type HTMLMotionProps } from 'framer-motion';
import { tapScale } from '@/lib/animations';
import { motionTokens } from '@/lib/motion-tokens';
import { useReducedMotion } from '@/hooks/use-reduced-motion';
import { cn } from '@/lib/utils';
import { forwardRef } from 'react';

/** Button with tap-scale feedback */
export const AnimatedButton = forwardRef<
  HTMLButtonElement,
  HTMLMotionProps<'button'> & { className?: string }
>(function AnimatedButton({ className, children, ...props }, ref) {
  const reducedMotion = useReducedMotion();
  return (
    <motion.button
      ref={ref}
      className={className}
      {...(reducedMotion ? {} : tapScale)}
      {...props}
    >
      {children}
    </motion.button>
  );
});

/** Input with subtle glow on focus */
export const AnimatedInput = forwardRef<
  HTMLInputElement,
  HTMLMotionProps<'input'> & { className?: string }
>(function AnimatedInput({ className, ...props }, ref) {
  const reducedMotion = useReducedMotion();
  return (
    <motion.input
      ref={ref}
      className={cn(
        'transition-shadow duration-200 focus:ring-2 focus:ring-primary/20',
        className,
      )}
      {...(!reducedMotion && { whileFocus: { scale: 1.005 } })}
      {...props}
    />
  );
});

/** Badge with slide-up entrance animation */
interface AnimatedBadgeProps {
  children: React.ReactNode;
  className?: string;
  show?: boolean;
}

export function AnimatedBadge({
  children,
  className,
  show = true,
}: AnimatedBadgeProps) {
  const reducedMotion = useReducedMotion();

  if (!show) return null;

  return (
    <motion.span
      className={className}
      initial={
        reducedMotion ? undefined : { opacity: 0, y: 8, scale: 0.9 }
      }
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={
        reducedMotion
          ? undefined
          : { opacity: 0, y: -4, scale: 0.95 }
      }
      transition={{
        duration: motionTokens.duration.fast,
        ease: motionTokens.easing.standard,
      }}
    >
      {children}
    </motion.span>
  );
}
