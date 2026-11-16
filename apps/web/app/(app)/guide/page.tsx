import Link from "next/link";
import {
  ArrowRight,
  BellRing,
  BookOpen,
  Bot,
  CalendarCheck,
  CheckCircle2,
  Compass,
  FileSearch,
  Info,
  KeyRound,
  Laptop,
  ListChecks,
  Mail,
  ShieldCheck,
  Sparkles,
  Upload,
  UserRound,
  Wrench,
} from "lucide-react";

import type { ReactNode } from "react";

export const dynamic = "force-dynamic";

const SECTIONS = [
  { id: "start", label: "五分钟上手" },
  { id: "pages", label: "页面地图" },
  { id: "account", label: "账号与登录" },
  { id: "resume", label: "简历与画像" },
  { id: "jobs", label: "找岗位" },
  { id: "maintain", label: "维护岗位库" },
  { id: "match", label: "推荐与匹配" },
  { id: "apply", label: "投递与面试" },
  { id: "agent", label: "Agent 工作台" },
  { id: "keys", label: "模型与搜索 Key" },
  { id: "mobile", label: "手机与多端" },
  { id: "limits", label: "限制与边界" },
];

const PAGES: [string, string, string][] = [
  ["首页", "/home", "系统介绍与快捷入口"],
  ["概览", "/dashboard", "真实统计、最近进度、即将开始的日程"],
  ["岗位库", "/jobs", "已核验岗位，可手动更新与清理"],
  ["发现岗位", "/discover", "官网直连检索与关键词搜索"],
  ["岗位推荐", "/matches", "基于已确认画像的推荐与资格判断"],
  ["Agent 工作台", "/agent", "多轮问答，实时进度，可取消"],
  ["投递看板", "/applications", "申请记录、邮件候选与时间线"],
  ["面试日程", "/calendar", "只显示已预约的笔试与面试"],
  ["我的画像", "/profile", "编辑并确认画像，确认后才参与打分"],
  ["设置", "/settings/email", "邮箱、模型与搜索 Key、账号安全"],
];

const MULTI_TURN = [
  ["「那杭州呢」", "只换城市，保留实习与大模型方向"],
  ["「那其他公司呢」", "换企业，城市与方向保留"],
  ["「把第一个岗位的 JD 发我」", "指回上一轮的第一条结果"],
  ["「刚才找到几个」", "直接引用上一轮的真实统计数字"],
];

function Section({
  id,
  icon,
  title,
  subtitle,
  children,
}: {
  id: string;
  icon: ReactNode;
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-24 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex items-start gap-3">
        <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-xl bg-sky-50 text-sky-700 ring-1 ring-sky-100">
          {icon}
        </span>
        <div>
          <h2 className="text-base font-semibold text-slate-900">{title}</h2>
          {subtitle ? <p className="mt-1 text-sm text-slate-500">{subtitle}</p> : null}
        </div>
      </div>
      <div className="mt-4 space-y-3 text-sm leading-relaxed text-slate-700">{children}</div>
    </section>
  );
}

