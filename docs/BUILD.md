# Windows 构建

已验证的原有打包环境为 Python 3.12.7、cryptography 43.0.0、PyInstaller 6.22.3。依赖文件保留与已有分发环境一致的版本。

## 准备环境

在 Windows 安装含 Tkinter 的 Python 3.12，在仓库根目录执行：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
```

## 完整程序包

从 [third_party/mitmproxy.json](../third_party/mitmproxy.json) 指定的官方来源获取 mitmproxy 12.3.0 Windows x86_64 包，解压得到 `mitmdump.exe`。示例将它放在 `tools/mitmdump.exe`：

```powershell
Get-FileHash .\tools\mitmdump.exe -Algorithm SHA256
.venv\Scripts\python.exe build.py --mitmdump .\tools\mitmdump.exe
```

`build.py` 会校验引擎文件是否匹配固定 SHA-256，并生成 `dist/gdmu-dorm-monitor/`。完整保留该目录中的 EXE、`app/`、`_internal/` 和 `runtime/`。构建过程不会下载引擎、安装证书或修改系统代理。

从源码运行内置同步时，将同一官方引擎放在仓库根目录的 `runtime/https/mitmdump.exe`，再运行 `run.py`。

## 查询界面构建

```powershell
.venv\Scripts\python.exe build.py --query-only
```

此产物没有 HTTPS 引擎，不具备内置微信同步，不能作为完整同步版程序包使用。

## 验证与分发

构建前按[贡献指南](../CONTRIBUTING.md)运行离线协议自检和回归测试。CI 在 Windows / Python 3.12 上自动执行同类检查，不需要学校或邮件凭证。

分发前在独立目录检查启动、所需运行库和相对路径。压缩包应包含许可证、第三方声明及使用说明，并排除 `.env`、`data/`、`token-sync/`、抓包和证书私钥。历史来源见[源码来源](SOURCE_PROVENANCE.md)。
