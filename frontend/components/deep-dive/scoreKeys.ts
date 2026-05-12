// Backward-compatible re-exports — the canonical source is `categories.ts`.
// `DISPLAY_TO_KEY` is kept as an alias of `SCORE_DISPLAY_TO_KEY`.

export {
  SCORE_DISPLAY_TO_KEY as DISPLAY_TO_KEY,
  normalizeScoreKeys,
} from "./categories";
