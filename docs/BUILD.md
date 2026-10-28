# Windows 构建

已验证的原有环境：Python 3.12.7、cryptography 43.0.0、PyInstaller 6.22.3。这是复现已有打包环境的记录。

```powershell
python -m pip install -r requirements-build.txt
python build.py --mitmdump "PATH_TO_OFFICIAL_MITMDUMP_EXE"
```

将构建 `dist/gdmu-dorm-monitor/`。引擎使用官方 mitmproxy 12.3.0，下载来源及固定 SHA-256 见 `third_party/mitmproxy.json`；构建脚本会核对引擎 SHA-256。它不会从网络自动下载、安装证书或改变系统代理。

只构建查询界面可明确使用 `python build.py --query-only`，该产物不具备内置同步引擎，不能当作完整 Release 上传。

仓库中的源码与公开发布用压缩包均排除个人配置/运行数据。项目 MIT 文件不替代运行库、引擎等第三方许可证。
