/**
 * Re-export of shared finance formatting helpers.
 *
 * The canonical implementation lives in `@/lib/finance-format` so both the
 * KOL Research View and the legacy /kol pages share one color convention.
 * Kept here as a thin shim so existing `./format` imports stay valid.
 */
export * from "@/lib/finance-format";
