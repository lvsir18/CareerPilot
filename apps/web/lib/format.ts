const DEFAULT_TIME_ZONE = "Asia/Shanghai";

/**
 * Format an ISO timestamp in the user-facing timezone.
 *
 * A missing or unparseable timestamp is shown as "未知" — the product must
 * never invent a publish date or display a discovery time in its place.
 */
export function formatDateTime(
  value: string | null | undefined,
  timeZone: string = DEFAULT_TIME_ZONE,
): string {
  if (!value) {
    return "未知";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "未知";
  }

  return new Intl.DateTimeFormat("zh-CN", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}
