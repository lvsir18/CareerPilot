/**
 * Content for the in-app manual (`/guide`).
 *
 * Kept as data so the page stays a thin renderer: adding a section should not
 * mean editing JSX. Mirrors `docs/USER_GUIDE.md` but written for the browser
 * (tables, steps, tips) and extended with the self-hosting bits an open-source
 * reader needs.
 */

export type GuideBlock =
  | { kind: "image"; src: string; alt: string; caption: string; width: number; height: number }
  | { kind: "p"; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "steps"; items: { title: string; body: string; href?: string }[] }
  | { kind: "table"; head: string[]; rows: string[][] }
  | { kind: "tip"; tone?: "info" | "warn"; text: string }
  | { kind: "code"; text: string; caption?: string };

export type GuideSubsection = {
  id: string;
  title: string;
  blocks: GuideBlock[];
};

export type GuideIcon =
  | "sparkles"
  | "rocket"
  | "map"
  | "user"
  | "file"
  | "compass"
  | "link"
  | "briefcase"
  | "target"
  | "calendar"
  | "bot"
  | "key"
  | "smartphone"
  | "settings"
  | "help"
  | "shield";

export type GuideSection = {
  id: string;
  icon: GuideIcon;
  title: string;
  summary: string;
  blocks?: GuideBlock[];
  subsections?: GuideSubsection[];
};

