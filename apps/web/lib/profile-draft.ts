/**
 * Profile drafts live in sessionStorage so a mistyped edit survives navigation.
 *
 * They are keyed by account: two accounts share one browser profile, and a
 * version-only check cannot tell them apart (both start at version 0), which
 * made account B see account A's unsaved text.
 */
export const DRAFT_PREFIX = "careerpilot.profile.draft.v2.";

export function draftKey(userId: string): string {
  return `${DRAFT_PREFIX}${userId}`;
}

export function clearAllProfileDrafts(): void {
  if (typeof window === "undefined") {
    return;
  }
  const keys = Object.keys(window.sessionStorage).filter((key) => key.startsWith(DRAFT_PREFIX));
  for (const key of keys) {
    window.sessionStorage.removeItem(key);
  }
}
