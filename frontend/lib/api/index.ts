/**
 * Barrel re-export — every consumer that imports from "@/lib/api" continues to
 * work unchanged.  No call-site modifications needed.
 */

// Selective from core: BASE/apiFetch were module-private pre-split and stay
// out of the public surface — api/* modules import them from "./core" directly.
export type { Citation } from "./core";
export * from "./themes";
export * from "./filings";
export * from "./pipeline";
export * from "./catalysts";
export * from "./status";
export * from "./workspace";
export * from "./performance";
export * from "./transcripts";
export * from "./model";
export * from "./prospectus";
export * from "./company";
