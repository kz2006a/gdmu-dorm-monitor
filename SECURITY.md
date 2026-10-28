# 安全政策

## 支持范围

安全问题优先在最新稳定版调查和修复。历史 Release 用于归档，不承诺对旧版本单独回补；请先核对[最新版本](https://github.com/kz2006a/gdmu-dorm-monitor/releases/latest)。

## 报告漏洞

请使用 GitHub 的[私密漏洞报告](https://github.com/kz2006a/gdmu-dorm-monitor/security/advisories/new)，说明受影响版本、复现条件、潜在影响和最小复现步骤。优先提供虚构数据或已脱敏样例。

不要在公开 Issue、PR 或评论中披露尚未修复的漏洞细节，也不要提交真实 Token、SMTP 授权码、`.env`、证书私钥、抓包或原始登录响应。若这些内容已意外公开，应先使相关凭证失效或更换，再处理公开副本。

普通连接错误、使用问题及功能建议通过 [Issues](https://github.com/kz2006a/gdmu-dorm-monitor/issues) 反馈。

## 本地数据与连接

- 勾选保存凭证后，程序同级 `.env` 会保存明文 Token 和邮件授权码，请仅在自己的可信设备使用并限制文件访问。
- `data/` 可能保存本地同步证书私钥，`token-sync/` 用于临时登录响应，不要分享这些目录。
- HTTPS 同步依赖真实微信登录和本地代理接入。证书信任、代理连接应通过程序界面明确操作，结束使用时可恢复网络设置。
- 小程序 AppID 是客户端公开标识，不能替代 AppSecret 或登录凭证；报告凭证泄露时应区分标识与认证秘密。

第三方组件的许可和固定来源见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 与 [third_party/mitmproxy.json](third_party/mitmproxy.json)。
