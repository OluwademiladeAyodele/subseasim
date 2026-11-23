import { useEffect, useState } from "react";
import { Check, Circle, CircleDot } from "lucide-react";

import { Badge, Button } from "@/components/ui/primitives";
import type { ExerciseSummary, TrainingState } from "@/types/simulation";

interface Props {
  training: TrainingState | null;
  exercises: ExerciseSummary[];
  onStart: (id: string) => void;
  onAnswer: (stepId: string, choice: string) => void;
  onAdvance: () => void;
  onStop: () => void;
}

function List({ items }: { items: string[] }) {
  return (
    <ul className="ml-4 list-disc space-y-0.5 text-fg">
      {items.map((x) => (
        <li key={x}>{x}</li>
      ))}
    </ul>
  );
}

function H({ children }: { children: React.ReactNode }) {
  return <h4 className="mb-1 mt-3 t-eyebrow">{children}</h4>;
}

export function TrainingPanel({ training, exercises, onStart, onAnswer, onAdvance, onStop }: Props) {
  if (!training) {
    return (
      <div className="p-4" data-testid="training-panel">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="t-heading">Intern curriculum</h2>
          <p className="text-[12.5px] text-dim">Work through the exercises in order; each one loads its own scenario.</p>
        </div>
        <ol className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(320px,1fr))]">
          {[...exercises].sort((a, b) => a.number - b.number).map((ex) => (
            <li key={ex.id} className="flex flex-col rounded-xl border border-line bg-panel p-4 shadow-[var(--shadow-card)]" data-testid={`exercise-${ex.id}`}>
              <div className="flex items-start gap-3">
                <span className="num grid h-8 w-8 shrink-0 place-items-center rounded-full bg-accent/10 text-[14px] font-semibold text-accent" aria-hidden>{ex.number}</span>
                <div className="min-w-0">
                  <div className="font-semibold leading-snug">{ex.title.replace(/^Exercise \d+\s*-\s*/, "")}</div>
                  <div className="text-[12px] text-dim">Exercise {ex.number} · {ex.step_count} steps</div>
                </div>
              </div>
              <H>You will learn to</H>
              <List items={ex.objectives} />
              <div className="mt-auto flex justify-end pt-3">
                <Button variant="primary" size="sm" onClick={() => onStart(ex.id)} aria-label={`Start ${ex.title}`} data-testid={`start-${ex.id}`}>Start exercise</Button>
              </div>
            </li>
          ))}
        </ol>
      </div>
    );
  }
  return <ActiveExercise t={training} onAnswer={onAnswer} onAdvance={onAdvance} onStop={onStop} />;
}

function ActiveExercise({ t, onAnswer, onAdvance, onStop }: { t: TrainingState; onAnswer: Props["onAnswer"]; onAdvance: () => void; onStop: () => void }) {
  const c = t.current;
  const [choice, setChoice] = useState<string | null>(null);
  useEffect(() => setChoice(null), [c.id]);
  const answered = !!c.response;
  const canContinue = c.kind === "info" || c.kind === "review" || c.complete;

  return (
    <div className="flex h-full flex-col" data-testid="training-panel">
      <div className="border-b border-line bg-panel-2 px-3 py-2">
        <div className="flex items-center justify-between gap-2">
          <span className="font-bold">{t.exercise.title}</span>
          <Button variant="ghost" size="xs" onClick={onStop}>Close</Button>
        </div>
        <ol className="mt-1.5 flex flex-wrap gap-x-2 gap-y-0.5">
          {t.steps.map((s, i) => (
            <li key={s.id} title={s.title} className="flex items-center gap-0.5 text-[11.5px] text-dim">
              {s.status === "complete" ? <Check size={11} className="text-ok" /> : s.status === "current" ? <CircleDot size={11} className="text-accent" /> : <Circle size={11} />}
              {i + 1}
            </li>
          ))}
        </ol>
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-3">
        <div className="mb-1 flex items-center gap-2">
          <Badge tone="accent">{c.kind}</Badge>
          <span className="font-bold" data-testid="training-step-title">{c.title}</span>
        </div>
        {c.body && <p className="whitespace-pre-line text-fg">{c.body}</p>}

        {c.id === "intro" && (
          <>
            <H>Learning objectives</H>
            <List items={t.exercise.objectives} />
            <H>Initial system configuration</H>
            <List items={t.exercise.initial_configuration} />
            <H>Operating instructions</H>
            <List items={t.exercise.instructions} />
            <H>Expected observations</H>
            <List items={t.exercise.expected_observations} />
          </>
        )}

        {c.kind === "task" && (
          <div className={`mt-3 border p-2 ${c.complete ? "border-ok/50 bg-ok/5" : "border-line bg-panel-2"}`} data-testid="task-status">
            {c.complete ? (
              <span className="text-ok">Task complete — observations recorded from the simulation.</span>
            ) : (
              <span className="text-warn">{c.hint ?? "Waiting for the required simulation state…"}</span>
            )}
          </div>
        )}

        {(c.kind === "prediction" || c.kind === "question") && (
          <div className="mt-3 space-y-1.5" role="radiogroup" aria-label={c.title}>
            {c.options?.map((o) => {
              const chosen = (c.response?.choice ?? choice) === o.id;
              const isCorrect = c.response?.correct_option === o.id;
              const border = answered && c.kind === "question" ? (isCorrect ? "border-ok" : chosen ? "border-bad" : "border-line") : chosen ? "border-accent" : "border-line";
              return (
                <button
                  key={o.id}
                  type="button"
                  role="radio"
                  aria-checked={chosen}
                  disabled={answered}
                  onClick={() => setChoice(o.id)}
                  className={`block w-full border ${border} bg-panel-2 px-2 py-1.5 text-left hover:bg-panel-3 disabled:cursor-default`}
                >
                  <span className="num mr-2 font-bold text-accent">{o.id.toUpperCase()}</span>
                  {o.text}
                </button>
              );
            })}
            {!answered && (
              <div className="flex justify-end">
                <Button variant="primary" size="sm" disabled={!choice} onClick={() => choice && onAnswer(c.id, choice)}>
                  {c.kind === "prediction" ? "Lock in prediction" : "Submit answer"}
                </Button>
              </div>
            )}
            {answered && c.kind === "prediction" && (
              <p className="text-info">Prediction recorded. It will be compared with the simulation result after you perform the operation.</p>
            )}
            {answered && c.kind === "question" && (
              <div className={`border p-2 ${c.response?.correct ? "border-ok/50 bg-ok/5" : "border-bad/50 bg-bad/5"}`} data-testid="question-feedback">
                <div className={c.response?.correct ? "font-bold text-ok" : "font-bold text-bad"}>{c.response?.correct ? "Correct" : "Not correct"}</div>
                <p className="mt-1">{c.response?.explanation}</p>
              </div>
            )}
          </div>
        )}

        {c.kind === "review" && c.review && (
          <div className="mt-2" data-testid="training-review">
            <p className="whitespace-pre-line">{c.review.text}</p>
            {c.review.table && <ReviewTable table={c.review.table} />}
          </div>
        )}

        {c.kind === "summary" && <Summary t={t} />}
      </div>

      {c.kind !== "summary" && (
        <div className="flex justify-end border-t border-line p-2">
          <Button variant="primary" size="sm" disabled={!canContinue} onClick={onAdvance}>Continue</Button>
        </div>
      )}
    </div>
  );
}

