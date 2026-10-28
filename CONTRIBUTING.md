# 贡献指南

欢迎提交问题反馈、功能建议、文档修正和代码改进。参与前请阅读[行为准则](CODE_OF_CONDUCT.md)；安全漏洞按[安全政策](SECURITY.md)私密报告。

## 开发环境

使用 Windows、Python 3.12（含 Tkinter）及 Git：

```powershell
git clone https://github.com/kz2006a/gdmu-dorm-monitor.git
cd gdmu-dorm-monitor
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run.py
```

完整微信同步需要另行准备官方 HTTPS 引擎，见[构建说明](docs/BUILD.md)。离线测试不需要引擎、学校账号或 SMTP 凭证。

## 修改与验证

从 `main` 建立描述用途的分支，保持一次改动集中解决一个问题。目录分工见[架构说明](docs/ARCHITECTURE.md)。遵循 `.editorconfig` 和相邻代码风格，避免混入无关的批量格式调整。

```powershell
.venv\Scripts\python.exe app/gdmu_balance.py --self-test
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

测试使用虚构宿舍、模拟学校接口和邮件服务。增加业务行为时，覆盖相关成功、失败和停止路径。界面改动检查小窗口布局及缩放；配置改动检查旧配置兼容性。PR 会在 Windows CI 中执行检查。

修改使用方式时同步更新文档，并在 `CHANGELOG.md` 的“未发布”部分记录用户可见的变化。版本历史与来源说明见[源码来源](docs/SOURCE_PROVENANCE.md)。

## 提交 Pull Request

先确认现有 Issue/PR 是否已有相同工作，再提交分支并使用 PR 模板说明问题、行为、实际验证和兼容性。提交标题用简短动词说明改动，例如 `docs: 完善首次连接说明` 或 `fix: 处理宿舍列表为空的情况`。

请勿提交 `.env`、个人配置、Token、SMTP 授权码、证书私钥、抓包、原始登录响应和运行记录。截图及复现样例使用虚构信息。新增依赖时说明用途、许可和 Windows 打包影响。

项目自有代码采用 [MIT 许可证](LICENSE)；贡献者须有权提交相应内容，第三方代码和资源应保留许可和来源。
