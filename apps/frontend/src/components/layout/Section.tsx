import type { ReactNode } from "react";
import { Container } from "./Container";

interface Props {
  children: ReactNode;
  className?: string;
  bleed?: boolean;
  /** Pass through to `Container`'s wider max-width scale for grid/map-heavy sections. */
  wide?: boolean;
}

export function Section({ children, className = "", bleed = false, wide = false }: Props) {
  return (
    <section className={`py-16 md:py-24 3xl:py-28 ${className}`}>
      {bleed ? children : <Container wide={wide}>{children}</Container>}
    </section>
  );
}
