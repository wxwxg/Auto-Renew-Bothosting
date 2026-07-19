🚀 Bot‑hosting 多账号自动续期
https://img.shields.io/badge/GitHub%2520Actions-%E8%87%AA%E5%8A%A8%E7%BB%AD%E6%9C%9F-blue?logo=githubactions
https://img.shields.io/badge/Python-3.10%252B-green?logo=python

通过 GitHub Actions 定时为 bot‑hosting.net 的多个账号自动续期免费计划（每 4 天续期一次），并自动更新过期的 SESSION_TOKEN，全程无人值守。
支持任意代理协议（含 VLESS / VMESS / Trojan / SOCKS5），一键部署，Telegram 实时通知。

📖 目录
功能特点

准备工作

配置说明

GitHub Secrets

多账号 JSON 格式

GitHub Actions 工作流

本地运行

截图调试

常见问题

许可证

✨ 功能特点
✅ 多账号支持 – 使用单个 JSON 数组管理任意数量的 bot‑hosting 账号。

✅ 双登录机制 – 优先使用 SESSION_TOKEN，失效后自动切换至 Discord OAuth（基于 DISCORD_TOKEN）。

✅ 自动续期 – 检测并点击“Renew”按钮，通过 Turnstile 验证，续期 4 天。

✅ 智能 Token 更新 – 续期成功后自动提取新的 SESSION_TOKEN 并更新到 GitHub Secrets（需 GH_TOKEN 权限）。

✅ 代理自由 – 支持 VLESS / VMESS / Trojan / SOCKS5 / HTTP(S) 等任意代理协议（内置 sing‑box 转换）。

✅ 通知推送 – 支持 Telegram 实时通知每个账号的执行结果，包含到期日期。

✅ 完全无头运行 – 适配 GitHub Actions 无图形化环境，也可本地调试。

✅ 截图调试 – 每次运行自动生成关键步骤截图，可下载排查问题。

🛠 准备工作
Fork 或 Clone 本仓库，并将以下文件放入仓库：

renew.py – 续期主脚本

.github/workflows/renew.yml – GitHub Actions 工作流

准备各账号的登录凭据（至少提供 session_token 或 discord_token 之一）：

从浏览器 Cookie 获取 session_token。

或从 Discord 开发者工具获取 discord_token。

（可选） 准备一个具有 写权限 的 GitHub Personal Access Token（GH_TOKEN），用于自动更新 Secrets。

（可选） 准备 Telegram Bot Token 和 Chat ID，用于接收通知。

⚙️ 配置说明
🔐 GitHub Secrets
在仓库 Settings → Secrets and variables → Actions 中设置以下 Secrets：

Secret 名称	是否必须	说明
ACCOUNTS_JSON	✅ 必须	多账号 JSON 数组（格式见下文）。
NODE_LINK	❌ 可选	任意代理链接（如 vless://...、socks5://...、vmess://...），用于网络加速或绕过限制。
GH_TOKEN	⭐ 强烈推荐	GitHub PAT，需要 repo 或 workflow 权限，用于自动更新 SESSION_TOKEN。
TG_BOT_TOKEN	❌ 可选	Telegram Bot Token，用于通知。
TG_CHAT_ID	❌ 可选	接收通知的 Telegram 用户/群组 ID。
注意：若未设置 ACCOUNTS_JSON，脚本会回退到传统单账号变量（EMAIL、SESSION_TOKEN、DISCORD_TOKEN），但推荐统一使用 JSON 格式。

📦 多账号 JSON 格式
ACCOUNTS_JSON 是一个 JSON 数组，每个元素代表一个账号：

json
[
  {
    "email": "user1@example.com",
    "session_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "secret_name": "SESSION_TOKEN"
  },
  {
    "email": "user2@gmail.com",
    "discord_token": "MTIzNDU2Nzg5MDEyMzQ1Njc4OQ.G...",
    "secret_name": "SESSION_TOKEN_2"
  },
  {
    "email": "user3@outlook.com",
    "session_token": "abc...",
    "discord_token": "def...",
    "secret_name": "MY_CUSTOM_TOKEN"
  }
]
字段说明：

