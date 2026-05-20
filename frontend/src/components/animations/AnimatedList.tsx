/**
 * AnimatedList - Gestaffelte Listenanimation
 */
import { motion } from 'framer-motion'
import { staggerContainer, staggerItem } from '@/lib/animations'
import type { ReactNode } from 'react'

interface AnimatedListProps {
  children: ReactNode
  className?: string
}

export function AnimatedList({ children, className }: AnimatedListProps) {
  return (
    <motion.div
      variants={staggerContainer}
      initial="initial"
      animate="animate"
      className={className}
    >
      {children}
    </motion.div>
  )
}

interface AnimatedListItemProps {
  children: ReactNode
  className?: string
}

export function AnimatedListItem({ children, className }: AnimatedListItemProps) {
  return (
    <motion.div variants={staggerItem} className={className}>
      {children}
    </motion.div>
  )
}
