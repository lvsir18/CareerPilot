import { CircleAlert, FlaskConical } from "lucide-react";

import { getApiBaseUrl } from "@/lib/api";

/**
 * Persistent transparency banner. Demo mode must always be visible, and an
 * unreachable API must be shown as an error instead of a silent empty state.
 */
export function DemoModeBanner({
  demoMode,
  apiReachable,
}: {
  demoMode: boolean;
  apiReachable: boolean;
}) {
  if (!apiReachable) {
    return (
      <div
        role="status"
        className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800"
      >
        <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
        <div>
          <p className="font-medium">无法连接后端 API</p>
          <p className="mt-1 text-rose-700">
            请确认 <code className="font-mono">{getApiBaseUrl()}</code> 已启动（
            <code className="font-mono">make dev</code>），页面当前展示的是降级状态。
          </p>
        </div>
      </div>
    );
  }

  if (!demoMode) {
    return null;
  }

  return (
    <div
      role="status"
      className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
    >
      <FlaskConical className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div>
        <p className="font-medium">演示数据 · 部分功能为规则模式</p>
        <p className="mt-1 text-amber-800">
          当前处于 M0 基础工程阶段：尚未接入任何真实岗位，也不提供自动投递。后续同步数据源与 Demo
          数据都会明确标注来源。
        </p>
      </div>
    </div>
  );
}
