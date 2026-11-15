/** Page body: consistent gutters, width and optional intro line + actions. */
export function PageBody({
  intro,
  actions,
  children,
  wide = false,
}: {
  intro?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  wide?: boolean;
}) {
  return (
    <div className={`mx-auto w-full px-5 py-4 ${wide ? "max-w-none" : "max-w-[1480px]"}`}>
      {(intro || actions) && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          {intro && <p className="max-w-3xl text-[13.5px] leading-relaxed text-muted">{intro}</p>}
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </div>
  );
}
