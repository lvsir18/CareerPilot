#!/usr/bin/env python3
"""Run the fixed M2-R3 query set against a live CareerPilot API.

This script never fakes provider calls. It records exactly whether a licensed
search provider was configured and which official domains returned candidates.
"""

from __future__ import annotations

import json
import os
import statistics
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
QUERIES = ROOT / "backend" / "tests" / "fixtures" / "m2r3_queries.json"
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
ORIGIN = os.getenv("EVAL_ORIGIN", "http://localhost:3000")
EMAIL = os.getenv("EVAL_EMAIL", "m2r3-eval@example.com")
PASSWORD = os.getenv("EVAL_PASSWORD", "strong-pass-123")
REGISTER = os.getenv("EVAL_REGISTER", "1") == "1"
OFFICIAL_HOSTS = {
    "jobs.bytedance.com",
    "join.qq.com",
    "talent.alibaba.com",
    "zhaopin.meituan.com",
    "career.meituan.com",
    "talent.baidu.com",
    "job.xiaohongshu.com",
    "jobs.bilibili.com",
    "careers.dewu.com",
    "talent.deepseek.com",
    "hr.360.cn",
    "hr.xiaomi.com",
    "minimax.cn",
    "www.minimax.cn",
    "campus.jd.com",
    "careers.kimi.com",
    "job.ctrip.com",
    "zhaopin.kuaishou.cn",
    "campus.kuaishou.cn",
    "careers.ctrip.com",
    "campus.163.com",
    "career.huawei.com",
    "careers.pddglobalhr.com",
    "vrfi1sk8a0.jobs.feishu.cn",
    "app.mokahr.com",
}


def _csrf(client: httpx.Client) -> str:
    response = client.get(f"{BASE_URL}/api/v1/auth/csrf")
    response.raise_for_status()
    return response.json()["data"]["csrf_token"]


def _auth(client: httpx.Client) -> None:
    token = _csrf(client)
    path = "/api/v1/auth/register" if REGISTER else "/api/v1/auth/login"
    response = client.post(
        f"{BASE_URL}{path}",
        headers={"Origin": ORIGIN, "X-CSRF-Token": token},
        json={"email": EMAIL, "password": PASSWORD},
    )
    if response.status_code not in {201, 200}:
        raise SystemExit(f"auth failed: {response.status_code} {response.text[:300]}")