export const GUIDE_SECTIONS: GuideSection[] = [
  {
    id: "what",
    icon: "sparkles",
    title: "它能做什么，不做什么",
    summary: "定位：把求职从海投变成一条可核验的流程",
    blocks: [
      {
        kind: "p",
        text: "CareerPilot 是一个本地 / 私有部署的求职工作台：把「找岗位、比画像、投递、跟进」串成一条链路，求职数据保存在你的部署环境中；启用外部模型或搜索时，相关内容会发给所选服务商。",
      },
      {
        kind: "steps",
        items: [
          {
            title: "官方岗位库",
            body: "只收录读到官方详情页的岗位，城市、部门、JD、发布时间都来自官网本身。",
            href: "/jobs",
          },
          {
            title: "可解释的匹配",
            body: "用确认过的画像给岗位打分，列出「符合什么、缺什么」，不给玄学分数。",
            href: "/matches",
          },
          {
            title: "能追问的 Agent",
            body: "多轮对话里能接着问「那杭州呢」「把第一个岗位的 JD 发我」。",
            href: "/agent",
          },
          {
            title: "投递与面试时间线",
            body: "记录投递阶段与明确预约；邮件识别结果先作为候选，确认后写入时间线。",
            href: "/applications",
          },
        ],
      },
      { kind: "p", text: "**明确的边界**（这是设计选择，不是待办）：" },
      {
        kind: "list",
        items: [
          "不自动投递、不代填表单、不绕验证码；",
          "不保存招聘平台的账号密码；",
          "搜索摘要 ≠ 完整 JD：没读到官方详情页的岗位只作为「候选」，不会伪装成正式岗位；",
          "不会因为抓取失败就把岗位判定为「已下线」，只记为「无法确认」。",
        ],
      },
      {
        kind: "tip",
        tone: "warn",
        text: "所有外部官网抓取都是只读的公开页面访问，频率受控；如果某个站点需要登录，系统会如实报告「读不到」，而不是编造内容。",
      },
    ],
  },
  {
    id: "start",
    icon: "rocket",
    title: "快速开始（自部署）",
    summary: "从环境检查到第一次完整使用",
    subsections: [
      {
        id: "start-requirements",
        title: "环境要求",
        blocks: [
          {
            kind: "table",
            head: ["依赖", "版本", "说明"],
            rows: [
              ["Docker + Docker Compose", "24+", "API / worker / web / Postgres / Redis 全部跑在容器里"],
              ["内存", "≥ 8 GB", "Playwright 渲染官网详情页时占用较高"],
              ["磁盘", "≥ 10 GB", "镜像 + 数据库 + 简历文件"],
              ["网络", "可出网", "访问企业官网与模型 API（国内建议配 npm 镜像）"],
            ],
          },
          {
            kind: "tip",
            text: "不需要本地装 Python / Node：镜像里已经带好。只有做二次开发时才需要本地工具链。",
          },
        ],
      },
      {
        id: "start-run",
        title: "启动",
        blocks: [
          {
            kind: "code",
            caption: "首次部署",
            text: "git clone https://github.com/lvsir18/CareerPilot.git careerpilot\ncd careerpilot\ncp .env.example .env        # 按需修改，见「配置速查」\ndocker compose up -d --build\ndocker compose exec api alembic upgrade head",
          },
          {
            kind: "code",
            caption: "确认服务健康",
            text: "curl -s http://localhost:8000/readyz   # → {\"status\":\"ok\"}\ncurl -s -o /dev/null -w '%{http_code}\\n' http://localhost:3000/login  # → 200",
          },
          { kind: "p", text: "然后浏览器打开 `http://localhost:3000`，注册第一个账号并登录。" },
          {
            kind: "tip",
            tone: "warn",
            text: "第一个注册的账号不会自动成为管理员：把邮箱写进 .env 的 ADMIN_EMAILS（逗号分隔），再 docker compose up -d api worker。",
          },
        ],
      },
      {
        id: "start-first-run",
        title: "第一次使用的四步",
        blocks: [
          {
            kind: "steps",
            items: [
              { title: "上传简历", body: "PDF / DOCX，解析成画像草稿。", href: "/profile" },
              { title: "确认画像", body: "补技能、改城市与方向偏好；未确认前不会给匹配分。", href: "/profile" },
              { title: "找岗位", body: "官网直连或关键词搜索，核验后进入岗位库。", href: "/discover" },
              { title: "开始投递", body: "收藏、加投递清单，用 Agent 追问细节。", href: "/jobs" },
            ],
          },
        ],
      },
    ],
  },
  {
    id: "pages",
    icon: "map",
    title: "页面地图",
    summary: "每个入口做什么",
    blocks: [
      {
        kind: "table",
        head: ["页面", "路径", "作用"],
        rows: [
          ["首页", "/home", "系统介绍与四个起点入口"],
          ["概览", "/dashboard", "统计、最新岗位、最近进度、即将开始的日程"],
          ["发现岗位", "/discover", "官网直连检索 / 关键词搜索 / 候选核验"],
          ["导入岗位", "/import", "粘贴官方链接或 JD"],
          ["岗位库", "/jobs", "已核验岗位，可筛选与维护"],
          ["岗位详情", "/jobs/{id}", "完整 JD、匹配分数、收藏与投递"],
          ["岗位推荐", "/matches", "按画像排序的推荐列表"],
          ["投递看板", "/applications", "投递状态流转与申请详情"],
          ["面试日程", "/calendar", "面试安排与日历视图"],
          ["Agent 工作台", "/agent", "多轮对话：找岗位、比画像、查进度"],
          ["收藏岗位", "/saved-jobs", "已收藏与投递清单"],
          ["简历与画像", "/profile", "上传简历、编辑并确认画像"],
          ["设置", "/settings/email", "邮箱同步、模型 API、搜索 API、账号安全"],
          ["使用手册", "/guide", "当前页面"],
        ],
      },
      { kind: "p", text: "手机上左侧栏收起，点左上角菜单按钮打开导航，点任意链接会自动收起。" },
    ],
  },
  {
    id: "account",
    icon: "user",
    title: "账号与登录",
    summary: "注册、密码、会话有效期",
    blocks: [
      {
        kind: "list",
        items: [
          "注册后自动登录，邮箱统一转小写存储；密码要求 ≥ 8 位，用 Argon2id 单向哈希，无法找回原文；",
          "登录状态默认保持 **30 天**（`AUTH_SESSION_TTL_DAYS`），到期需重新登录；",
          "连续登录失败会触发限流（返回 429），等几分钟再试；",
          "所有写操作都带 CSRF 校验：出现「CSRF 校验失败」时刷新页面再操作即可。",
        ],
      },
      {
        kind: "table",
        head: ["场景", "做法"],
        rows: [
          ["忘记密码", "登录页点「忘记密码？」，输入邮箱 + 新密码（需开启 `PASSWORD_RESET_ENABLED`）"],
          ["修改密码", "设置页最下方「账号安全」，输入当前密码 + 新密码；修改后其他设备立即掉线"],
          ["退出登录", "侧栏底部退出，同时清空本机画像草稿"],
        ],
      },
      {
        kind: "tip",
        tone: "warn",
        text: "只要服务暴露到公网，就应关闭 PASSWORD_RESET_ENABLED —— 否则知道邮箱的人可以直接改密码。",
      },
    ],
  },
  {
    id: "profile",
    icon: "file",
    title: "简历与画像",
    summary: "上传一次，之后所有匹配都基于它",
    subsections: [
      {
        id: "profile-upload",
        title: "上传与解析",
        blocks: [
          {
            kind: "list",
            items: [
              "支持 PDF / DOCX，大小上限由 `MAX_RESUME_MB` 控制（默认 10 MB）；",
              "解析出教育经历、实习/项目、技能、意向城市与方向，生成**草稿**，不会直接覆盖已确认画像；",
              "解析失败时可手动填写，或只上传部分内容。",
            ],
          },
        ],
      },
      {
        id: "profile-confirm",
        title: "确认画像",
        blocks: [
          {
            kind: "p",
            text: "画像里包含五部分：技能、教育、实习经历、项目经历、求职偏好。**未确认的画像不会参与匹配打分。**",
          },
          {
            kind: "tip",
            text: "项目与实习的描述越具体（技术栈、数据规模、指标结果），匹配解释与 Agent 的分析就越有据可依。",
          },
          { kind: "p", text: "确认后可以在任何时间回来修改，改动会立即影响后续匹配结果。" },
        ],
      },
    ],
  },
  {
    id: "discover",
    icon: "compass",
    title: "找岗位：发现与核验",
    summary: "两种检索方式 + 候选核验",
    subsections: [
      {
        id: "discover-official",
        title: "A. 官网直连检索",
        blocks: [
          {
            kind: "p",
            text: "由服务端浏览器把关键词输入企业官方搜索框，直接读取真实岗位（标题、城市、招聘类型、完整 JD）。当前已适配 7 家：",
          },
          {
            kind: "table",
            head: ["企业", "方式", "备注"],
            rows: [
              ["腾讯", "官方 JSON 接口", "最快，但没有发布时间"],
              ["京东", "官方 JSON 接口", "详情链接按 `#/details?id=` 生成，可复核"],
              ["字节跳动", "浏览器渲染", "虚拟列表，单次约 10 条"],
              ["小红书", "浏览器渲染", "支持滚动翻页"],
              ["美团", "官方 JSON 接口", "秒级，含部门与更新时间"],
              ["哔哩哔哩", "浏览器渲染", "—"],
              ["MiniMax", "飞书 ATS", "按租户路径精确匹配"],
            ],
          },
          {
            kind: "tip",
            text: "其余企业会明确标注「不支持自动发现」，不会假装成功。这类企业可以用「导入岗位」手动加官方链接。",
          },
        ],
      },
      {
        id: "discover-search",
        title: "B. 关键词实时搜索",
        blocks: [
          {
            kind: "list",
            items: [
              "需要配置 Tavily Key（可在设置页填自己的，见「模型与搜索 Key」）；",
              "搜索返回的是**候选链接**（标题 + 摘要），不是完整 JD；",
              "岗位方向、城市、招聘类型可以组合筛选，方向按 8 个大类划分；",
              "进入页面不会自动检索：填好条件点「搜索」才会消耗额度。",
            ],
          },
          {
            kind: "tip",
            tone: "warn",
            text: "命中限流时会提示「每分钟最多 30 次搜索，本次已跳过」——本次只返回库内已有岗位，等 1 分钟再试。每日另有总预算（默认 500 次）。",
          },
        ],
      },
      {
        id: "discover-verify",
        title: "候选核验",
        blocks: [
          {
            kind: "list",
            items: [
              "**批量核验**：当前页最多 10 条，逐条处理，单条失败不影响其他；",
              "**按企业一键核验**：把所选企业的全部候选交给后台队列，不受每分钟限流（单次上限 1000 条）；",
              "可选「全选」或「自定义数量」；后台执行，切页不中断，可随时取消；",
              "核验成功才会写入岗位库，失败会保留候选并记录原因。",
            ],
          },
          {
            kind: "p",
            text: "核验时会优先用本地浏览器渲染页面（阿里、快手等前端渲染站点也能读到 JD），渲染读不到才退回静态抽取。",
          },
        ],
      },
    ],
  },
  {
    id: "import",
    icon: "link",
    title: "导入岗位",
    summary: "官方链接或已核实的 JD",
    blocks: [
      {
        kind: "table",
        head: ["方式", "适合", "结果"],
        rows: [
          ["官方链接", "企业有公开详情页", "解析后预览，确认即入库"],
          ["粘贴 JD", "需要登录 / 页面读不到", "保存为仅本人可见的私有岗位"],
        ],
      },
      {
        kind: "list",
        items: [
          "链接必须是 https 的官方详情页；域名属于已收录的 19 家企业（含任意子域）即可核验；",
          "页面上的「在招业务 / 部门」「更新于 / 更新时间」「招聘项目」「职位类别」都会被解析入库；",
          "没写这些标签的岗位对应字段留空，不做猜测。",
        ],
      },
    ],
  },
  {
    id: "jobs",
    icon: "briefcase",
    title: "岗位库与维护",
    summary: "筛选、复核、发现新增、归档",
    subsections: [
      {
        id: "jobs-filter",
        title: "筛选与查看",
        blocks: [
          {
            kind: "list",
            items: [
              "只收录**已读到官方详情页**的岗位，候选不会混进来；",
              "支持关键词、城市、招聘类型、岗位方向（8 个大类）、来源与招聘项目组合筛选；",
              "详情页展示完整 JD、部门、发布时间、匹配分数与「符合 / 缺少」的技能项。",
            ],
          },
        ],
      },
      {
        id: "jobs-maintain",
        title: "更新岗位（复核 + 发现新增）",
        blocks: [
          {
            kind: "p",
            text: "点「更新岗位」先弹范围确认，明确显示「当前筛选共 N 个岗位 · 本次最多复核 M 个 · 不支持自动发现的企业」，避免把「当前筛选」误解成「当前页」。",
          },
          {
            kind: "table",
            head: ["结果", "含义"],
            rows: [
              ["新增", "发现新岗位并入库"],
              ["内容更新", "JD、城市、部门等字段发生变化"],
              ["内容未变", "检查过，内容一致（只更新时间）"],
              ["确认下线", "官网明确写了「职位已下架 / 招聘已结束」"],
              ["恢复在招", "之前判为下线，本次读到明确在招"],
              ["无法确认", "超时、登录页、跳转列表页等 —— 保持原状态"],
              ["不支持", "该企业尚未适配自动发现"],
            ],
          },
          {
            kind: "list",
            items: [
              "复核顺序是**最久没检查的优先**，连续点两次会继续往后覆盖；",
              "默认跳过最近 6 小时内已成功复核的岗位（可选 不跳过 / 6 / 24 / 72 小时）；",
              "复核失败（无法确认）不写冷却，下次会优先重试；",
              "「发现新增」可选深度：快速（每家 10 条）、标准（30 条）、深度（50 条 + 多关键词）。",
            ],
          },
          {
            kind: "tip",
            text: "任务在后台执行：切页也会继续，左侧「岗位库」旁有旋转图标；回到页面会自动接管进度，也可点「取消任务」（当前这条处理完就停）。",
          },
        ],
      },
      {
        id: "jobs-archive",
        title: "清理已下线（管理员）",
        blocks: [
          {
            kind: "list",
            items: [
              "先预览，只列出**有明确下线证据**的岗位（企业、岗位、检查时间、判定依据）；",
              "执行后是**软归档**：不再出现在列表、推荐与 Agent 结果中，但收藏、申请、匹配历史都保留；",
              "管理员可在「查看已归档」里恢复 —— 恢复只代表取消归档，不代表岗位重新在招。",
            ],
          },
          {
            kind: "tip",
            tone: "warn",
            text: "清理、查看归档、恢复都是全局操作，只对 ADMIN_EMAILS 里的账号开放；普通用户看不到这些按钮。",
          },
        ],
      },
    ],
  },
  {
    id: "matches",
    icon: "target",
    title: "推荐与匹配",
    summary: "分数怎么来的，为什么有时不给分",
    blocks: [
      {
        kind: "list",
        items: [
          "匹配基于**已确认画像**：技能标签、教育背景、实习与项目经历、求职偏好；",
          "分数是规则化比对结果（技能命中、方向一致、城市与类型匹配），每一分都能对应到具体依据；",
          "画像未确认时不给分数，只提示先去确认；",
          "列表按分数与新鲜度排序，详情页会展开「符合」「暂未体现」两类技能。",
        ],
      },
      {
        kind: "tip",
        text: "分数是筛选工具，不是录取概率预测。看到高分也请自己核对 JD；看到低分可以点开看缺了什么，用来决定要不要补技能。",
      },
    ],
  },
  {
    id: "applications",
    icon: "calendar",
    title: "投递与面试",
    summary: "看板、邮件解析与日历",
    subsections: [
      {
        id: "applications-board",
        title: "投递看板",
        blocks: [
          {
            kind: "list",
            items: [
              "状态流转：已投递 → 笔试 / 面试 → Offer / 已拒绝 / 已放弃；",
              "可以从岗位详情「加入待投递清单」开始，也可以手动新建；",
              "每条申请有独立详情页：关联岗位、时间线、面试安排与备注。",
            ],
          },
        ],
      },
      {
        id: "applications-email",
        title: "邮件同步（可选）",
        blocks: [
          {
            kind: "table",
            head: ["邮箱", "凭据", "正常寿命", "失效原因"],
            rows: [
              ["Gmail", "OAuth refresh token", "长期", "OAuth 应用处于 Testing → 7 天过期；改密码；撤销授权；6 个月未用"],
              ["QQ 邮箱", "IMAP 授权码", "长期", "改密码；关闭 IMAP/SMTP；腾讯安全策略回收"],
            ],
          },
          {
            kind: "list",
            items: [
              "同步只读取招聘相关邮件（面试邀请、测评、Offer），不会上传整箱邮件；",
              "识别出的信息先进入「邮件候选」，确认后才写入申请时间线；",
              "同步在后台执行；异常会在设置页显示原因与上次成功时间。",
            ],
          },
          {
            kind: "tip",
            tone: "warn",
            text: "如果 Gmail 每 7 天就要重绑，去 Google Cloud Console 把 OAuth 应用从 Testing 发布为 In production。",
          },
        ],
      },
      {
        id: "applications-calendar",
        title: "面试日程",
        blocks: [
          {
            kind: "p",
            text: "面试邀请解析出的时间会进入日历；时间冲突会提示，改期后原时段自动释放。",
          },
        ],
      },
    ],
  },
  {
    id: "agent",
    icon: "bot",
    title: "Agent 工作台",
    summary: "能追问的求职助手",
    subsections: [
      {
        id: "agent-ask",
        title: "怎么问",
        blocks: [
          {
            kind: "list",
            items: [
              "「帮我找北京的大模型实习」—— 检索并给出推荐与理由；",
              "「哪些岗位更适合我的简历？」—— 结合画像与岗位库排序；",
              "「看看我最近的申请进度」—— 读取投递与面试记录；",
              "「我的项目经历够不够垂直？」—— 会读取画像里的项目与实习正文逐条分析并指出缺口。",
            ],
          },
        ],
      },
      {
        id: "agent-multi-turn",
        title: "多轮追问",
        blocks: [
          {
            kind: "table",
            head: ["你说", "效果"],
            rows: [
              ["「找北京的大模型实习」→「那杭州呢」", "只换城市，保留「大模型 + 实习」"],
              ["「把第一个岗位的 JD 发我」", "指回上一轮的第一个结果"],
              ["「刚才杭州那边你找到几个？」", "直接引用上一轮统计，不重搜"],
              ["「看看我最近的申请进度」", "换主题时不继承上一轮检索条件"],
            ],
          },
          {
            kind: "p",
            text: "单次对话最多保留最近 10 轮消息用于理解追问；更早的检索范围仍由「上一轮检索范围」承接。",
          },
        ],
      },
      {
        id: "agent-run",
        title: "执行与中断",
        blocks: [
          {
            kind: "list",
            items: [
              "提交后立即返回，任务在后台执行，页面实时显示阶段与工具调用（SSE 推送）；",
              "断线会自动降级为轮询；刷新页面会恢复最近一次运行状态；",
              "运行中可点「停止任务」；单次执行有 300 秒硬上限；",
              "切到其他页面任务不会中断，左侧「Agent 工作台」旁有旋转图标，回来会自动续上。",
            ],
          },
          {
            kind: "tip",
            text: "需要确认画像时，Agent 会停下来等你点确认，而不是自己编一个画像继续算分。",
          },
        ],
      },
    ],
  },
  {
    id: "keys",
    icon: "key",
    title: "模型与搜索 Key（按账号隔离）",
    summary: "多账号共用部署时，各花各的额度",
    blocks: [
      {
        kind: "p",
        text: "服务端 .env 可以配一份默认 Key，但它属于部署者。为避免「一个人的额度给所有人花」，每个账号可以在设置页配置自己的 Key。",
      },
      {
        kind: "table",
        head: ["项目", "模型 API", "搜索 API（Tavily）"],
        rows: [
          ["入口", "设置页「模型 API」", "设置页「搜索 API（Tavily）」"],
          ["提供方", "OpenAI 兼容（可填 Base URL）/ Anthropic", "Tavily"],
          ["生效范围", "只影响自己的 Agent 任务", "只影响自己的实时检索"],
          ["不配置时", "管理员用服务端默认；其他账号提示去配置", "管理员用服务端默认；其他账号只查岗位库"],
          ["测试连接", "发一次最小请求并显示耗时", "发一次搜索（约 1 credit）"],
        ],
      },
      {
        kind: "list",
        items: [
          "Key 加密存储，接口只返回掩码（如 sk-ab…9f2c），日志不记明文；",
          "首次保存必须填 Key；之后只改模型或 Base URL 时可以留空沿用；",
          "解析顺序：自己的 Key → 服务端默认（仅管理员）→ 报错，不会静默使用别人的 Key。",
        ],
      },
    ],
  },
  {
    id: "mobile",
    icon: "smartphone",
    title: "手机与多端访问",
    summary: "响应式 Web，无需安装 App",
    subsections: [
      {
        id: "mobile-lan",
        title: "同一个 Wi-Fi",
        blocks: [
          {
            kind: "code",
            caption: "查本机局域网地址（macOS）",
            text: "ipconfig getifaddr en0   # 例如 192.168.1.10\n# 手机浏览器打开 http://192.168.1.10:3000",
          },
          {
            kind: "p",
            text: "页面与接口都走 3000 一个端口（前端把 /api/v1/* 反向代理到后端），换网络或 IP 变化不需要重建镜像，在手机上输入新地址即可。",
          },
        ],
      },
      {
        id: "mobile-tailscale",
        title: "不在同一个网络",
        blocks: [
          {
            kind: "list",
            items: [
              "电脑和手机都装 Tailscale 并登录同一账号，相当于处在同一内网；",
              "电脑上执行 tailscale ip -4 得到 100.x.x.x 地址，手机浏览器打开 http://100.x.x.x:3000；",
              "Tailscale 地址不随网络变化，比局域网 IP 稳定。",
            ],
          },
          {
            kind: "tip",
            tone: "warn",
            text: "局域网 / Tailscale 访问若提示「请求来源不受信任」，把 .env 的 ALLOW_LAN_ORIGINS 设为 true，再执行 docker compose up -d api；公网域名必须显式写进 CSRF_TRUSTED_ORIGINS。",
          },
        ],
      },
    ],
  },
  {
    id: "config",
    icon: "settings",
    title: "配置速查",
    summary: "最常改的几个环境变量",
    blocks: [
      {
        kind: "table",
        head: ["变量", "作用", "默认"],
        rows: [
          ["SESSION_SECRET", "会话与 CSRF 签名密钥", "必须改成随机值"],
          ["ADMIN_EMAILS", "管理员邮箱（逗号分隔）", "空 → 无管理员"],
          ["AUTH_SESSION_TTL_DAYS", "登录保持天数", "30"],
          ["PASSWORD_RESET_ENABLED", "是否允许自助重置密码", "true（公网请关）"],
          ["ALLOW_LAN_ORIGINS", "是否放行局域网 / Tailscale 来源", "false"],
          ["LLM_PROVIDER / LLM_BASE_URL / LLM_API_KEY / LLM_MODEL", "服务端默认模型", "空 → 未配置"],
          ["TAVILY_API_KEY", "服务端默认搜索 Key", "空 → 未配置"],
          ["SHARED_LLM_KEY_ADMINS_ONLY", "默认模型 Key 是否仅管理员可用", "true"],
          ["SHARED_SEARCH_KEY_ADMINS_ONLY", "默认搜索 Key 是否仅管理员可用", "true"],
          ["SEARCH_RATE_LIMIT_PER_MINUTE", "每账号每分钟搜索上限", "30"],
          ["SEARCH_DAILY_BUDGET_PER_PROVIDER", "每日搜索总预算", "500"],
          ["MAX_RESUME_MB", "简历文件大小上限", "10"],
          ["MAILBOX_SECRET_KEY", "邮箱凭据加密密钥（丢失需重绑）", "空 → 无法绑定邮箱"],
          ["JOB_DISCOVER_MAX_PER_COMPANY", "发现新增时每家抓取条数上限", "100"],
        ],
      },
      {
        kind: "code",
        caption: "改完配置后",
        text: "docker compose up -d api worker    # 让后端读取新的 .env\ndocker compose build web && docker compose up -d web   # 只有前端变量才需要重建",
      },
    ],
  },
  {
    id: "faq",
    icon: "help",
    title: "常见问题",
    summary: "踩坑最多的十件事",
    blocks: [
      {
        kind: "list",
        items: [
          "**忘记密码怎么办？** 登录页「忘记密码？」自助重置（需开启 PASSWORD_RESET_ENABLED）；已登录可在设置页「账号安全」改密。",
          "**手机打不开页面 / 登录后马上变未登录？** 确认在同一 Wi-Fi 或同一 Tailscale 网络，用 http://<电脑IP>:3000，不要用 localhost。",
          "**手机提示「请求来源不受信任」？** 设置 ALLOW_LAN_ORIGINS=true，再执行 docker compose up -d api；用域名访问时把域名加进 CSRF_TRUSTED_ORIGINS。",
          "**点了「更新岗位」好像还是同一批？** 复核是最久未检查优先，并默认跳过 6 小时内已成功复核的岗位；想扫全库把「跳过」设为不跳过、上限 200，连点两次。",
          "**为什么看不到「清理已下线」？** 这些是全局操作，只对 ADMIN_EMAILS 里的账号显示。",
          "**「发现新增」没有新岗位？** 官网列表按发布时间倒序，每家默认只看前 N 条；已入库时结果就是「内容未变」。可以提高深度或多关键词。",
          "**为什么某个岗位 JD 是空的？** 官网接口或详情页本身没有正文（例如腾讯部分「青云课题」岗位），系统不会编造。",
          "**Agent 说「未配置模型」？** 去设置页「模型 API」填自己的 Key，或让管理员配置服务端默认 Key。",
          "**搜索总提示限流？** 实时搜索有每分钟与每日额度；进入页面不会自动搜，点「搜索」才消耗额度。",
          "**邮箱总掉线？** Gmail 若每 7 天失效是 OAuth 应用仍在 Testing；QQ 授权码失效需重新生成并重绑。",
        ],
      },
    ],
  },
  {
    id: "limits",
    icon: "shield",
    title: "限制、边界与路线图",
    summary: "目前做不到什么，以及为什么",
    blocks: [
      {
        kind: "table",
        head: ["能力", "现状", "原因"],
        rows: [
          ["自动发现企业", "7 家直连", "其余站点需要登录、前端签名或版权限制；可手动导入"],
          ["单次复核", "≤ 200 个岗位", "每个岗位要开一次浏览器，避免长时间占用资源"],
          ["单次核验候选", "≤ 1000 条", "同上，且受第三方站点频率限制"],
          ["Agent 单次执行", "≤ 300 秒", "防止单次任务无限占用 worker"],
          ["岗位方向", "8 个大类", "过细会让分类互相重叠，按大厂岗位类型划分更稳定"],
          ["多端", "响应式 Web", "没有 PWA / 原生 App；iOS「添加到主屏幕」只是快捷方式"],
        ],
      },
      {
        kind: "p",
        text: "数据与隐私：岗位、画像、申请记录保存在你的 Postgres 与本地文件目录。启用外部模型或搜索后，相关问题、画像、JD 或检索词会发送给所选服务商；邮箱连接也会访问邮箱服务商。备份请使用项目脚本，并妥善保管加密密钥。",
      },
      {
        kind: "tip",
        text: "路线图：更多 ATS（北森 / Moka）适配、PWA 离线壳、简历版本对比。欢迎在 GitHub 提 issue 说明你最需要哪一个。",
      },
    ],
  },
];

