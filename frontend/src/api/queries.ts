/**
 * React Query Hooks for Agent-State Contracts — Task P1-FE-7 (Git Issue #41).
 *
 * Provides typed data fetching hooks wired to the backend API & stub endpoints:
 * - `useHedgeContext`: Fetches standardized hedge context (Contract 1)
 * - `useStrategyDecision`: Fetches current Strategy Manager decision (Contract 3)
 * - `useStrategyHypothesis`: Fetches a single strategy hypothesis (Contract 2)
 * - `useRiskDecision`: Fetches risk gate decision (Contract 4)
 * - `useExecutionPlan`: Fetches multi-leg execution plan (Contract 5)
 * - `useExecutionResult`: Fetches execution result report (Contract 6)
 * - `useMonitoringState`: Fetches rolling monitoring state (Contract 7)
 * - `useHealth`: Fetches service health and build info
 */

import { useQuery, useMutation, type UseQueryOptions, type UseMutationOptions } from '@tanstack/react-query';
import { apiClient } from './client';
import type {
  AlpacaAccount,
  AlpacaHistoryResponse,
  HedgeContext,
  PortfolioState,
  StrategyDecision,
  StrategyHypothesis,
  RiskDecision,
  ExecutionPlan,
  ExecutionResult,
  MonitoringState,
  HealthResponse,
  AgentRun,
  WorkflowState,
  RunCycleResponse,
} from './types';

export const queryKeys = {
  health: ['health'] as const,
  context: ['context'] as const,
  portfolioLatest: ['portfolio', 'latest'] as const,
  alpacaAccount: (accountId?: string) => ['alpaca', 'account', accountId ?? 'default'] as const,
  alpacaHistory: (accountId?: string, period?: string, timeframe?: string) =>
    ['alpaca', 'history', accountId ?? 'default', period ?? '1W', timeframe ?? '1H'] as const,
  agentRuns: (cycleId?: string) => ['agentRuns', cycleId ?? 'all'] as const,
  strategy: (cycleId?: string) => ['strategy', cycleId ?? 'latest'] as const,
  strategyHypotheses: (cycleId?: string) => ['strategy', 'hypotheses', cycleId ?? 'latest'] as const,
  strategyHypothesis: (id?: string) => ['strategy', 'hypothesis', id ?? 'selected'] as const,
  risk: (cycleId?: string) => ['risk', cycleId ?? 'latest'] as const,
  riskChecks: (cycleId?: string) => ['risk', 'checks', cycleId ?? 'latest'] as const,
  executionPlan: ['execution', 'plan'] as const,
  executionResult: (cycleId?: string) => ['execution', 'result', cycleId ?? 'latest'] as const,
  orders: (cycleId?: string) => ['orders', cycleId ?? 'latest'] as const,
  monitoring: ['monitoring'] as const,
  workflow: (cycleId?: string) => ['workflow', cycleId ?? 'latest'] as const,
};

export function useHedgeContext(
  options?: Partial<UseQueryOptions<HedgeContext, Error>>
) {
  return useQuery<HedgeContext, Error>({
    queryKey: queryKeys.context,
    queryFn: () => apiClient.get<HedgeContext>('/context'),
    ...options,
  });
}

export function usePortfolioLatest(
  options?: Partial<UseQueryOptions<PortfolioState, Error>>
) {
  return useQuery<PortfolioState, Error>({
    queryKey: queryKeys.portfolioLatest,
    queryFn: async () => {
      try {
        return await apiClient.get<PortfolioState>('/portfolio/latest');
      } catch {
        // Fallback to /context portfolio_state if /portfolio/latest is not standalone
        const ctx = await apiClient.get<HedgeContext>('/context');
        return ctx.portfolio_state;
      }
    },
    ...options,
  });
}

