export type JobSort = "published_at_desc" | "first_seen_at_desc" | "title_asc";

export interface JobFilters {
  q: string;
  cities: string;
  job_types: string;
  source_types: string;
  recruitment_program: string;
  sort: JobSort;
  page: number;
  /** Admin-only view of soft-archived postings (`?archived=1`). */
  archived?: boolean;
}

export const DEFAULT_JOB_FILTERS: JobFilters = {
  q: "",
  cities: "",
  job_types: "",
  source_types: "",
  recruitment_program: "",
  sort: "published_at_desc",
  page: 1,
};

const SORT_VALUES: JobSort[] = ["published_at_desc", "first_seen_at_desc", "title_asc"];

type SearchParamValue = string | string[] | undefined;

function firstValue(value: SearchParamValue): string {
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

/** Convert Next.js searchParams into validated filters (unknown values are dropped). */
export function parseJobFilters(
  params: Record<string, SearchParamValue> | undefined,
): JobFilters {
  const rawSort = firstValue(params?.sort);
  const sort = SORT_VALUES.includes(rawSort as JobSort)
    ? (rawSort as JobSort)
    : DEFAULT_JOB_FILTERS.sort;
  const rawPage = Number.parseInt(firstValue(params?.page), 10);
  const page = Number.isFinite(rawPage) && rawPage > 0 ? rawPage : 1;

  return {
    q: firstValue(params?.q),
    cities: firstValue(params?.cities),
    job_types: firstValue(params?.job_types),
    source_types: firstValue(params?.source_types),
    recruitment_program: firstValue(params?.recruitment_program),
    sort,
    page,
  };
}

/** Build the API query string; empty filters are omitted to keep URLs clean. */
export function buildJobQuery(filters: JobFilters, pageSize = 12): string {
  const params = new URLSearchParams();
  const textFields: Array<[string, string]> = [
    ["q", filters.q],
    ["cities", filters.cities],
    ["job_types", filters.job_types],
    ["source_types", filters.source_types],
    ["recruitment_program", filters.recruitment_program],
  ];

  for (const [key, value] of textFields) {
    const trimmed = value.trim();
    if (trimmed) {
      params.set(key, trimmed);
    }
  }
  if (filters.sort !== DEFAULT_JOB_FILTERS.sort) {
    params.set("sort", filters.sort);
  }
  if (filters.page > 1) {
    params.set("page", String(filters.page));
  }
  if (filters.archived) {
    params.set("archived", "true");
  }
  params.set("page_size", String(pageSize));
  return params.toString();
}

export function jobPageHref(filters: JobFilters, page: number, pageSize = 12): string {
  return `/jobs?${buildJobQuery({ ...filters, page }, pageSize)}`;
}
