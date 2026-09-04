/**
 * Demand Analytics data hook (M99-FL).
 *
 * Thin React wrapper over `stores/analyticsStore`. Exposes the summary, active
 * filters, load state, and the filter/fetch actions so the Demand Analytics
 * page stays declarative. A fetch is triggered by the page on mount / when the
 * RBAC permission is satisfied.
 */
import { useAnalyticsStore } from "@/stores/analyticsStore";

export function useAnalytics() {
  const filters = useAnalyticsStore((s) => s.filters);
  const summary = useAnalyticsStore((s) => s.summary);
  const isLoading = useAnalyticsStore((s) => s.isLoading);
  const error = useAnalyticsStore((s) => s.error);
  const setFilters = useAnalyticsStore((s) => s.setFilters);
  const fetch = useAnalyticsStore((s) => s.fetch);
  const reset = useAnalyticsStore((s) => s.reset);

  return { filters, summary, isLoading, error, setFilters, fetch, reset };
}