export function useAlpacaAccount(
  accountId?: string,
  options?: Partial<UseQueryOptions<AlpacaAccount, Error>>
) {
  return useQuery<AlpacaAccount, Error>({
    queryKey: queryKeys.alpacaAccount(accountId),
    queryFn: () =>
      apiClient.get<AlpacaAccount>(
        accountId ? `/alpaca/account?account_id=${encodeURIComponent(accountId)}` : '/alpaca/account'
      ),
    refetchInterval: 5000,
    ...options,
  });
}

export function useAlpacaHistory(
  accountId?: string,
  period: string = '1W',
  timeframe: string = '1H',
  options?: Partial<UseQueryOptions<AlpacaHistoryResponse, Error>>
) {
  return useQuery<AlpacaHistoryResponse, Error>({
    queryKey: queryKeys.alpacaHistory(accountId, period, timeframe),
    queryFn: () => {
      const params = new URLSearchParams();
      if (accountId) params.set('account_id', accountId);
      params.set('period', period);
      params.set('timeframe', timeframe);
      return apiClient.get<AlpacaHistoryResponse>(`/alpaca/history?${params.toString()}`);
    },
    refetchInterval: 15000,
    ...options,
  });
}

export function useAgentRuns(
  cycleId?: string,
  options?: Partial<UseQueryOptions<AgentRun[], Error>>
) {
  return useQuery<AgentRun[], Error>({
    queryKey: queryKeys.agentRuns(cycleId),
    queryFn: () =>
      apiClient.get<AgentRun[]>(
        cycleId ? `/agent-runs?cycle_id=${encodeURIComponent(cycleId)}` : '/agent-runs'
      ),
    ...options,
  });
}

export function useStrategyDecision(
  cycleId?: string,
  options?: Partial<UseQueryOptions<StrategyDecision, Error>>
) {
  return useQuery<StrategyDecision, Error>({
    queryKey: queryKeys.strategy(cycleId),
    queryFn: () =>
      apiClient.get<StrategyDecision>(
        cycleId ? `/strategy/decision?cycle_id=${encodeURIComponent(cycleId)}` : '/strategy'
      ),
    ...options,
  });
}

export function useStrategyHypotheses(
  cycleId?: string,
  options?: Partial<UseQueryOptions<StrategyHypothesis[], Error>>
) {
  return useQuery<StrategyHypothesis[], Error>({
    queryKey: queryKeys.strategyHypotheses(cycleId),
    queryFn: () =>
      apiClient.get<StrategyHypothesis[]>(
        cycleId ? `/strategy/hypotheses?cycle_id=${encodeURIComponent(cycleId)}` : '/strategy/hypotheses'
      ),
    ...options,
  });
}

export function useStrategyHypothesis(
  id?: string,
  options?: Partial<UseQueryOptions<StrategyHypothesis, Error>>
) {
  return useQuery<StrategyHypothesis, Error>({
    queryKey: queryKeys.strategyHypothesis(id),
    queryFn: async () => {
      if (!id || id === 'selected') {
        return apiClient.get<StrategyHypothesis>('/strategy/hypothesis');
      }
      try {
        return await apiClient.get<StrategyHypothesis>(
          `/strategy/hypotheses/${encodeURIComponent(id)}`
        );
      } catch {
        return await apiClient.get<StrategyHypothesis>('/strategy/hypothesis');
      }
    },
    ...options,
  });
}

export function useRiskDecision(
  cycleId?: string,
  options?: Partial<UseQueryOptions<RiskDecision, Error>>
) {
  return useQuery<RiskDecision, Error>({
    queryKey: queryKeys.risk(cycleId),
    queryFn: () =>
      apiClient.get<RiskDecision>(
        cycleId ? `/risk?cycle_id=${encodeURIComponent(cycleId)}` : '/risk'
      ),
    ...options,
  });
}

export function useRiskChecks(
  cycleId?: string,
  options?: Partial<UseQueryOptions<RiskDecision, Error>>
) {
  return useQuery<RiskDecision, Error>({
    queryKey: queryKeys.riskChecks(cycleId),
    queryFn: () =>
      apiClient.get<RiskDecision>(
        cycleId ? `/risk/checks?cycle_id=${encodeURIComponent(cycleId)}` : '/risk/checks'
      ),
    ...options,
  });
}

