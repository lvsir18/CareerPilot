# 安全策略

CareerPilot 会把简历、邮箱凭据、模型 API Key 存在**部署者自己的机器**上，因此安全问题的影响面比 SaaS 更大。
如果你发现漏洞，请先私下告知，不要开公开 issue。

## 报告方式

- 通过 GitHub 的 **Security → Report a vulnerability**（Private vulnerability reporting）提交；
- 或在 issue 里只写「有安全问题，请提供私下渠道」，不描述细节。

请在报告里说明：影响版本、复现步骤、影响范围（是否能读取他人数据、是否能越权写库）、你建议的修复方向。
我们会在 **72 小时内**确认收到，并在修复发布后于 CHANGELOG / Release Notes 中致谢（如果你愿意署名）。

## 支持范围

只维护默认分支（`main`）的最新版本。自建部署如果改过代码，需要你自己确认问题是否仍然存在。

## 部署前必须了解的限制

这些行为影响部署的信任边界；不应因为属于既有设计就忽略其风险：

| 行为 | 说明 |
|---|---|
| 服务端默认模型 / 搜索 Key 只给管理员用 | 避免部署者的额度被其他账号消耗；可通过 `SHARED_*_ADMINS_ONLY=false` 显式放开 |
| `ALLOW_LAN_ORIGINS=true` 会放行私有网段来源 | 仅限 IP 字面量（192.168 / 10 / 172.16 / Tailscale 100.64），公网域名仍需显式配置 |
| 关闭 `PASSWORD_RESET_ENABLED` 才能安全暴露公网 | 开启时知道邮箱即可重置密码，这是个人版的便利取舍 |
| 抓取官网详情页时使用无头浏览器 | 只访问公开页面，不登录、不绕验证码；包含 URL 与公网地址校验，部署时仍应限制容器对内网资源的访问 |
| 明文 Key 不会回显 | 接口只返回掩码，日志不记录；但拥有数据库与 `MAILBOX_SECRET_KEY` 的人可以解密 |

## 加固建议（部署到公网时）

1. 改掉 `SESSION_SECRET`、`POSTGRES_PASSWORD`、`MAILBOX_SECRET_KEY` 为随机值；
2. 关闭 `PASSWORD_RESET_ENABLED`；
3. 前置 HTTPS 反向代理，`COOKIE_SECURE` 保持开启；
4. 只暴露 3000（web），不要把 8000（api）与 5432（postgres）直接暴露；
5. 定期备份数据库卷与 `FILE_STORAGE_DIR`，备份文件本身也要加访问控制。

## 外部服务与公开材料

模型、搜索和邮箱服务不是本地存储的一部分：启用后，相关内容会传给所配置的服务商。公开截图、日志或 issue 前，请清除真实简历、招聘邮件、账号、Cookie、Token、授权码和服务商 Key。

GitHub 私密漏洞报告入口需要仓库管理员在 Settings → Security 中启用；首发时请确认入口可用。此仓库不应提交真实数据库、上传目录或运行备份，历史提交也需要检查。
