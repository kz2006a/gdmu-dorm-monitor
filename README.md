# 广东医 · 宿舍水电监测

[![Windows CI](https://github.com/kz2006a/gdmu-dorm-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/kz2006a/gdmu-dorm-monitor/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/kz2006a/gdmu-dorm-monitor)](https://github.com/kz2006a/gdmu-dorm-monitor/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

面向广东医科大学宿舍的 Windows 桌面工具：查询水电余量、持续监测、低阈值警告，以及真实微信小程序登录同步。

当前稳定版：**v1.7.1**。接口和读数以学校系统为准。

## 下载与首次使用

从 [最新 Release](https://github.com/kz2006a/gdmu-dorm-monitor/releases/latest) 下载适合的附件：

| 附件 | 用途 |
|---|---|
| `*-windows-x64.zip` | 新用户使用的完整 Windows 程序包，无需安装 Python |
| `*-update.zip` | 指定版本的覆盖升级包，适用范围见 Release 说明 |
| `*-source.zip` | 从源码运行或参与开发 |

1. 完整解压程序包，运行其中的 EXE，保留同级 `app`、`_internal` 和 `runtime` 文件夹。
2. 在 Windows 微信中打开“广东医缴费”，点击右上角 **“⋯” → “添加到电脑桌面”**，创建小程序快捷方式。
3. 进入软件“微信连接”，选择该快捷方式，勾选“登录过期时自动打开小程序”并保存连接设置，再点击“连接并获取登录”。
4. 按界面提示完成证书、代理接入和真实微信登录。获得有效 Token 后自动加载宿舍，选择房间后保存并查询。
5. 在“监测设置”配置通知与阈值，保存后到总览开始监测。默认 Windows 通知，无须配置邮箱。

快捷方式的创建、验证和自动续接设置详见[首次使用图文教程](docs/USER_GUIDE.md#首次使用)。

## 功能

- 按校区、楼栋和房间选择宿舍；重新打开后按内部 ID 恢复上次选择。
- Windows 余量通知、低阈值警告、固定时间提醒；SMTP 邮件为可选通道。
- 自动查询及网络失败重试的最低间隔为 30 分钟。
- Token 过期先静默恢复；最终失败才尝试一次失败通知并暂停监测。
- 可选保存凭证、打开软件后自动连接微信和自动开始监测。

自动恢复需要有效快捷方式、可用的同步连接和真实微信登录。微信仍可能需要手动完成学校登录或进入查询页。最小化可继续监测；退出或休眠期间不能监测。

## 从源码运行

支持 Windows、Python 3.12（含 Tkinter）：

```powershell
git clone https://github.com/kz2006a/gdmu-dorm-monitor.git
cd gdmu-dorm-monitor
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run.py
```

查询可直接运行。源码的内置 HTTPS 同步另需准备官方 `mitmdump.exe`，路径及摘要校验见[构建说明](docs/BUILD.md)。

```powershell
.venv\Scripts\python.exe app/gdmu_balance.py --self-test
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

测试使用虚构数据和模拟服务，不需要学校账号或 SMTP 凭证。

## 项目目录

```text
app/          查询、界面、配置、监测和微信同步
launcher/     Windows EXE 启动器
tests/        离线回归测试
docs/         使用、构建、架构及历史来源
third_party/  第三方许可和引擎来源
.github/      问题模板、PR 模板及 CI
run.py        源码入口
build.py      本地打包入口
```

## 文档与参与

- [使用说明与常见问题](docs/USER_GUIDE.md)
- [构建说明](docs/BUILD.md) · [目录与架构](docs/ARCHITECTURE.md)
- [变更记录](CHANGELOG.md) · [源码来源](docs/SOURCE_PROVENANCE.md)
- [贡献指南](CONTRIBUTING.md) · [行为准则](CODE_OF_CONDUCT.md) · [获取帮助](SUPPORT.md)
- [安全政策与私密报告](SECURITY.md)

本地 `.env` 可能保存明文 Token 和邮件授权码，`data/` 可能包含证书私钥。不要将个人配置、运行记录、抓包和原始登录响应提交到仓库或公开讨论。

## 许可

项目自有代码采用 [MIT 许可证](LICENSE)。第三方组件及文档截图中的软件界面、商标保留各自权利，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
