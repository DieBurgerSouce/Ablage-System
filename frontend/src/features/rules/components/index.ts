/**
 * Business Rules Components
 *
 * Re-Exports aus dem Admin-Rules-Modul.
 */

export {
  RuleTable,
  RuleFormDialog,
  ConditionBuilder,
  ActionBuilder,
  AIRuleGenerator,
  RuleTestPanel,
  RuleTemplateGallery,
} from '@/features/admin/rules/components'

// Re-export RulesAdminPage under a more generic name
export { RulesAdminPage as RuleBuilderView } from '@/features/admin/rules/RulesAdminPage'
