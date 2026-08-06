import type { ReactNode } from "react";

interface Props {
  children: ReactNode;
  className?: string;
  bleed?: boolean;
}

export function Section({ children, className = "", bleed = false }: Props) {
  return (
    <section className={`py-16 md:py-24 ${className}`}>
      <div className={bleed ? "" : "mx-auto max-w-7xl px-6"}>{children}</div>
    </section>
  );
}