字段	必填	描述
email	✅	仅用于通知和日志显示，可任意填写。
session_token	⚠️ 至少其一	bot‑hosting 的登录 Cookie（优先使用）。
discord_token	⚠️ 至少其一	Discord 用户 Token，作为备用登录方式。
secret_name	可选	该账号的 SESSION_TOKEN 更新到哪个 GitHub Secret。若不指定，索引 0 使用 SESSION_TOKEN，索引 ≥1 使用 SESSION_TOKEN_索引。
🧰 其他环境变量（工作流或本地）
脚本也读取以下环境变量（可在工作流 env 或本地 .env 中设置）：

变量名	默认值	说明
IS_PROXY	false	是否启用代理（通常由 NODE_LINK 自动控制）。
PROXY_SERVER	http://127.0.0.1:1080	代理服务器地址（仅在 IS_PROXY=true 时生效）。
HEADLESS	false	是否无头模式（建议 false 以便有头调试）。
GH_TOKEN	-	GitHub PAT（也可通过 Secret 传递）。
TG_BOT_TOKEN	-	Telegram Bot Token。
TG_CHAT_ID	-	Telegram 接收者 ID。
⚡ GitHub Actions 工作流
工作流文件 .github/workflows/renew.yml 已内置：

定时触发：每天 UTC 1:00（北京时间 9:00）自动运行。

手动触发：支持 workflow_dispatch 随时运行。

工作流会自动：

设置 Python 环境，安装 SeleniumBase 等依赖。

若有 NODE_LINK，自动下载 sing‑box 并转换任意代理协议为本地 SOCKS5。

运行 renew.py 处理所有账号。

上传关键步骤的截图（*.png）作为 Artifact，方便调试。

清理进程和临时文件。

🖥 本地运行
克隆仓库后，在本地终端执行：

bash
# 安装依赖
pip install seleniumbase requests

# 设置环境变量（示例）
export ACCOUNTS_JSON='[{"email":"test@example.com","session_token":"xxx"}]'
export NODE_LINK="socks5://127.0.0.1:1080"   # 若需要代理
export HEADLESS=false                        # 有头模式调试

# 运行脚本
python renew.py
本地运行时需要安装 Chrome 浏览器及对应的 WebDriver（seleniumbase 会自动处理）。

📷 截图调试
脚本会在关键步骤自动截图（如点击续期按钮、Turnstile 验证、续期成功等），文件命名格式为 描述_邮箱_时间戳.png。

在 GitHub Actions 运行完成后，您可以在 Artifacts 区域下载 screenshots.zip，解压即可查看所有截图，精确定位问题。

https://docs.github.com/assets/cb-23094/images/help/actions/artifact-overview.png

❓ 常见问题
Q：为什么续期总是失败？
A：最常见的原因是 Turnstile 验证未成功。可以查看截图，确认“Renew for 4 days”按钮是否出现。若代理不稳定，可更换 NODE_LINK。

Q：如何获取 session_token？
A：登录 bot‑hosting.net，按 F12 → Application → Cookies → 复制 session_token 的值。

Q：如何获取 discord_token？
A：打开 Discord 网页版，按 F12 → Network → 任意请求头中找 authorization 字段。

Q：NODE_LINK 支持哪些协议？
A：任何 sing‑box 支持的协议，包括 VLESS、VMESS、Trojan、Shadowsocks、SOCKS5、HTTP(S) 等。脚本会自动解析并转换为本地代理。

Q：自动更新 Secret 需要什么权限？
A：GH_TOKEN 至少需要 repo 或 workflow 写入权限。推荐创建一个专用的 Fine‑grained PAT，仅授予当前仓库的 Secrets 读写权限。

Q：多个账号的 Secret 名称是什么？
A：若未指定 secret_name，索引 0 使用 SESSION_TOKEN，索引 1 使用 SESSION_TOKEN_1，依此类推。您可以在 Secrets 中提前创建这些变量。

📄 许可证
本项目基于 MIT License 开源，仅供学习交流使用。使用前请确保遵守 bot‑hosting.net 的服务条款。

Happy Renewing! 🎉

