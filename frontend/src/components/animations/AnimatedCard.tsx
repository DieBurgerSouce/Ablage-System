/**
 * AnimatedCard - Karte mit Hover- und Tap-Animationen
 */
import { motion } from 'framer-motion'
import { hoverLift, tapScale } from '@/lib/animations'
import { cn } from '@/lib/utils'
import type { ReactNode } from 'react'

interface AnimatedCardProps {
  children: ReactNode
  className?: string
  onClick?: () => void
}

export function AnimatedCard({ children, className, onClick }: AnimatedCardProps) {
  return (
    <motion.div
      {...hoverLift}
      {...tapScale}
      onClick={onClick}
      className={cn(
        'rounded-lg border bg-card text-card-foreground shadow-sm transition-shadow hover:shadow-md',
        onClick && 'cursor-pointer',
        className
      )}
    >
      {children}
    </motion.div>
  )
}
