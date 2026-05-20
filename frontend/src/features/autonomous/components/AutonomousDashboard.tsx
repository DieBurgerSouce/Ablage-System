/**
 * Autonomous Dashboard Component
 * Main dashboard with tabs for overview, queue, history, and settings
 */

import { motion } from 'framer-motion';
import { Shield, Clock, Activity, Settings } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { TrustLevelPanel } from './TrustLevelPanel';
import { DelayedAcceptanceQueue } from './DelayedAcceptanceQueue';
import { ActionLog } from './ActionLog';
import { RollbackPanel } from './RollbackPanel';
import { ConfidenceOverview } from './ConfidenceOverview';
import { usePendingApprovals } from '../hooks/useAutonomous';

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.5,
      ease: 'easeOut',
    },
  },
};

export function AutonomousDashboard() {
  const { data: pendingApprovals } = usePendingApprovals({ limit: 5 });

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="space-y-6 p-6"
    >
      {/* Header */}
      <motion.div variants={itemVariants}>
        <h1 className="text-3xl font-bold tracking-tight">Autonomes System</h1>
        <p className="text-muted-foreground mt-2">
          Verwalten Sie Vertrauensstufen, überwachen Sie KI-Entscheidungen und überprüfen Sie
          ausstehende Genehmigungen
        </p>
      </motion.div>

      {/* Main Tabs */}
      <motion.div variants={itemVariants}>
        <Tabs defaultValue="overview" className="space-y-4">
          <TabsList className="grid w-full grid-cols-4 lg:w-[600px]" aria-label="Autonomes System Tabs">
            <TabsTrigger value="overview" className="flex items-center gap-2" aria-label="Übersicht anzeigen">
              <Shield className="h-4 w-4" />
              <span>Übersicht</span>
            </TabsTrigger>
            <TabsTrigger value="queue" className="flex items-center gap-2" aria-label="Warteschlange anzeigen">
              <Clock className="h-4 w-4" />
              <span>
                Warteschlange
                {pendingApprovals && pendingApprovals.length > 0 && (
                  <span className="ml-1 rounded-full bg-primary px-2 py-0.5 text-xs text-primary-foreground">
                    {pendingApprovals.length}
                  </span>
                )}
              </span>
            </TabsTrigger>
            <TabsTrigger value="history" className="flex items-center gap-2" aria-label="Verlauf anzeigen">
              <Activity className="h-4 w-4" />
              <span>Verlauf</span>
            </TabsTrigger>
            <TabsTrigger value="settings" className="flex items-center gap-2" aria-label="Einstellungen anzeigen">
              <Settings className="h-4 w-4" />
              <span>Einstellungen</span>
            </TabsTrigger>
          </TabsList>

          {/* Overview Tab */}
          <TabsContent value="overview" className="space-y-6">
            <motion.div
              variants={containerVariants}
              initial="hidden"
              animate="visible"
              className="space-y-6"
            >
              {/* Statistics */}
              <motion.div variants={itemVariants}>
                <ConfidenceOverview />
              </motion.div>

              {/* Trust Level + Queue Preview */}
              <div className="grid gap-6 lg:grid-cols-2">
                <motion.div variants={itemVariants}>
                  <TrustLevelPanel />
                </motion.div>

                <motion.div variants={itemVariants}>
                  <DelayedAcceptanceQueue />
                </motion.div>
              </div>

              {/* Rollback Panel */}
              <motion.div variants={itemVariants}>
                <RollbackPanel />
              </motion.div>
            </motion.div>
          </TabsContent>

          {/* Queue Tab */}
          <TabsContent value="queue" className="space-y-6">
            <motion.div
              variants={containerVariants}
              initial="hidden"
              animate="visible"
              className="space-y-6"
            >
              <motion.div variants={itemVariants}>
                <DelayedAcceptanceQueue />
              </motion.div>
            </motion.div>
          </TabsContent>

          {/* History Tab */}
          <TabsContent value="history" className="space-y-6">
            <motion.div
              variants={containerVariants}
              initial="hidden"
              animate="visible"
              className="space-y-6"
            >
              <motion.div variants={itemVariants}>
                <ActionLog />
              </motion.div>

              <motion.div variants={itemVariants}>
                <RollbackPanel />
              </motion.div>
            </motion.div>
          </TabsContent>

          {/* Settings Tab */}
          <TabsContent value="settings" className="space-y-6">
            <motion.div
              variants={containerVariants}
              initial="hidden"
              animate="visible"
              className="space-y-6"
            >
              <motion.div variants={itemVariants}>
                <TrustLevelPanel />
              </motion.div>

              <motion.div variants={itemVariants}>
                <ConfidenceOverview />
              </motion.div>
            </motion.div>
          </TabsContent>
        </Tabs>
      </motion.div>
    </motion.div>
  );
}
