# 广东医宿舍水电查询 · v0.1.0

命令行只读查询工具：输入自己的登录 Token 和宿舍内部编号，查询剩余电量、水量。

## 安装和使用

需要 Python 及 cryptography：

```powershell
python -m pip install -r requirements.txt
python app/gdmu_balance.py --self-test
python app/gdmu_balance.py --building-id YOUR_BUILDING_ID --room-id YOUR_ROOM_ID
```

程序提示输入 Token，默认不回显，也不把它写入文件。内部编号不是楼号或门牌号，请使用自己有权查询的宿舍编号。

`--self-test` 只做离线编解码校验，使用虚构目标 1/1 与示例 100 度电、10 吨水，不访问学校。

## 本版范围

- 命令行查询、指定楼栋/房间内部 ID、离线协议校验和错误提示。
- 不包含图形界面、定时监测、邮件、桌面通知或微信自动登录。
- 实时查询需要有效 Token，结果以上游系统为准。

## 来源说明

最早的独立命令行历史快照未单独保存。本版采用后来保留的兼容命令行入口归档，其中保留了供后续窗口版使用的列表辅助函数；它不是原始历史 Git 提交。

公开整理仅将离线样例改为合成编号/余额，不发布原始抓包、个人配置、凭证或私钥。

## 许可与发布

项目自有代码使用 MIT。cryptography 是外部运行依赖，保留其自身许可，未在源码包中捆绑第三方库。
