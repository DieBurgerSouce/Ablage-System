/**
 * SuccessCheck - Animiertes Erfolgshäkchen
 */
import { motion } from 'framer-motion'
import { successPulse, prefersReducedMotion } from '@/lib/animations'
import { CheckCircle2 } from 'lucide-react'
import { cn } from '@/lib/utils'

interface SuccessCheckProps {
  className?: string
  size?: number
}

export function SuccessCheck({ className, size = 48 }: SuccessCheckProps) {
  if (prefersReducedMotion) {
    return <CheckCircle2 className={cn('text-green-500', className)} style={{ width: size, height: size }} />
  }

  return (
    <motion.div
      initial={successPulse.initial}
      animate={successPulse.animate}
      className={className}
    >
      <CheckCircle2 className="text-green-500" style={{ width: size, height: size }} />
    </motion.div>
  )
}