function Steps({ items }: { items: { title: string; body: string; href?: string }[] }) {
  return (
    <ol className="grid gap-3 sm:grid-cols-3">
      {items.map((item, index) => (
        <li key={item.title} className="rounded-xl bg-slate-50 p-4">
          <span className="inline-flex size-7 items-center justify-center rounded-lg bg-white text-xs font-semibold text-slate-700 ring-1 ring-slate-200">
            {index + 1}
          </span>
          <p className="mt-3 text-sm font-medium text-slate-900">{item.title}</p>
          <p className="mt-1 text-xs leading-relaxed text-slate-600">{item.body}</p>
          {item.href ? (
            <Link href={item.href} className="mt-2 inline-block text-xs font-medium text-sky-700 hover:underline">
              去这里 →
            </Link>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

function Tip({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "warn" }) {
  const styles =
    tone === "warn"
      ? "border-amber-200 bg-amber-50 text-amber-900"
      : "border-sky-200 bg-sky-50 text-sky-900";
  const Icon = tone === "warn" ? Info : CheckCircle2;
  return (
    <div className={`flex gap-2 rounded-xl border p-3 text-xs leading-relaxed ${styles}`}>
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div>{children}</div>
    </div>
  );
}

export default function GuidePage() {
  return (
    <div className="space-y-8 pb-6">
      <section className="relative overflow-hidden rounded-3xl border border-slate-200 bg-gradient-to-br from-slate-900 via-slate-900 to-sky-950 px-6 py-10 text-white sm:px-10">
        <div className="pointer-events-none absolute -top-24 -right-16 size-64 rounded-full bg-sky-500/25 blur-3xl" />
        <div className="relative max-w-2xl">
          <span className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-[11px] tracking-wide text-sky-200">
            <BookOpen className="size-3.5" aria-hidden />
            使用手册
          </span>
          <h1 className="mt-4 text-2xl font-semibold sm:text-3xl">从注册到拿到面试，每一步怎么做</h1>
          <p className="mt-3 text-sm leading-relaxed text-slate-300">
            这份手册按「上手 → 找岗位 → 投递 → Agent」的顺序组织，遇到具体问题可以直接跳到对应章节。
            更详细的技术说明见项目里的 <code className="rounded bg-white/10 px-1">docs/USER_GUIDE.md</code>。
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              href="#start"
              className="inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-medium text-slate-900 transition hover:bg-slate-100"
            >
              从五分钟上手开始
              <ArrowRight className="size-4" aria-hidden />
            </Link>
            <Link
              href="/jobs"
              className="inline-flex items-center gap-2 rounded-xl border border-white/25 px-4 py-2.5 text-sm text-white transition hover:bg-white/10"
            >
              直接去岗位库
            </Link>
          </div>
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-[200px_1fr]">
        <nav aria-label="手册目录" className="lg:sticky lg:top-20 lg:self-start">
          <p className="mb-2 hidden text-xs font-medium tracking-wide text-slate-400 uppercase lg:block">
            目录
          </p>
          <ul className="flex gap-2 overflow-x-auto pb-1 lg:block lg:space-y-1 lg:overflow-visible lg:pb-0">
            {SECTIONS.map((item) => (
              <li key={item.id} className="shrink-0">
                <a
                  href={`#${item.id}`}
                  className="block rounded-lg px-3 py-1.5 text-xs whitespace-nowrap text-slate-600 transition hover:bg-slate-100 hover:text-slate-900 lg:text-sm"
                >
                  {item.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="min-w-0 space-y-5">
          <Section
            id="start"
            icon={<Upload className="size-4" aria-hidden />}
            title="五分钟上手"
            subtitle="第一次使用，按顺序做完这三步就能看到推荐。"
          >
            <Steps
              items={[
                {
                  title: "上传简历",
                  body: "支持 PDF / DOCX（默认 ≤ 10 MB）。扫描版读不出文字时，可以手动填写。",
                  href: "/resumes",
                },
                {
                  title: "确认画像",
                  body: "在「我的画像」核对教育、项目与偏好，点「确认画像」后才会参与打分。",
                  href: "/profile",
                },
                {
                  title: "找岗位并跟进",
                  body: "看推荐或自己搜，收藏 / 登记投递；面试预约会进入日历。",
                  href: "/jobs",
                },
              ]}
            />
            <Tip>
              画像**未确认**时，推荐与详情都不会给分数 —— 这是为了避免用没核对过的内容算分。
            </Tip>
          </Section>

          <Section
            id="pages"
            icon={<Compass className="size-4" aria-hidden />}
            title="页面地图"
            subtitle="左侧导航每一项对应的功能。"
          >
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-500">
                    <th className="border-b border-slate-200 py-2 pr-4 font-medium">页面</th>
                    <th className="border-b border-slate-200 py-2 pr-4 font-medium">地址</th>
                    <th className="border-b border-slate-200 py-2 font-medium">用途</th>
                  </tr>
                </thead>
                <tbody>
                  {PAGES.map(([label, href, desc]) => (
                    <tr key={href} className="align-top">
                      <td className="border-b border-slate-100 py-2 pr-4 whitespace-nowrap font-medium text-slate-800">
                        {label}
                      </td>
                      <td className="border-b border-slate-100 py-2 pr-4 whitespace-nowrap">
                        <Link href={href} className="font-mono text-xs text-sky-700 hover:underline">
                          {href}
                        </Link>
                      </td>
                      <td className="border-b border-slate-100 py-2 text-slate-600">{desc}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          <Section
            id="account"
            icon={<UserRound className="size-4" aria-hidden />}
            title="账号与登录"
            subtitle="登录状态、忘记密码与改密。"
          >
            <ul className="list-disc space-y-1.5 pl-5">
              <li>注册后自动登录；连续登录失败会触发限流，稍等再试。</li>
              <li>登录状态默认保持 <strong>30 天</strong>，到期需要重新登录。</li>
              <li>
                <strong>忘记密码</strong>：登录页点「忘记密码？」，输入邮箱与新密码（≥ 8 位）。
              </li>
              <li>
                <strong>修改密码</strong>：设置页最下方「账号安全」。改完当前浏览器保持登录，
                其他设备的会话立即失效。
              </li>
              <li>密码以 Argon2id 单向哈希保存，无法查看原文，只能重置。</li>
            </ul>
          </Section>

          <Section
            id="resume"
            icon={<FileSearch className="size-4" aria-hidden />}
            title="简历与画像"
            subtitle="解析结果只是草稿，确认后才生效。"
          >
            <ul className="list-disc space-y-1.5 pl-5">
              <li>解析会按简历章节分栏：实习进「实习与项目经历」，项目与科研进「项目」。</li>
              <li>时间范围统一成 <code className="rounded bg-slate-100 px-1">2025.10 - 2026.01</code> 的形式。</li>
              <li>修改已确认的画像会自动失效，需要重新确认。</li>
              <li>有未保存修改时顶部会提示，刷新或误关页面后草稿会恢复（按账号隔离）。</li>
            </ul>
          </Section>

          <Section
            id="jobs"
            icon={<FileSearch className="size-4" aria-hidden />}
            title="找岗位"
            subtitle="三种来源，可信度不同。"
          >
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl bg-slate-50 p-4">
                <p className="text-sm font-medium text-slate-900">发现岗位</p>
                <p className="mt-1 text-xs text-slate-600">
                  官方直连（已适配 7 家），或关键词搜索；结果分「候选」与「已核验」。
                </p>
              </div>
              <div className="rounded-xl bg-slate-50 p-4">
                <p className="text-sm font-medium text-slate-900">导入岗位</p>
                <p className="mt-1 text-xs text-slate-600">
                  粘贴官方详情页链接，或直接粘 JD 存为仅自己可见的私有候选。
                </p>
              </div>
              <div className="rounded-xl bg-slate-50 p-4">
                <p className="text-sm font-medium text-slate-900">岗位库</p>
                <p className="mt-1 text-xs text-slate-600">
                  只收录读到官方详情页的岗位，可按企业、城市、类型筛选。
                </p>
              </div>
            </div>
            <Tip tone="warn">
              搜索摘要不等于完整 JD；只有读到官方详情页才会进入岗位库。
            </Tip>
          </Section>

          <Section
            id="maintain"
            icon={<Wrench className="size-4" aria-hidden />}
            title="维护岗位库"
            subtitle="岗位库顶部的「更新岗位」与「清理已下线」，都是手动触发。"
          >
            <p>
              <strong>更新岗位</strong>会先显示范围：当前筛选命中多少岗位、本次上限（40 / 100 / 200）、
              以及不支持自动发现的企业。可勾选「复核已有岗位」（默认）与「发现新增岗位」。
            </p>
            <ul className="list-disc space-y-1.5 pl-5">
              <li>复核按「最久未检查优先」，连续点两次会继续往后覆盖，不会重复同一批。</li>
              <li>默认跳过最近 6 小时内已成功复核的岗位（可选不跳过 / 6 小时 / 24 小时 / 3 天）。</li>
              <li>只有官方页面明确写了「职位已下架 / 招聘已结束」才会标记下线并存证。</li>
              <li>超时、登录页、空正文、跳转列表页一律记为「无法确认」，保持原状态，下次会重试。</li>
            </ul>
            <p>
              <strong>清理已下线</strong>先展示预览（岗位、企业、检查时间、判定依据），确认后执行
              <strong>软归档</strong>：退出检索与推荐，但收藏、申请与历史详情都保留，管理员可在
              「查看已归档」里恢复（恢复不代表重新在招）。
            </p>
            <Tip tone="warn">
              清理 / 归档 / 恢复是<strong>全局操作</strong>，需要管理员权限；普通用户仍可使用「更新岗位」。
            </Tip>
          </Section>

          <Section
            id="match"
            icon={<Sparkles className="size-4" aria-hidden />}
            title="推荐与匹配"
            subtitle="分数来自系统的匹配服务，不是模型编的。"
          >
            <ul className="list-disc space-y-1.5 pl-5">
              <li>只用<strong>已确认画像</strong>计算分数；每条包含分数、资格判断、命中技能与缺口。</li>
              <li>「只看符合我资格的岗位」默认开启，隐藏数量会写在旁边。</li>
              <li>资格「不符合」仍会展示并列出硬性条件（毕业年份、学历），它说的是「能不能投」。</li>
            </ul>
          </Section>

          <Section
            id="apply"
            icon={<CalendarCheck className="size-4" aria-hidden />}
            title="投递与面试"
            subtitle="状态、时间线与日历是三块不同的东西。"
          >
            <ul className="list-disc space-y-1.5 pl-5">
              <li>看板支持列表 / 表格 / 看板三种视图，行内下拉可直接改状态。</li>
              <li>每条申请可「登记笔试 / 面试预约」，支持「新增一轮」与「改期（仅替换选中那条）」。</li>
              <li>日历只显示<strong>已预约</strong>的笔试 / 面试 / 在线测评，投递状态不进日历。</li>
              <li>上传招聘通知 <code className="rounded bg-slate-100 px-1">.eml</code> 会先预览，确认后才写入时间线。</li>
            </ul>
          </Section>

          <Section
            id="agent"
            icon={<Bot className="size-4" aria-hidden />}
            title="Agent 工作台"
            subtitle="可以追问，可以中途切页，任务不会丢。"
          >
            <p>提交后立即返回，任务在后台执行，页面实时显示阶段与工具调用。</p>
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-500">
                    <th className="border-b border-slate-200 py-2 pr-4 font-medium">你说</th>
                    <th className="border-b border-slate-200 py-2 font-medium">效果</th>
                  </tr>
                </thead>
                <tbody>
                  {MULTI_TURN.map(([ask, effect]) => (
                    <tr key={ask}>
                      <td className="border-b border-slate-100 py-2 pr-4 whitespace-nowrap text-slate-800">
                        {ask}
                      </td>
                      <td className="border-b border-slate-100 py-2 text-slate-600">{effect}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul className="list-disc space-y-1.5 pl-5">
              <li>运行中可「停止任务」；执行有 300 秒上限，超时会标记为失败/超时。</li>
              <li>切到其他页面任务继续跑，左侧「Agent 工作台」旁会出现加载图标，回来自动补进度。</li>
              <li>画像未确认而本次需要完整匹配时，会暂停并提示「去确认画像」或「已确认，继续」。</li>
            </ul>
            <Tip tone="warn">
              Agent 只推荐它真的检索到的岗位；没有符合条件的结果时会直接说「没有」，不会把最接近的包装成推荐。
            </Tip>
          </Section>

          <Section
            id="keys"
            icon={<KeyRound className="size-4" aria-hidden />}
            title="模型与搜索 Key"
            subtitle="多账号共用部署时，各用各的额度。"
          >
            <ul className="list-disc space-y-1.5 pl-5">
              <li>设置页「模型 API」支持 OpenAI 兼容（可填自建网关）与 Anthropic，模型名可留空用默认。</li>
              <li>「搜索 API（Tavily）」用于实时检索，未配置时只查岗位库、不发实时请求。</li>
              <li>两处都有「测试连接」，会发一次最小真实请求并显示耗时与错误原文。</li>
              <li>Key 加密存储，接口只返回 <code className="rounded bg-slate-100 px-1">sk-ab…9f2c</code> 形式的掩码。</li>
              <li>服务端默认 Key 默认<strong>只对管理员开放</strong>，其他账号需自己配置，不会花部署者的额度。</li>
            </ul>
            <Tip>
              想回退到服务端默认：点「清除，改用服务端默认」。若你不是管理员且服务端限制共享，Agent 会提示先配置。
            </Tip>
          </Section>

          <Section
            id="mobile"
            icon={<Laptop className="size-4" aria-hidden />}
            title="手机与多端"
            subtitle="同一 Wi-Fi 直接用，异地用 Tailscale。"
          >
            <ul className="list-disc space-y-1.5 pl-5">
              <li>手机与电脑连同一 Wi-Fi，浏览器打开 <code className="rounded bg-slate-100 px-1">http://电脑IP:3000</code>。</li>
              <li>不在同一网络时，两台设备装 Tailscale 并登录同一账号，用 <code className="rounded bg-slate-100 px-1">100.x.x.x:3000</code> 访问。</li>
              <li>页面与接口都走 3000 一个端口，换网络只需换地址，不用改配置或重建镜像。</li>
              <li>手机上左侧栏收进左上角菜单；任务面板与卡片可上下滑动。</li>
            </ul>
          </Section>

          <Section
            id="limits"
            icon={<ShieldCheck className="size-4" aria-hidden />}
            title="限制与边界"
            subtitle="写在这里，而不是藏在设置里。"
          >
            <ul className="list-disc space-y-1.5 pl-5">
              <li>不自动投递、不自动填表、不代登录招聘平台；不保存平台密码。</li>
              <li>官方直连目前 7 家（腾讯、京东、字节、小红书、美团、B站、MiniMax），其余需手动导入。</li>
              <li>在线搜索需要 Tavily Key；未配置时直连与手动导入仍可用。</li>
              <li>岗位维护单次上限 200 个，发现最多 6 家企业；全量需要分批执行。</li>
              <li>没有 PWA / 原生 App：不支持离线，也不能像 App 一样全屏启动。</li>
              <li>邮件同步依赖自备 Gmail OAuth 或 QQ 邮箱授权码，只产生「待确认」候选。</li>
            </ul>
          </Section>

          <div className="rounded-2xl border border-slate-200 bg-slate-900 p-6 text-slate-300">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <BellRing className="size-4 text-sky-400" aria-hidden />
                <p className="text-sm text-white">还有问题？</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Link
                  href="/agent"
                  className="inline-flex items-center gap-1.5 rounded-lg bg-white px-3 py-2 text-xs font-medium text-slate-900"
                >
                  去问 Agent
                  <ArrowRight className="size-3.5" aria-hidden />
                </Link>
                <Link
                  href="/settings/email"
                  className="inline-flex items-center gap-1.5 rounded-lg border border-white/20 px-3 py-2 text-xs text-white"
                >
                  打开设置
                </Link>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
            <ListChecks className="size-3.5" aria-hidden />
            <span>共 {SECTIONS.length} 节</span>
            <span>·</span>
            <Mail className="size-3.5" aria-hidden />
            <span>完整版见 docs/USER_GUIDE.md</span>
            <span>·</span>
            <Wrench className="size-3.5" aria-hidden />
            <span>实现细节见 docs/IMPLEMENTATION_STATUS.md</span>
          </div>
        </div>
      </div>
    </div>
  );
}
