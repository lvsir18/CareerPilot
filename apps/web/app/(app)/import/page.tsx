import { JobImportForm } from "@/components/job-import-form";

export const dynamic = "force-dynamic";

export default function ImportJobPage() {
  return (
    <div className="mx-auto max-w-4xl">
      <header className="border-b border-slate-200 pb-5">
        <p className="text-xs font-semibold tracking-[0.2em] text-sky-600 uppercase">
          M2-A · 真实岗位导入
        </p>
        <h1 className="mt-2 text-2xl font-semibold text-slate-900">导入官方岗位链接</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-600">
          目前支持百度招聘官网的公开详情页。系统只抓取你提交的单个链接，不批量爬取、不登录第三方账号。
          若页面无法读取，可以粘贴已核实的 JD 并确认入库。
        </p>
      </header>

      <JobImportForm />
    </div>
  );
}
