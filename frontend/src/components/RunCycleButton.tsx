import React, { useState } from 'react';
import { Play, RefreshCw, CheckCircle2, AlertCircle } from 'lucide-react';
import { useTriggerRunCycle } from '../api/queries';

export interface RunCycleButtonProps {
  isRunning?: boolean;
  onCycleTriggered?: (cycleId: string) => void;
  className?: string;
}

export const RunCycleButton: React.FC<RunCycleButtonProps> = ({
  isRunning = false,
  onCycleTriggered,
  className = '',
}) => {
  const triggerMutation = useTriggerRunCycle();
  const [lastSuccessMessage, setLastSuccessMessage] = useState<string | null>(null);

  const isPending = isRunning || triggerMutation.isPending;

  const handleClick = async () => {
    if (isPending) return;

    try {
      const res = await triggerMutation.mutateAsync();
      setLastSuccessMessage(`Cycle ${res.cycle_id} initiated`);
      if (onCycleTriggered) {
        onCycleTriggered(res.cycle_id);
      }
    } catch {
      // Error handled by triggerMutation.error
    }
  };

  return (
    <div className={`flex flex-col items-end gap-1.5 ${className}`}>
      <button
        onClick={handleClick}
        disabled={isPending}
        className={`px-4 py-2 text-xs font-mono font-bold uppercase transition-all duration-150 flex items-center gap-2 border ${
          isPending
            ? 'bg-[var(--brand-spruce)]/50 border-[var(--brand-spruce)]/50 text-white cursor-not-allowed opacity-80'
            : 'bg-[var(--brand-spruce)] hover:bg-[#143225] border-[var(--brand-spruce)] text-white shadow-sm active:scale-98 cursor-pointer'
        }`}
        data-testid="run-cycle-button"
        title={isPending ? 'Cycle is currently running' : 'Trigger autonomous hedge assessment cycle'}
      >
        {isPending ? (
          <>
            <RefreshCw className="w-3.5 h-3.5 animate-spin text-[#A67C37]" />
            <span>Cycle Executing...</span>
          </>
        ) : (
          <>
            <Play className="w-3.5 h-3.5 text-[#A67C37] fill-[#A67C37]" />
            <span>Run Autonomous Cycle</span>
          </>
        )}
      </button>

      {/* Success notification */}
      {lastSuccessMessage && !isPending && !triggerMutation.error && (
        <span
          className="text-[10px] font-mono text-[var(--status-safe)] flex items-center gap-1"
          data-testid="cycle-success-feedback"
        >
          <CheckCircle2 className="w-3 h-3" />
          {lastSuccessMessage}
        </span>
      )}

      {/* Error notification */}
      {triggerMutation.error && (
        <span
          className="text-[10px] font-mono text-[var(--status-danger)] flex items-center gap-1"
          data-testid="cycle-error-feedback"
        >
          <AlertCircle className="w-3 h-3" />
          Trigger failed: {triggerMutation.error.message}
        </span>
      )}
    </div>
  );
};
