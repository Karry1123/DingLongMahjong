# 3 步免费上线

项目结构：Vercel 的 Root Directory 选 `frontend`；Render 的 Root Directory 选 `backend`。先部署后端，再部署前端。免费方案适用于个人非商业项目，受平台额度限制。

## 1. 推送到 GitHub

在项目根目录运行以下 PowerShell 命令。先在 GitHub 创建空仓库，将 URL 换成自己的地址；推送前可用 `git status --short` 检查文件。

```powershell
git init -b main
git add --all
git diff --cached --check
git commit -m "Prepare Mahjong EV cloud deployment"
git remote add origin https://github.com/你的用户名/你的仓库名.git
git push -u origin main
```

之后可用一条命令完成检查、提交与推送：

```powershell
.\scripts\publish.ps1 -RepositoryUrl https://github.com/你的用户名/你的仓库名.git -CommitMessage "更新麻将项目"
```

## 2. Render 部署 FastAPI

在 [Render](https://dashboard.render.com/) 选择 **New → Web Service** 并关联 GitHub 仓库。选 **Free**，Root Directory 填 `backend`，Language 选 Python，Build Command 填 `pip install -r requirements.txt`，Start Command 填 `uvicorn app.main:app --host 0.0.0.0 --port $PORT`。Python 版本设 `3.11.11`；也可直接使用仓库根目录的 `render.yaml` 创建 Blueprint。健康检查路径为 `/health`。部署完成后打开 `https://你的服务.onrender.com/health`，应返回 `{"status":"ok"}`。

如使用自定义前端域名，在 Render 环境变量 `ALLOWED_ORIGINS` 中填写完整 Origin，多个域名以逗号分隔；`*.vercel.app` 和本地开发域名已默认允许。Render Free 闲置 15 分钟后会休眠，首次请求可能需要约一分钟唤醒。`/api/game/record` 写入的本地对局轨迹不会在服务休眠、重启或重新部署后保留；需要长期保存时应另接持久化存储。

## 3. Vercel 部署 Vue

### Render 免费后端 + Neon 持久牌谱

在 Neon 创建 Free PostgreSQL 项目，区域选择 Singapore，与当前 Render 服务接近。复制 production 分支的 PostgreSQL 连接地址（含 `sslmode=require`），在 Render → Environment 中设置 `DATABASE_URL`。连接地址包含密码，只存到 Render 的环境变量，不提交到仓库或前端。

不要设置 `GAME_RECORD_DB_PATH` 或 `PVP_RECORD_DB_PATH`，这两个变量会强制使用 SQLite，覆盖 PostgreSQL 配置。保存并重新部署后，新完成的 PvE/PvP 牌局自动建表并归档到 Neon。房间配置仍使用本地 SQLite，正在进行的房间仍属于进程内状态。

牌谱不再因超过 200/500 局而自动删除。PvE 列表默认返回最新 200 局，用 `/api/game/records?limit=200&offset=200` 读取下一页；按 game_id 读取完整牌谱不受分页限制。玩家设备的历史缓存仍只保留 10 局。

切换数据库前先导出现存线上牌谱；SQLite 历史不会自动迁入 PostgreSQL。免费数据库有容量与计算额度限制，定期导出到本机备份。Render 自家的免费 PostgreSQL 有到期限制，不用于长期牌谱保存。

在 [Vercel](https://vercel.com/new) 导入同一 GitHub 仓库。Root Directory 选 `frontend`，Framework Preset 选 Vite，Build Command 为 `npm run build`，Output Directory 为 `dist`。在 Production 和 Preview 环境添加 `VITE_API_BASE_URL=https://你的服务.onrender.com`（只填根地址，不加 `/api`），然后 Deploy。`frontend/vercel.json` 处理 SPA 页面刷新；浏览器请求会直接发送到 Render。访问 Vercel 域名，检查自动发牌和切牌推荐是否成功。

本地开发：后端在 `backend` 中运行 `uvicorn app.main:app --reload --port 8000`；前端在 `frontend` 中运行 `npm run dev`。Vite 自动将 `/api` 代理到本地后端。


## App 构建（Capacitor）

在 frontend 安装依赖后，将 `.env.mobile.example` 复制为 `.env.mobile`，配置真实的 HTTPS 绝对 `VITE_API_BASE_URL`（不带 /api，不允许 loopback），执行 `npm.cmd run build:mobile` 输出 dist-mobile。网页仍用 `npm.cmd run build` 输出 dist。

首次执行 `npx cap add android`、`npx cap add ios` 生成原生工程；随后 `npx cap sync android` 并用 `npm run cap:android` 打开 Android Studio。两端工程均存在时，`npm run cap:sync` 会先构建再同步两端。Android 不要求在本环境执行 Gradle 构建；iOS 仅生成工程，签名和构建必须在 macOS/Xcode 完成。App 发布通过各平台签名包完成，不会随网页部署自动更新。

本次受限网络下 npm install 返回 EACCES，需要手动 npm install；原生工程生成与同步尚未完成。依赖安装后先更新锁文件，再重新构建和生成工程。后端还需允许 WebView 来源的 CORS 和 WSS，详细环境要求、真机验收、注册码生成及导入运维见 [docs/mobile-app.md](docs/mobile-app.md)。
