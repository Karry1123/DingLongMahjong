# 顶龙麻将 App

App 与网页共用 Vue 3 账号登录、好友、邀请与对战页面，使用 hash 路由。应用标识 `com.dinglong.mahjong`，名称“顶龙麻将”。网页构建输出 `dist`，App 构建输出 `dist-mobile`；只有 App 入口载入原生插件。

## 环境要求

- Node.js 22+、npm，依赖采用 Capacitor 8 主版本。Vite 的 Node 要求也需满足。
- Android：Android Studio Otter 2025.2.1 或更新版本、其配套 JDK、Android SDK 36（最低设备 API 24）。先在 Android Studio 完成 SDK 安装及许可接受，再连接真机。
- iOS：可以准备源码与生成工程；运行模拟器、签名、构建、归档必须使用 macOS 和 Xcode 26+，最低 iOS 15。本任务不构建 iOS。
- 版本依据：[Capacitor 8 升级文档](https://capacitorjs.com/docs/updating/8-0)。KeepAwake 使用[社区插件](https://github.com/capacitor-community/keep-awake)，在 package.json 以 `@capacitor/keep-awake` npm 别名安装。

## 首次安装与构建

在 `frontend` 目录执行（PowerShell 可使用 `npm.cmd`、`npx.cmd`）：

```powershell
npm.cmd install
Copy-Item .env.mobile.example .env.mobile
# 编辑 .env.mobile，替换占位符为已部署的真实 HTTPS API 域名
npm.cmd run build:mobile
npx.cmd cap add android
npx.cmd cap add ios
npx.cmd cap sync android
npm.cmd run cap:android
```

`cap add` 每个平台仅执行一次；若 Windows 上 iOS 工具检查阻止生成，请在 macOS 重跑 `npx cap add ios`。已有两个工程后，每次更新页面或插件执行 `npm run cap:sync`（先构建，再同步两端）；仅调试 Android 时可用 `npm run build:mobile` 与 `npx cap sync android`。`cap:ios` 只打开 Xcode 工程，不进行构建。首次安装会更新 package-lock.json，安装成功后提交一致的锁文件。

当前仓库状态（2026-10-17）：Capacitor 8 依赖已安装并写入 package-lock.json，`build:mobile` 已通过，`android/` 与 `ios/` 工程已生成并完成 `cap sync android`。尚未验证的是 Gradle 构建与真机行为：开发机没有安装 Android SDK，`gradlew assembleDebug` 未执行；iOS 需在 macOS 上构建。`.env.mobile` 目前为占位域名，部署前必须改为真实 HTTPS API 域名后重新 `npm run cap:sync`。

`VITE_API_BASE_URL` 必须是绝对 HTTPS 地址，例如 `https://your-service.onrender.com`，不含 `/api` 后缀；客户端自行拼接 `/api`。构建会拒绝空值、相对地址、HTTP、localhost 和 loopback。不要把设备自身的 127.0.0.1 当作开发电脑。后端同时需要正确配置 WebView 来源的 CORS（Android 默认 `https://localhost`，iOS 默认 `capacitor://localhost`）及 HTTPS/WSS。不得把密码、注册码、签名密钥放入 VITE 环境变量。Android 禁止 cleartext 与 mixed content；没有启用远程 server.url。

## 真机调试与验收

Android 开启开发者选项和 USB 调试，连接并授权设备。在 Android Studio 选择设备，运行 `android` 工程；也可先用 `adb devices` 检查连接，通过桌面 Chrome 的 `chrome://inspect/#devices` 检查 WebView 网络、控制台与 WSS。API 测试环境也应使用 HTTPS 域名。

逐项检查：注册、登录、重启仍能恢复账号；好友请求与邀请即时更新；等待室开局；牌桌方向锁及系统拒绝锁定后的 CSS 回退；退桌解锁和释放常亮；切后台后重新回前台，重新请求 /me 与 active match，WS 重新鉴权并拉取快照；返回键先关弹层，再回上页，对局离开确认后调用退出接口，顶层退出；底部 Tab、刘海和手势区域不遮挡内容。断网与登录过期应显示共享页面错误，不保留过期 WS。

iOS 在 macOS 安装依赖、构建、同步后用 `npm run cap:ios` 打开工程，设置 Development Team、Bundle ID、签名和设备。Preferences 插件涉及的隐私清单按[官方说明](https://capacitorjs.com/docs/apis/preferences)配置 UserDefaults 原因 `CA92.1`，再进行发布前审查；Windows 无法验证签名或构建。

## 原生适配说明

`src/platform` 统一提供 secureSession、orientation、lifecycle、backButton、haptics、keepAwake 和 statusBar。网页 token 仍用 localStorage 的 `dl.auth.token`；App 用 Preferences 同名键，启动时先异步恢复到内存，再加载路由。Preferences 是平台偏好存储，不是 Keychain/Keystore 加密保险库。写 token 成功后才进入共享登录后页面。退出立即清除内存 token 并删除持久值。

牌桌挂载申请方向锁和常亮，卸载释放；重叠牌桌使用引用计数。方向锁失败不阻断进入，现有 useOrientation 的 CSS 旋转继续工作。状态栏采用 DARK（暗背景浅色文字）及 #06221D；新 Android 的 edge-to-edge 可能忽略背景设置，需在真机检查安全区。底部 Tab 已使用 `env(safe-area-inset-bottom)`。硬件返回键通过弹层登记和已有路由离桌守卫处理。

## 注册码运维

遵循 [账号好友 API 契约](friends-auth-api.md)，App 不包含生成注册码的能力。站长在可信环境运行：

```text
python backend/scripts/registration_codes.py generate --count 20 --batch 2026-10 --expires-in-days 30 --out <私有目录>/codes-2026-10.txt --manifest <私有目录>/codes-2026-10.json
python backend/scripts/registration_codes.py import --manifest <私有目录>/codes-2026-10.json --dry-run
python backend/scripts/registration_codes.py import --manifest <私有目录>/codes-2026-10.json
python backend/scripts/registration_codes.py list --batch 2026-10
python backend/scripts/registration_codes.py revoke --batch 2026-10
```

导入在能访问服务端数据库的运维环境执行，提前核对 `DATABASE_URL` / `AUTH_DB_PATH`。明文 txt 私下分发，摘要 manifest 用于导入，均不放入 App 资源或公开仓库。重复导入不会重置已用或已撤销码；此处只记录操作说明，本次没有操作服务端数据库。

## 检查命令

```powershell
node --test tests/*.test.js
npm.cmd run build
npm.cmd run build:mobile
npx.cmd cap sync android
```

新增平台测试使用 web 与注入的 mock native 插件，覆盖会话持久化、监听清理、横屏失败、常亮引用计数、返回键和 WS 前后台恢复。设备方向、震动、状态栏、系统返回行为、APK 签名和原生构建需真机/原生工具链验证。
