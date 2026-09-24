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

在 [Vercel](https://vercel.com/new) 导入同一 GitHub 仓库。Root Directory 选 `frontend`，Framework Preset 选 Vite，Build Command 为 `npm run build`，Output Directory 为 `dist`。在 Production 和 Preview 环境添加 `VITE_API_BASE_URL=https://你的服务.onrender.com`（只填根地址，不加 `/api`），然后 Deploy。`frontend/vercel.json` 处理 SPA 页面刷新；浏览器请求会直接发送到 Render。访问 Vercel 域名，检查自动发牌和切牌推荐是否成功。

本地开发：后端在 `backend` 中运行 `uvicorn app.main:app --reload --port 8000`；前端在 `frontend` 中运行 `npm run dev`。Vite 自动将 `/api` 代理到本地后端。