export function useExecutionPlan(
  options?: Partial<UseQueryOptions<ExecutionPlan, Error>>
) {
  return useQuery<ExecutionPlan, Error>({
    queryKey: queryKeys.executionPlan,
    queryFn: () => apiClient.get<ExecutionPlan>('/execution/plan'),
    ...options,
  });
}

export function useExecutionResult(
  cycleId?: string,
  options?: Partial<UseQueryOptions<ExecutionResult, Error>>
) {
  return useQuery<ExecutionResult, Error>({
    queryKey: queryKeys.executionResult(cycleId),
    queryFn: () =>
      apiClient.get<ExecutionResult>(
        cycleId ? `/execution?cycle_id=${encodeURIComponent(cycleId)}` : '/execution'
      ),
    ...options,
  });
}

export function useOrders(
  cycleId?: string,
  options?: Partial<UseQueryOptions<ExecutionResult, Error>>
) {
  return useQuery<ExecutionResult, Error>({
    queryKey: queryKeys.orders(cycleId),
    queryFn: () =>
      apiClient.get<ExecutionResult>(
        cycleId ? `/orders?cycle_id=${encodeURIComponent(cycleId)}` : '/orders'
      ),
    ...options,
  });
}

export function useMonitoringState(
  options?: Partial<UseQueryOptions<MonitoringState, Error>>
) {
  return useQuery<MonitoringState, Error>({
    queryKey: queryKeys.monitoring,
    queryFn: () => apiClient.get<MonitoringState>('/monitoring'),
    ...options,
  });
}

export function useWorkflowState(
  cycleId?: string,
  options?: Partial<UseQueryOptions<WorkflowState, Error>>
) {
  return useQuery<WorkflowState, Error>({
    queryKey: queryKeys.workflow(cycleId),
    queryFn: () =>
      apiClient.get<WorkflowState>(
        cycleId ? `/workflow-state?cycle_id=${encodeURIComponent(cycleId)}` : '/workflow-state'
      ),
    refetchInterval: 3000,
    ...options,
  });
}

export function useTriggerRunCycle(
  options?: UseMutationOptions<RunCycleResponse, Error, { force?: boolean } | void>
) {
  return useMutation<RunCycleResponse, Error, { force?: boolean } | void>({
    mutationFn: (vars) => apiClient.post<RunCycleResponse>('/run-cycle', vars ?? {}),
    ...options,
  });
}

export function useHealth(
  options?: Partial<UseQueryOptions<HealthResponse, Error>>
) {
  return useQuery<HealthResponse, Error>({
    queryKey: queryKeys.health,
    queryFn: () => apiClient.get<HealthResponse>('/health'),
    ...options,
  });
}

export function usePnlCurrent(
  options?: Partial<UseQueryOptions<any, Error>>
) {
  return useQuery<any, Error>({
    queryKey: ['pnl', 'current'],
    queryFn: () => apiClient.get<any>('/pnl/current'),
    ...options,
  });
}

export function usePnlSeries(
  cycleId?: string,
  options?: Partial<UseQueryOptions<any[], Error>>
) {
  return useQuery<any[], Error>({
    queryKey: ['pnl', 'series', cycleId ?? 'all'],
    queryFn: () =>
      apiClient.get<any[]>(
        cycleId ? `/pnl/series?cycle_id=${encodeURIComponent(cycleId)}` : '/pnl/series'
      ),
    ...options,
  });
}

export function useMonitoringEvents(
  cycleId?: string,
  options?: Partial<UseQueryOptions<any[], Error>>
) {
  return useQuery<any[], Error>({
    queryKey: ['monitoring', 'events', cycleId ?? 'all'],
    queryFn: () =>
      apiClient.get<any[]>(
        cycleId ? `/monitoring/events?cycle_id=${encodeURIComponent(cycleId)}` : '/monitoring/events'
      ),
    ...options,
  });
}



