import { JobImportForm } from "@/components/job-import-form";

export const dynamic = "force-dynamic";

export default function ImportJobPage() {
  return (
    <div className="mx-auto max-w-4xl">
      <header className="border-b border-slate-200 pb-5">
        <p className="text-xs font-medium tracking-wide text-sky-700">手动导入</p>
        <h1 className="mt-2 text-2xl font-semibold text-slate-900">导入官方岗位链接</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-600">
          两种方式：<strong>链接解析</strong>支持任何企业的岗位详情页——百度直接解析为公开岗位，
          其他企业用无头浏览器读取页面并给出待确认草稿（只读你提交的单个链接，不批量爬取、不登录第三方账号）；
          <strong>粘贴 JD</strong> 适用于读不到的页面，保存后是仅本人可见的私有候选。
        </p>
      </header>

      <JobImportForm />
    </div>
  );
}