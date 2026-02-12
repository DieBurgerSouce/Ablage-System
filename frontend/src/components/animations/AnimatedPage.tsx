/**
 * AnimatedPage - Wrapper für sanfte Seitenübergänge
 */
import { motion } from 'framer-motion'
import { pageTransition } from '@/lib/animations'
import type { ReactNode } from 'react'

interface AnimatedPageProps {
  children: ReactNode
  className?: string
}

export function AnimatedPage({ children, className }: AnimatedPageProps) {
  return (
    <motion.div
      initial={pageTransition.initial}
      animate={pageTransition.animate}
      exit={pageTransition.exit}
      className={className}
    >
      {children}
    </motion.div>
  )
}