// Contextual illustrations use an isolated demo database, never real accounts.
const SCREENSHOTS: Record<string, [string, string, string]> = {
  pages: ["home", "首页与核心功能导航", "先选择当前要完成的任务；首页和概览分别承担功能入口与进度汇总。"],
  "profile-confirm": ["profile", "演示画像编辑页", "核对教育、技能与经历，再保存并确认画像。"],
  "jobs-filter": ["jobs", "演示岗位库与筛选", "演示岗位带有专门标签；真实岗位应以官方详情页为准。"],
  "jobs-maintain": ["job-maintenance", "岗位维护范围确认", "先核对范围、复核上限与发现深度，再启动任务；截图未执行更新。"],
  matches: ["matches", "演示岗位推荐", "同时阅读匹配依据与资格判断，分数不等于录取概率。"],
  "applications-board": ["applications", "演示投递看板", "看板表示申请阶段；进入申请详情登记明确的笔试或面试预约。"],
  "applications-calendar": ["calendar", "演示面试日程", "只有明确预约进入日历；修改阶段不会自动预约。"],
  "agent-multi-turn": ["agent", "Agent 预置演示对话", "这是预置对话，未调用模型，不代表真实招聘结果；用于说明历史与结果卡片的阅读方式。"],
};
for (const section of GUIDE_SECTIONS) {
  for (const target of [section, ...(section.subsections ?? [])]) {
    const shot = SCREENSHOTS[target.id];
    if (!shot) continue;
    const [name, alt, caption] = shot;
    (target.blocks ??= []).push({ kind: "image", src: `/guide/${name}.png`, alt,
      caption: `${caption} 图中人物、岗位与预约均为虚构演示数据。`, width: 1600, height: 1050 });
  }
}

