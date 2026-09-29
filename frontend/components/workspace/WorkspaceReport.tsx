"use client";
import { useCallback, useEffect, useState } from "react";
import {
  workspaceApi,
  type WorkspaceRun,
  type WorkspaceSSE,
  type WorkspaceStep,
  type WorkspaceStepOutput,
  type UpdateRefreshOutput,
  type ResearchOutput,
  type ValidationOutput,
  type ChallengeOutput,
  type DifferentiationOutput,
} from "@/lib/api";
import { VerdictBadge } from "./VerdictBadge";
import { UpdateRefreshCard } from "./StepCards/UpdateRefreshCard";
import { ResearchCard } from "./StepCards/ResearchCard";
import { ValidationCard } from "./StepCards/ValidationCard";
import { ChallengeCard } from "./StepCards/ChallengeCard";
import { DifferentiationCard } from "./StepCards/DifferentiationCard";

const STEP_LABELS: Record<WorkspaceStep, string> = {
  update_refresh:  "1. Update / Refresh",
  research:        "2. Research",
  validation:      "3. Validation",
  challenge:       "4. Challenge",
  differentiation: "5. Differentiation",
};

type StepResult = WorkspaceStepOutput | { error: string };

export function WorkspaceReport({ runId }: { runId: string }) {
  const [run, setRun] = useState<WorkspaceRun | null>(null);
  const [activeStep, setActiveStep] = useState<WorkspaceStep | null>(null);
  const [stepOutputs, setStepOutputs] = useState<Partial<Record<WorkspaceStep, StepResult>>>({});
  const [stepFailures, setStepFailures] = useState<Record<string, string>>({});
  const [verdict, setVerdict] = useState<WorkspaceRun["verdict"]>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // REST is the source of truth: on mount, and again when the run finishes
  // (for the saved model version, final status and error).
  const refresh = useCallback(() => {
    workspaceApi.get(runId).then((r) => {
      setRun(r);
      // Merge: outputs the stream already delivered win over an older snapshot.
      setStepOutputs((prev) => ({ ...r.step_outputs, ...prev }));
      setVerdict(r.verdict);
      if (r.error) setError(r.error);
    }).catch((e) => setLoadError(e instanceof Error ? e.message : String(e)));
  }, [runId]);

  useEffect(() => { refresh(); }, [refresh]);

  // Live updates, only while the run is going. A finished run has nothing to
  // stream, and the server closing its stream would make EventSource reconnect
  // in a loop. Transient errors are left to EventSource's own reconnect (they
  // used to close the stream for good).
  const running = run?.status === "running";
  useEffect(() => {
    if (!running) return;
    const es = new EventSource(workspaceApi.streamUrl(runId));

    es.onmessage = (msg) => {
      const evt: WorkspaceSSE = JSON.parse(msg.data);
      switch (evt.type) {
        case "workspace_run_start":
          break;
        case "step_start":
          setActiveStep(evt.step);
          break;
        case "step_complete":
          setStepOutputs((prev) => ({ ...prev, [evt.step]: evt.output }));
          break;
        case "step_failed":
          setStepFailures((prev) => ({ ...prev, [evt.step]: evt.error }));
          break;
        case "workspace_run_complete":
          setVerdict(evt.verdict);
          setActiveStep(null);
          es.close();
          refresh();
          break;
        case "workspace_run_failed":
          setError(evt.error);
          setActiveStep(null);
          es.close();
          refresh();
          break;
      }
    };

    return () => es.close();
  }, [runId, running, refresh]);

  if (loadError) {
    return (
      <div className="p-6 text-sm text-[var(--error-text)]">Couldn&apos;t load this workspace run: {loadError}</div>
    );
  }

  if (!run) {
    return (
      <div className="p-6 text-[var(--text-muted)]">Loading…</div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl p-6 space-y-6">
      <header className="flex items-baseline justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-[var(--text)]">
            {run.ticker} · workspace refresh
          </h1>
          <p className="text-sm text-[var(--text-muted)] mt-0.5">
            {run.ticker_model_version_before === 0 ? (
              <span className="text-[var(--text-faint)]">no model</span>
            ) : (
              <>
                v{run.ticker_model_version_before}
                {run.ticker_model_version_after
                  ? ` → v${run.ticker_model_version_after}`
                  : ""}
              </>
            )}{" "}
            · {new Date(run.created_at).toLocaleString()} · {run.status}
          </p>
        </div>
        <VerdictBadge verdict={verdict} />
      </header>

      {error && (
        <div className="rounded border border-[var(--error-border)] bg-[var(--error-bg)] text-[var(--error)] p-3 text-sm">
          Run failed: {error}
        </div>
      )}

      <div className="space-y-4">
        {(Object.keys(STEP_LABELS) as WorkspaceStep[]).map((step) => (
          <StepShell
            key={step}
            label={STEP_LABELS[step]}
            isActive={activeStep === step}
            output={stepOutputs[step]}
            failure={stepFailures[step]}
            step={step}
            ticker={run.ticker}
          />
        ))}
      </div>
    </div>
  );
}

function StepShell({
  label,
  isActive,
  output,
  failure,
  step,
  ticker,
}: {
  label: string;
  isActive: boolean;
  output: StepResult | undefined;
  failure?: string;
  step: WorkspaceStep;
  ticker: string;
}) {
  return (
    <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
      <header className="flex items-center justify-between">
        <h2 className="text-base font-medium text-[var(--text)]">{label}</h2>
        {isActive && (
          <span className="text-xs text-[var(--text-muted)]">running…</span>
        )}
        {failure && (
          <span className="text-xs text-[var(--error)]">failed: {failure}</span>
        )}
      </header>
      {output !== undefined && <StepBody step={step} output={output} ticker={ticker} />}
    </section>
  );
}

function StepBody({ step, output, ticker }: { step: WorkspaceStep; output: StepResult; ticker: string }) {
  if ("error" in output) {
    return (
      <pre className="mt-2 text-xs text-[var(--error)] overflow-x-auto">
        {output.error}
      </pre>
    );
  }
  if (step === "update_refresh") return <UpdateRefreshCard output={output as UpdateRefreshOutput} ticker={ticker} />;
  if (step === "research") return <ResearchCard output={output as ResearchOutput} />;
  if (step === "validation") return <ValidationCard output={output as ValidationOutput} ticker={ticker} />;
  if (step === "challenge") return <ChallengeCard output={output as ChallengeOutput} />;
  if (step === "differentiation") return <DifferentiationCard output={output as DifferentiationOutput} />;
  return (
    <pre className="mt-2 text-xs text-[var(--text-muted)] overflow-x-auto">
      {JSON.stringify(output, null, 2)}
    </pre>
  );
}
