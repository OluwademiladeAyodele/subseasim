/**
 * UI primitives (shadcn/ui-style, copied in). Light "workstation" theme:
 * white cards on a soft canvas, rounded 8 px, sentence-case labels, press
 * feedback on pointer-down.
 */
import * as React from "react";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import * as SliderPrimitive from "@radix-ui/react-slider";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

// ------------------------------------------------------------------ Button
const buttonVariants = cva(
  "pressable inline-flex select-none items-center justify-center gap-1.5 whitespace-nowrap rounded-lg border font-medium disabled:pointer-events-none disabled:opacity-40",
  {
    variants: {
      variant: {
        default: "border-line-strong bg-panel text-fg shadow-[var(--shadow-card)] hover:bg-panel-2",
        primary: "border-transparent bg-navy text-white shadow-[var(--shadow-card)] hover:bg-navy-2",
        ok: "border-ok/25 bg-ok/8 text-ok hover:bg-ok/15",
        bad: "border-bad/25 bg-bad/8 text-bad hover:bg-bad/15",
        ghost: "border-transparent bg-transparent text-muted hover:bg-panel-3 hover:text-fg",
        subtle: "border-transparent bg-panel-3 text-fg hover:bg-line",
      },
      size: { sm: "h-8 px-3 text-[13px]", md: "h-9 px-3.5 text-sm", xs: "h-7 px-2.5 text-xs", icon: "h-8 w-8 p-0" },
    },
    defaultVariants: { variant: "default", size: "md" },
  },
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, type, ...props }, ref) => (
  <button ref={ref} type={type ?? "button"} className={cn(buttonVariants({ variant, size }), className)} {...props} />
));
Button.displayName = "Button";

// ------------------------------------------------------------------- Badge
const badgeVariants = cva("inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11.5px] font-medium leading-4", {
  variants: {
    tone: {
      neutral: "bg-panel-3 text-muted",
      ok: "bg-ok/10 text-ok",
      bad: "bg-bad/10 text-bad",
      warn: "bg-warn/12 text-warn",
      info: "bg-info/10 text-info",
      fault: "bg-fault/10 text-fault",
      accent: "bg-accent/10 text-accent",
    },
  },
  defaultVariants: { tone: "neutral" },
});

export function Badge({ className, tone, ...props }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}

/** Small coloured status dot (pairs with a text label; never colour alone). */
export function Dot({ tone = "neutral", pulse = false, className }: { tone?: "ok" | "bad" | "warn" | "info" | "fault" | "neutral"; pulse?: boolean; className?: string }) {
  const c = { ok: "bg-ok", bad: "bg-bad", warn: "bg-warn", info: "bg-info", fault: "bg-fault", neutral: "bg-static" }[tone];
  return <span aria-hidden className={cn("inline-block h-2 w-2 shrink-0 rounded-full", c, pulse && "live-dot", className)} />;
}

// ------------------------------------------------------------------- Panel / Card
export function Panel({
  title,
  right,
  className,
  bodyClassName,
  children,
  subtitle,
  icon,
}: {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  icon?: React.ReactNode;
  right?: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={cn("flex min-h-0 flex-col overflow-hidden rounded-xl border border-line bg-panel shadow-[var(--shadow-card)]", className)}>
      {title !== undefined && (
        <header className="flex min-h-11 shrink-0 items-center justify-between gap-3 border-b border-line px-4 py-2">
          <div className="flex min-w-0 items-center gap-2">
            {icon && <span className="text-dim">{icon}</span>}
            <div className="min-w-0">
              <h2 className="t-heading truncate text-fg">{title}</h2>
              {subtitle && <p className="truncate text-xs text-dim">{subtitle}</p>}
            </div>
          </div>
          {right}
        </header>
      )}
      <div className={cn("min-h-0 flex-1", bodyClassName)}>{children}</div>
    </section>
  );
}

// -------------------------------------------------------------------- Tabs (segmented)
export const Tabs = TabsPrimitive.Root;

export const TabsList = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.List>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.List ref={ref} className={cn("flex h-10 shrink-0 items-stretch gap-1 border-b border-line bg-panel px-2", className)} {...props} />
));
TabsList.displayName = "TabsList";

export const TabsTrigger = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      "relative px-3 text-[13px] font-medium text-dim transition-colors hover:text-fg data-[state=active]:text-fg data-[state=active]:after:absolute data-[state=active]:after:inset-x-2 data-[state=active]:after:-bottom-px data-[state=active]:after:h-0.5 data-[state=active]:after:rounded-full data-[state=active]:after:bg-navy",
      className,
    )}
    {...props}
  />
));
TabsTrigger.displayName = "TabsTrigger";

export const TabsContent = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content ref={ref} className={cn("min-h-0 flex-1 overflow-auto data-[state=inactive]:hidden", className)} {...props} />
));
TabsContent.displayName = "TabsContent";

