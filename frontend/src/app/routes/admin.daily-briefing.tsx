/**
 * Admin Daily Briefing Route
 *
 * KI-Tagesbriefing mit proaktiven Insights.
 */

import { createFileRoute } from "@tanstack/react-router";
import { DailyBriefingPage } from "@/features/daily-briefing";

export const Route = createFileRoute("/admin/daily-briefing")({
  component: DailyBriefingPage,
});