function ReviewTable({ table }: { table: { columns: string[]; rows: (string | number)[][]; emphasis_rows?: number[] } }) {
  return (
    <table className="mt-2 w-full border-collapse text-[12.5px]">
      <thead>
        <tr>
          {table.columns.map((c) => (
            <th key={c} className="border-b border-line px-1 py-0.5 text-left text-dim">
              {c}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {table.rows.map((r, i) => (
          <tr key={i} className={table.emphasis_rows?.includes(i) ? "font-semibold" : ""}>
            {r.map((v, j) => (
              <td key={j} className={`border-b border-line/50 px-1 py-0.5 ${j ? "num text-right" : "text-muted"}`}>
                {typeof v === "number" ? v.toFixed(1) : v}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Summary({ t }: { t: TrainingState }) {
  const s = t.score;
  return (
    <div className="mt-2 space-y-3" data-testid="training-summary">
      <div className="grid grid-cols-2 gap-2">
        <div className="border border-line bg-panel-2 p-2">
          <div className="text-[11.5px] font-bold uppercase text-dim">Assessment questions</div>
          <div className="num text-xl">
            {s.questions_correct} / {s.questions_total}
          </div>
        </div>
        <div className="border border-line bg-panel-2 p-2">
          <div className="text-[11.5px] font-bold uppercase text-dim">Predictions matching result</div>
          <div className="num text-xl">
            {s.predictions_correct} / {s.predictions_resolved}
          </div>
        </div>
      </div>
      <div>
        <H>Predictions vs simulation</H>
        {t.summary?.predictions.map((p) => (
          <div key={p.step_id} className="mb-2 border-l-2 pl-2" style={{ borderColor: p.correct ? "var(--color-ok)" : "var(--color-warn)" }}>
            <div className="font-bold">{p.title}</div>
            <div>
              You predicted: <span className="text-accent">{p.choice_text}</span>. Simulation: <span className="text-fg">{p.correct_text ?? "unresolved"}</span>
            </div>
            {p.explanation && <p className="text-[12.5px] text-muted">{p.explanation}</p>}
          </div>
        ))}
      </div>
      <div>
        <H>Questions</H>
        {t.summary?.questions.map((q) => (
          <div key={q.step_id} className="mb-1">
            <span className={q.correct ? "text-ok" : "text-bad"}>{q.correct ? "✓" : "✗"}</span> {q.title}
          </div>
        ))}
      </div>
      <p className="text-[12.5px] text-dim">
        Duration {Math.round((t.summary?.duration_s ?? 0) / 60)} min. Explanations refer to this simulation run with illustrative data; they are not real-world
        operating instructions.
      </p>
    </div>
  );
}
