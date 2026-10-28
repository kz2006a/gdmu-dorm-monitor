# 目录与架构

项目是 Windows 桌面应用，Python 业务模块与 EXE 启动器分开。源码入口为 `run.py`，分发包由启动器加载同级 `app/`。

## 目录分工

| 路径 | 用途 |
|---|---|
| `app/` | 查询、界面、监测、登录同步与本地配置 |
| `launcher/` | Windows EXE 入口及打包所需运行库导入 |
| `tests/` | 使用模拟接口、虚构数据和临时目录的离线测试 |
| `docs/` | 使用、构建、恢复逻辑及历史来源说明 |
| `third_party/` | 第三方许可证和 HTTPS 引擎的固定来源、摘要 |
| `.github/` | Issue/PR 模板和 Windows CI |
| `build.py` | 本地构建入口 |

## 主要模块

| 模块 | 职责 |
|---|---|
| `gdmu_balance.py` | 只读学校接口、列表整理、协议编解码及离线样例 |
| `gdmu_desktop.py`、`gdmu_ui.py` | 主窗口、页面布局、宿舍选择与查询结果 |
| `gdmu_reminders.py`、`gdmu_mail_ui.py` | 提醒规则、运行状态、邮件及设置交互 |
| `gdmu_notifications.py` | 原生 Windows 通知 |
| `gdmu_config.py` | 程序同级 `.env` 的读写与配置兼容 |
| `gdmu_token_sync.py` | 真实登录响应中的候选 Token 接收和校验 |
| `gdmu_proxy.py`、`gdmu_proxy_addon.py`、`gdmu_proxy_ui.py` | 本地 HTTPS 引擎、限定响应接入和连接界面 |
| `gdmu_wechat_window.py` | 微信小程序窗口识别、唤起后的关闭协调 |
| `gdmu_selftest.py` | 已打包启动器的离线检查 |

## 数据流

有效登录 → 加载校区/楼栋/房间 → 选择或按 ID 恢复宿舍 → 查询余量 → 保存目标 → 按设置监测及通知。

网络请求在后台执行，结果交回 Tk 主线程更新界面。Token 过期后进入恢复状态，恢复成功继续原监测，最终失败只尝试一次失败通知并暂停。详见 [Token 恢复说明](TOKEN_RECOVERY.md)。

个人配置、登录响应、提醒去重记录及证书属于运行数据，不作为源码或分发包的一部分提交。测试应使用独立临时目录和模拟服务。
