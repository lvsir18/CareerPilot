export default function DashboardLoading() {
  return (
    <div className="animate-pulse space-y-6" aria-busy="true" aria-label="页面加载中">
      <div className="h-16 rounded-xl bg-slate-200/70" />
      <div className="h-10 w-2/3 rounded-lg bg-slate-200/70" />
      <div className="h-44 rounded-2xl bg-slate-200/60" />
      <div className="grid gap-6 lg:grid-cols-5">
        <div className="h-96 rounded-2xl bg-slate-200/60 lg:col-span-3" />
        <div className="h-96 rounded-2xl bg-slate-200/60 lg:col-span-2" />
      </div>
    </div>
  );
}