// ------------------------------------------------------------------ Segmented control
export function Segmented<T extends string | number>({
  value,
  options,
  onChange,
  label,
  size = "md",
  disabled,
  testIdPrefix,
}: {
  value: T;
  options: { value: T; label: React.ReactNode; title?: string }[];
  onChange: (v: T) => void;
  label: string;
  size?: "sm" | "md";
  disabled?: boolean;
  testIdPrefix?: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className={cn("inline-flex rounded-lg bg-panel-3 p-0.5", disabled && "opacity-50")}>
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={String(o.value)}
            type="button"
            role="radio"
            aria-checked={on}
            title={o.title}
            disabled={disabled}
            data-testid={testIdPrefix ? `${testIdPrefix}-${o.value}` : undefined}
            onClick={() => !on && onChange(o.value)}
            className={cn(
              "pressable rounded-md font-medium",
              size === "sm" ? "h-7 px-2.5 text-xs" : "h-8 px-3 text-[13px]",
              on ? "bg-panel text-fg shadow-[var(--shadow-card)]" : "text-dim hover:text-fg",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

// ------------------------------------------------------------------ Slider
export const Slider = React.forwardRef<
  React.ElementRef<typeof SliderPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof SliderPrimitive.Root>
>(({ className, ...props }, ref) => (
  <SliderPrimitive.Root ref={ref} className={cn("relative flex w-full touch-none select-none items-center py-2", className)} {...props}>
    <SliderPrimitive.Track className="relative h-1.5 w-full grow overflow-hidden rounded-full bg-panel-3">
      <SliderPrimitive.Range className="absolute h-full bg-navy" />
    </SliderPrimitive.Track>
    <SliderPrimitive.Thumb
      aria-label={props["aria-label"]}
      className="block h-4.5 w-4.5 rounded-full border-2 border-navy bg-white shadow-[var(--shadow-card)] transition-transform active:scale-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
    />
  </SliderPrimitive.Root>
));
Slider.displayName = "Slider";

// ------------------------------------------------------------------- Input
export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...props }, ref) => (
  <input
    ref={ref}
    className={cn(
      "num h-8 w-full rounded-lg border border-line-strong bg-panel px-2.5 text-right text-[13px] text-fg transition-colors placeholder:text-dim hover:border-dim/60 focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/20 aria-[invalid=true]:border-bad aria-[invalid=true]:ring-bad/15",
      className,
    )}
    {...props}
  />
));
Input.displayName = "Input";

export function Select({ className, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "h-8 rounded-lg border border-line-strong bg-panel px-2.5 text-[13px] text-fg transition-colors hover:border-dim/60 focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/20",
        className,
      )}
      {...props}
    />
  );
}

// ------------------------------------------------------------------- Kbd
export function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd className="num rounded border border-line-strong bg-panel-2 px-1.5 py-px text-[10.5px] text-dim">{children}</kbd>;
}

// ------------------------------------------------------------------- Stat (hyperbold metric)
export function Stat({
  label,
  value,
  unit,
  sub,
  tone = "fg",
  trend,
  testId,
  onClick,
}: {
  label: React.ReactNode;
  value: React.ReactNode;
  unit?: React.ReactNode;
  sub?: React.ReactNode;
  tone?: "fg" | "accent" | "ok" | "warn" | "bad" | "fault" | "info";
  trend?: "up" | "down" | null;
  testId?: string;
  onClick?: () => void;
}) {
  const color = { fg: "text-fg", accent: "text-accent", ok: "text-ok", warn: "text-warn", bad: "text-bad", fault: "text-fault", info: "text-info" }[tone];
  const Comp = onClick ? "button" : "div";
  return (
    <Comp
      type={onClick ? "button" : undefined}
      onClick={onClick}
      data-testid={testId}
      className={cn(
        "min-w-0 rounded-xl border border-line bg-panel px-4 py-3 text-left shadow-[var(--shadow-card)]",
        onClick && "pressable cursor-pointer hover:border-line-strong",
      )}
    >
      <div className="truncate text-xs font-medium text-dim">{label}</div>
      <div className={cn("num mt-1 flex items-baseline gap-1.5 text-[26px] font-semibold leading-none tracking-[-0.02em]", color)}>
        {value}
        {unit && <span className="text-[13px] font-medium tracking-normal text-dim">{unit}</span>}
        {trend && (
          <span className={cn("text-xs", trend === "up" ? "text-[#ea580c]" : "text-info")} aria-label={trend === "up" ? "rising" : "falling"}>
            {trend === "up" ? "▲" : "▼"}
          </span>
        )}
      </div>
      {sub && <div className="mt-1.5 truncate text-xs text-dim">{sub}</div>}
    </Comp>
  );
}
