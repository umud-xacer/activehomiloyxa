import type { ElementType, ReactNode } from "react";

interface ContainerProps {
  children: ReactNode;
  className?: string;
  as?: ElementType;
  /**
   * Wider max-width scale for content that benefits from more breathing
   * room on large monitors (listing grids, map + panel layouts) instead of
   * the default reading-width scale (prose-heavy sections, forms).
   */
  wide?: boolean;
}

/**
 * Single source of truth for horizontal page padding + max-width across all
 * 7 responsive tiers. Content width grows in controlled steps as the
 * viewport widens -- it never tracks viewport width 1:1, so 1920px/2560px+
 * screens get generous whitespace instead of edge-to-edge stretching.
 */
const PADDING = "px-4 sm:px-6 md:px-8 xl:px-10 2xl:px-12 3xl:px-16 4xl:px-20";
const MAX_WIDTH_DEFAULT = "max-w-7xl 2xl:max-w-[1400px] 3xl:max-w-[1600px] 4xl:max-w-[1800px]";
const MAX_WIDTH_WIDE = "max-w-7xl 2xl:max-w-[1560px] 3xl:max-w-[1800px] 4xl:max-w-[2000px]";

export function Container({ children, className = "", as: Tag = "div", wide = false }: ContainerProps) {
  const maxWidth = wide ? MAX_WIDTH_WIDE : MAX_WIDTH_DEFAULT;
  return <Tag className={`mx-auto w-full ${PADDING} ${maxWidth} ${className}`}>{children}</Tag>;
}
