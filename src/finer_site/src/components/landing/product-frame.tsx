import Image from "next/image";
import { cn } from "@/lib/utils";

/**
 * Editorial "browser frame" wrapper for real product screenshots.
 * Renders a hard-edged window chrome (no soft glass) around a captured
 * screenshot stored under /public/landing.
 */
export function ProductFrame({
  src,
  alt,
  width,
  height,
  label,
  priority = false,
  className,
}: {
  src: string;
  alt: string;
  width: number;
  height: number;
  /** Faux address-bar label, e.g. "finer.os/research". */
  label: string;
  priority?: boolean;
  className?: string;
}) {
  return (
    <figure
      className={cn(
        "overflow-hidden rounded-sm border border-[var(--table-border)] bg-white shadow-[var(--shadow-panel)]",
        className,
      )}
    >
      <div className="flex items-center gap-2 border-b border-[var(--table-border)] bg-[var(--table-header-bg)] px-3 py-2">
        <span className="h-2.5 w-2.5 rounded-full bg-morningstar-red/70" />
        <span className="h-2.5 w-2.5 rounded-full bg-[var(--accent-gold)]/60" />
        <span className="h-2.5 w-2.5 rounded-full bg-[var(--accent-teal)]/50" />
        <span className="ml-3 truncate font-mono text-[11px] text-foreground/45">
          {label}
        </span>
      </div>
      <Image
        src={src}
        alt={alt}
        width={width}
        height={height}
        priority={priority}
        className="block h-auto w-full"
        sizes="(max-width: 1024px) 100vw, 960px"
      />
    </figure>
  );
}