const OPERATION_HELP: Record<string, GuideBlock[]> = {
  "profile-confirm": [
    { kind: "steps", items: [
      { title: "先校对再确认", body: "逐项检查毕业年份、学位、技能与到岗偏好，修正解析遗漏。不要把未实际掌握的技能加进画像。" },
      { title: "检查保存结果", body: "保存成功后再确认；失败时保留当前内容，先处理提示再重试。看到已确认状态后，再去推荐页检查结果。", href: "/matches" },
    ] },
    { kind: "tip", tone: "warn", text: "扫描版 PDF 可能缺少可提取文字。解析为空时，请换文字版 PDF / DOCX，或手动完善画像；解析成功也需要你核对。" },
  ],
  import: [
    { kind: "steps", items: [
      { title: "复制岗位详情链接", body: "灰色企业入口用于打开官方招聘站。进入某个具体岗位，再复制地址；不要复制公司首页或岗位列表页。" },
      { title: "检查预览再入库", body: "逐项核对职位名称、城市、职位描述与任职要求。若正文截断或要求为空，先到官网对照，不要直接确认。" },
      { title: "读不到时改用粘贴", body: "需要登录或无法解析时，可以粘贴你已经核实的 JD。它是仅本人可见的私有内容，不会伪装成官方核验结果。" },
    ] },
    { kind: "tip", text: "遇到解析不完整，报告问题时附上官方链接、缺失字段、操作步骤和版本。请勿附带招聘平台 Cookie、登录口令或个人申请信息。" },
  ],
  matches: [{ kind: "table", head: ["你看到的情况", "下一步"], rows: [
    ["提示画像未确认", "回到我的画像，先保存并确认，再刷新推荐。"],
    ["推荐为空", "检查岗位库是否有已核验岗位，并放宽城市、类型或方向条件。"],
    ["高分但资格不满足", "技能匹配与硬性资格是两项判断，先核对毕业届别、学历与到岗要求。"],
  ] }],
  "applications-calendar": [{ kind: "tip", text: "验收方法：先登记一条带明确时间的预约，回到日历查看；只把阶段改成面试，不应出现新日程。改期后再次检查原时段是否释放。邮件发送时间不等于预约时间。" }],
  "agent-run": [{ kind: "table", head: ["状态 / 现象", "你可以怎么做"], rows: [
    ["等待确认画像", "打开我的画像，保存并确认后回到原会话继续；未确认时不会跳过校验。"],
    ["长时间执行中", "先看阶段进度，可离开页面稍后回来；不要反复提交同一问题。"],
    ["已请求停止", "取消是协作式的，当前外部请求可能需要结束后才退出。"],
    ["失败或部分完成", "阅读错误提示与已有结果；确认模型配置、网络或来源限制后再重试。"],
  ] }],
};
for (const section of GUIDE_SECTIONS) {
  for (const target of [section, ...(section.subsections ?? [])]) {
    const help = OPERATION_HELP[target.id];
    if (!help) continue;
    const blocks = target.blocks ??= [];
    const imageAt = blocks.findIndex((block) => block.kind === "image");
    blocks.splice(imageAt < 0 ? blocks.length : imageAt, 0, ...help);
  }
}
