# 广东医 · 宿舍水电监测

Windows 桌面工具：选择宿舍、查询水电余量、Windows 通知、可选 SMTP 邮件，以及真实微信小程序登录响应同步。

当前版本：**v1.7.1**。本项目是个人工具，接口和数据以学校系统为准。

## 使用

从 [Releases](https://github.com/kz2006a/gdmu-dorm-monitor/releases) 下载完整 Windows 程序包，完整解压后运行 EXE，保留同级 `app`、`_internal`、`runtime`。

首次使用：**微信连接 → 选择宿舍 → 自动保存并查询 → 按需开始监测**。新 Token 验证后自动加载列表；重新打开后按 ID 恢复上次宿舍。

- 不需要邮箱即可使用 Windows 通知；邮件为可选通道。
- 自动查询和网络重试最低间隔 30 分钟。
- Token 过期先静默刷新；失败后仅尝试一次失败通知并暂停监测。
- 软件不生成虚拟微信 code；微信仍可能需要人工完成登录或进入查询页。
- 退出/休眠期间不能监测，不会自动设置 Windows 开机启动。

详见 [使用说明](docs/USER_GUIDE.md)、[构建说明](docs/BUILD.md)、[变更日志](CHANGELOG.md)。

## 从源码运行

已验证环境为 Windows、Python 3.12、Tkinter；依赖版本保留与已有打包环境一致。

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run.py
```

查询功能可直接运行；内置 HTTPS 同步另需放入官方 `mitmdump.exe`，见构建说明。协议自检仅使用虚构编号和合成余额：

```powershell
python app/gdmu_balance.py --self-test
python -m unittest discover -s tests -p "test_*.py" -v
```

## 配置与贡献

本地 `.env` 可能保存 Token、邮件授权码；`data/` 可能包含证书私钥，均已忽略。请勿将这些文件、抓包或真实登录响应提交到 Issues/PR。

本仓库不包含原始微信包、学校图片或个人运行数据。源码中的离线样例已经改为合成数据。历史版本归档的来源和局限见每版 Release；后整理的版本不会冒充当时的 Git 提交。

使用 MIT 许可发布本项目自有代码；第三方组件见 [Third-party notices](THIRD_PARTY_NOTICES.md)。
