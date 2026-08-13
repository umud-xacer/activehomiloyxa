/**
 * Reusable "share this listing" button -- uses the native Web Share sheet
 * (`navigator.share`) where available (essentially every mobile browser), and falls back to
 * copying the link to the clipboard with an inline "Nusxalandi" confirmation everywhere else
 * (desktop Chrome/Firefox have no `navigator.share`). No backend involved -- the URL is the
 * public listing page itself.
 */
import { useEffect, useState } from "react";
import { Check, Share2 } from "lucide-react";

export function ShareButton({
  url,
  title,
  size = "md",
  variant = "outline",
  className = "",
}: {
  url: string;
  title: string;
  size?: "sm" | "md";
  variant?: "overlay" | "outline";
  className?: string;
}) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const t = setTimeout(() => setCopied(false), 2000);
    return () => clearTimeout(t);
  }, [copied]);

  const share = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (navigator.share) {
      try {
        await navigator.share({ title, url });
      } catch {
        // AbortError when the user just closes the native sheet -- not a real failure.
      }
      return;
    }
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      // Clipboard API needs a secure context/permission; silently no-op rather than throwing
      // in the rare browser that has neither Web Share nor Clipboard access.
    }
  };

  const dims = size === "sm" ? "size-8" : "size-9";
  const iconDims = size === "sm" ? "size-3.5" : "size-4";
  const shell =
    variant === "overlay"
      ? "bg-white/90 text-foreground shadow-soft backdrop-blur hover:bg-white"
      : "border border-border bg-card hover:bg-muted";

  return (
    <span className="relative inline-flex">
      <button
        type="button"
        aria-label="Ulashish"
        onClick={share}
        className={`inline-flex shrink-0 items-center justify-center rounded-full transition ${dims} ${shell} ${className}`}
      >
        {copied ? (
          <Check className={`${iconDims} text-success`} />
        ) : (
          <Share2 className={iconDims} />
        )}
      </button>
      {copied && (
        <span className="absolute -bottom-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-foreground px-2.5 py-1 text-[11px] font-medium text-background shadow-elevated">
          Havola nusxalandi
        </span>
      )}
    </span>
  );
}