def main() -> None:
    queries = json.loads(QUERIES.read_text(encoding="utf-8"))
    assert len(queries) >= 20
    all_leads: dict[str, dict] = {}
    rows = []
    latencies = []
    by_company: dict[str, set[str]] = defaultdict(set)
    response_occurrences: list[str] = []
    provider_counts: dict[str, int] = defaultdict(int)
    licensed_configured = False
    tavily_queries = 0
    tavily_cached_queries = 0
    credits_estimated = 0

    with httpx.Client(timeout=60) as client:
        _auth(client)
        for item in queries:
            params = {
                "query": item["query"],
                "companies": ",".join(item["companies"]),
                "city": item["city"],
                "job_type": item["job_type"],
                "job_family": item["job_family"],
                "page_size": 20,
                "sort": "relevance",
            }
            started = time.perf_counter()
            response = client.get(f"{BASE_URL}/api/v1/jobs/discover", params=params)
            latency = (time.perf_counter() - started) * 1000
            latencies.append(latency)
            if response.status_code != 200:
                rows.append(
                    {
                        "id": item["id"],
                        "status": response.status_code,
                        "latency_ms": round(latency, 1),
                        "error": response.text[:300],
                    }
                )
                continue
            data = response.json()["data"]
            search = data["search"]
            licensed_configured = licensed_configured or search["licensed_configured"]
            for provider in search["providers_used"]:
                provider_counts[provider] += 1
            tavily_queries += int(search.get("tavily_queries") or 0)
            tavily_cached_queries += int(search.get("tavily_cached_queries") or 0)
            credits_estimated += int(search.get("credits_estimated") or 0)
            local_by_url = {
                lead["official_url"]: lead for lead in data["leads"]
            }
            for result in search["provider_results"]:
                local = local_by_url.get(result["url"])
                key = result["url"]
                if key not in all_leads:
                    all_leads[key] = {
                        **result,
                        "official_url": result["url"],
                        "company": local["company"] if local else result["company"],
                        "verification_status": local["verification_status"]
                        if local
                        else "search_snippet_only",
                    }
                else:
                    all_leads[key]["providers"] = sorted(
                        set(all_leads[key].get("providers") or [])
                        | set(result.get("providers") or [])
                    )
                response_occurrences.append(result["url"])
                by_company[result["company"] if not local else local["company"]].add(
                    result["url"]
                )
            rows.append(
                {
                    "id": item["id"],
                    "company": item["companies"],
                    "query": item["query"],
                    "city": item["city"],
                    "job_family": item["job_family"],
                    "status": 200,
                    "latency_ms": round(latency, 1),
                    "provider_hits": len(search["provider_results"]),
                    "leads": data["total_leads"],
                    "jobs": data["total_jobs"],
                    "providers": search["providers_used"],
                    "licensed_configured": search["licensed_configured"],
                }
            )

    valid_urls = 0
    published = 0
    verified = 0
    for lead in all_leads.values():
        host = (urlsplit(lead["official_url"]).hostname or "").lower()
        if host in OFFICIAL_HOSTS:
            valid_urls += 1
        if lead.get("published_date"):
            published += 1
        if lead.get("verification_status") == "verified_official":
            verified += 1

    # Duplicate ratio across all fixed-query response occurrences (not DB dedupe).
    duplicate_ratio = 0.0
    if response_occurrences:
        duplicate_ratio = max(
            0.0, 1.0 - (len(set(response_occurrences)) / len(response_occurrences))
        )

    def provider_metrics(name: str) -> dict:
        entries = [
            lead for lead in all_leads.values() if name in (lead.get("providers") or [])
        ]
        return {
            "unique_candidates": len(entries),
            "official_domain_valid": sum(
                1
                for lead in entries
                if (urlsplit(lead["official_url"]).hostname or "").lower()
                in OFFICIAL_HOSTS
            ),
            "published_date_available": sum(
                1 for lead in entries if lead.get("published_date")
            ),
            "companies": sorted({lead["company"] for lead in entries}),
        }

    official_query_count = sum(
        1 for item in queries if "baidu" in item["companies"]
    )
    provider_metrics_all = {
        "tavily": provider_metrics("tavily"),
        "baidu_official_list": provider_metrics("baidu_official_list"),
    }
    summary = {
        "query_count": len(queries),
        "official_site_query_count": official_query_count,
        "provider_result_query_counts": dict(provider_counts),
        "licensed_search_configured": licensed_configured,
        "unique_candidates": len(all_leads),
        "official_domain_valid": valid_urls,
        "official_domain_valid_rate": round(valid_urls / len(all_leads), 4)
        if all_leads
        else 0,
        "published_date_available": published,
        "published_date_available_rate": round(published / len(all_leads), 4)
        if all_leads
        else 0,
        "verified_official_candidates": verified,
        "detail_verification_attempts_observed": "3 (M2-R1/R2 run; see report)",
        "detail_verification_success_rate_observed": "3/3 = 100%",
        "duplicate_ratio_across_query_results": round(duplicate_ratio, 4),
        "latency_ms": {
            "avg": round(statistics.mean(latencies), 1),
            "p95": round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 1),
            "max": round(max(latencies), 1),
        },
        "paid_search_api_calls": tavily_queries,
        "tavily_query_requests": tavily_queries,
        "tavily_cached_queries": tavily_cached_queries,
        "tavily_credits_estimated": credits_estimated,
        "credit_note": "按每条查询一次 Tavily basic 请求估算；缓存命中可能减少实际 credits",
        "official_public_page_requests_estimate": official_query_count,
        "provider_metrics": provider_metrics_all,
        "by_company_unique_candidates": {
            company: len(values) for company, values in sorted(by_company.items())
        },
        "queries": rows,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
