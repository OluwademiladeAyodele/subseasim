/**
 * shadcn/ui-style primitives (copied-in components, styled for the
 * industrial dark theme). Kept in one file because each is small.
 */
import * as React from "react";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import * as SliderPrimitive from "@radix-ui/react-slider";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

// ------------------------------------------------------------------ Button
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-sm border text-xs font-semibold uppercase tracking-wide transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-40",
  {
    variants: {
      variant: {
        default: "border-line-strong bg-panel-3 text-fg hover:bg-line",
        primary: "border-accent/60 bg-accent/15 text-accent hover:bg-accent/25",
        ok: "border-ok/60 bg-ok/10 text-ok hover:bg-ok/20",
        bad: "border-bad/60 bg-bad/10 text-bad hover:bg-bad/20",
        ghost: "border-transparent bg-transparent text-muted hover:text-fg hover:bg-panel-3",
      },
      size: { sm: "h-7 px-2.5", md: "h-8 px-3", xs: "h-6 px-2 text-[10px]" },
    },
    defaultVariants: { variant: "default", size: "md" },
  },
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, ...props }, ref) => (
  <button ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />
));
Button.displayName = "Button";

// ------------------------------------------------------------------- Badge
const badgeVariants = cva("inline-flex items-center gap-1 rounded-sm border px-1.5 py-px text-[10px] font-bold uppercase tracking-wider", {
  variants: {
    tone: {
      neutral: "border-line-strong text-muted",
      ok: "border-ok/50 text-ok bg-ok/10",
      bad: "border-bad/50 text-bad bg-bad/10",
      warn: "border-warn/50 text-warn bg-warn/10",
      info: "border-info/50 text-info bg-info/10",
      fault: "border-fault/50 text-fault bg-fault/10",
      accent: "border-accent/50 text-accent bg-accent/10",
    },
  },
  defaultVariants: { tone: "neutral" },
});

export function Badge({ className, tone, ...props }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}

// ------------------------------------------------------------------- Panel
export function Panel({
  title,
  right,
  className,
  bodyClassName,
  children,
}: {
  title?: React.ReactNode;
  right?: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={cn("flex min-h-0 flex-col border border-line bg-panel", className)}>
      {title !== undefined && (
        <header className="flex h-7 shrink-0 items-center justify-between gap-2 border-b border-line bg-panel-2 px-2.5">
          <h2 className="text-[11px] font-bold uppercase tracking-[0.12em] text-muted">{title}</h2>
          {right}
        </header>
      )}
      <div className={cn("min-h-0 flex-1", bodyClassName)}>{children}</div>
    </section>
  );
}

// -------------------------------------------------------------------- Tabs
export const Tabs = TabsPrimitive.Root;

export const TabsList = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.List>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.List ref={ref} className={cn("flex h-7 shrink-0 items-stretch border-b border-line bg-panel-2", className)} {...props} />
));
TabsList.displayName = "TabsList";

export const TabsTrigger = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      "border-r border-line px-3 text-[11px] font-bold uppercase tracking-[0.1em] text-muted hover:text-fg data-[state=active]:bg-panel data-[state=active]:text-accent data-[state=active]:shadow-[inset_0_-2px_0_var(--color-accent)]",
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

// ------------------------------------------------------------------ Slider
export const Slider = React.forwardRef<
  React.ElementRef<typeof SliderPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof SliderPrimitive.Root>
>(({ className, ...props }, ref) => (
  <SliderPrimitive.Root ref={ref} className={cn("relative flex w-full touch-none select-none items-center py-2", className)} {...props}>
    <SliderPrimitive.Track className="relative h-1.5 w-full grow overflow-hidden rounded-full bg-line">
      <SliderPrimitive.Range className="absolute h-full bg-accent/70" />
    </SliderPrimitive.Track>
    <SliderPrimitive.Thumb
      aria-label={props["aria-label"]}
      className="block h-4 w-2.5 rounded-[2px] border border-accent bg-panel-3 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
    />
  </SliderPrimitive.Root>
));
Slider.displayName = "Slider";

// ------------------------------------------------------------------- Input
export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...props }, ref) => (
  <input
    ref={ref}
    className={cn(
      "num h-7 w-full rounded-sm border border-line-strong bg-bg px-2 text-right text-xs text-fg focus-visible:border-accent focus-visible:outline-none aria-[invalid=true]:border-bad",
      className,
    )}
    {...props}
  />
));
Input.displayName = "Input";

export function Select({ className, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn("h-7 rounded-sm border border-line-strong bg-bg px-1.5 text-xs text-fg focus-visible:border-accent focus-visible:outline-none", className)}
      {...props}
    />
  );
}
