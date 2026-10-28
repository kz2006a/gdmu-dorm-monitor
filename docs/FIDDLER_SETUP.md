# Fiddler 登录响应同步接入

这项功能接收 `code2Session` 响应中的新 Token，不读取该请求头中可能残留的旧 Token。新 Token 先在当前宿舍余量接口验证，成功后才替换和保存。

## 一次性设置

1. 完整解压 v1.3.0 程序包并启动 EXE，保留 `app` 和 `_internal` 文件夹。
2. 配好自己的宿舍、SMTP 参数和提醒规则。升级用户可以先关闭新旧程序，将自己 v1.2.0 程序目录中的 `.env` 复制到新程序目录，再打开新程序。
3. 在主窗口点击 **生成同步脚本**。软件会启用 Token 同步，并打开当前程序目录下的 `Fiddler_同步片段.txt`。
4. 打开 **Fiddler Classic → Rules → Customize Rules**。
5. 找到原有的 `OnBeforeResponse` 函数，把生成的片段粘贴到这个函数的大括号内，保留其他原有代码。例如：

```javascript
static function OnBeforeResponse(oSession: Session) {
    // 在这里粘贴软件生成的完整片段。
    // 原有规则继续保留。
}
```

6. 保存规则，确认 Fiddler 没有脚本编译错误，HTTPS 解密和 Capture Traffic 已开启。
7. 在微信小程序正常触发一次重新登录，例如旧 Token 失效后再查询。此时需要出现新的 `code2Session` 请求。
8. 软件应依次显示收到登录响应、验证候选 Token、接入新 Token。若此前是因过期暂停的监测，会自动继续；手动停止的提醒会保持停止。

脚本必须放在 **OnBeforeResponse** 内，才能读取服务器响应。[Fiddler 官方事件说明](https://www.telerik.com/fiddler/fiddler-classic/documentation/knowledge-base/fiddlerscript/modifyrequestorresponse)

## 工作方式

```text
小程序正常重新登录
→ 学校 code2Session 返回新 Token
→ Fiddler 将该响应临时写入当前程序的 token-sync 目录
→ 软件解码 info 并提取 Token
→ 余量接口验证通过
→ 更新内存及可选的 .env 保存值
→ 根据原来的监测意图恢复提醒
```

片段仅导出以下请求的 HTTP 200 响应：

```text
POST https://pay.gdmu.edu.cn/pmccl/api/code2Session
```

软件还会检查 `ret_code=00`、Token 字段与格式，拒绝过旧的响应和已识别的账号不匹配凭证。JWT 时间信息仅用作防止回退的辅助检查，实际有效性由学校查询接口确认。

不会因捕获其他站点、余量查询或请求头中的旧 Token 而替换凭证。Fiddler 自身的全局捕获范围仍由你的原有设置决定。

## 运行条件

- 保持本软件、微信及 Fiddler 运行，HTTPS 解密正常。
- 新 Token 仍由微信小程序登录产生。本功能不会替代 `wx.login`，也不会自行打开小程序或延长旧 Token 的有效期。
- 如果小程序没有产生新的登录请求，软件会等待；在小程序查询一次以触发正常重新登录即可，不用复制粘贴 Token。
- 关闭或禁用同步后，程序会撤销本地接收标记。异常退出后标记约 30 秒失效，Fiddler 片段不再导出后续响应。
- 本地响应文件读取后删除；只将通过查询验证的 Token 按“记住凭证”选项保存。记录里只显示指纹，不显示完整 Token。

## 移动目录与升级

Fiddler 片段包含当前程序的绝对目录。移动程序文件夹后，或改用另一份程序目录时，请重新生成片段，并替换原来添加的 GDMU 同步片段。

不要在多个目录对应的片段之间混用路径。EXE 保持目录式发布，配置和已验证 Token 仍保存在所用程序目录的 `.env`。

## 常见情况

| 表现 | 检查方法 |
|---|---|
| 一直等待响应 | 确认小程序确实重新调用了 code2Session，Fiddler 能解密，并且片段路径对应当前程序 |
| Fiddler 提示编译错误 | 确认片段位于 OnBeforeResponse 函数体内，未把整个函数放进另一个函数 |
| 收到响应但没有 Token | 小程序可能仍需完成学校登录；完成后再触发查询 |
| 候选验证失败 | 原 Token 不会被覆盖；检查网络、所选宿舍权限或重新在小程序登录 |
| Token 更新但提醒未启动 | 若此前手动停止或尚未配置 SMTP，请检查配置并点击开始提醒 |
| 过期后才启用同步 | 软件会保留本次因过期暂停的监测意图，收到有效 Token 后自动续上；手动停止会取消这一意图 |

