# 局域网与手机热点预览

后端在 `backend` 执行：

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

前端在 `frontend` 执行：

```powershell
npm.cmd run dev -- --host 0.0.0.0 --port 5173
```

电脑访问 `http://localhost:5173/`，同一网络的手机访问 `http://电脑IPv4地址:5173/`（地址可用 `ipconfig` 查看，热点重连后可能改变）。

开发环境 `VITE_API_BASE_URL` 留空或填 `/`。HTTP `/api` 和 WebSocket `/api/rooms/{id}/ws` 均使用浏览器当前来源，由 Vite 的 `/api` 代理转发；配置中的回环代理目标只在电脑服务器执行，不会发到手机自身。不要额外改成 `/ws`，房间握手的实际路径在 `/api/rooms` 下。

若显式配置了回环后端地址，前端会根据当前浏览器 hostname 替换回环主机，HTTP/HTTPS 与 WS/WSS 同步处理。部署使用的外部 `VITE_API_BASE_URL` 保持显式配置。

HTTP CORS 和 WebSocket 共用来源策略，支持 localhost、回环地址、10/8、172.16/12、192.168/16 及局域网 IPv6 来源，也保留已有部署白名单。Windows 防火墙需允许当前网络上的前端端口；直连后端时还需允许 8000。通过 Vite 代理时手机只需连接前端端口。

普通打包仍使用生产 API；本地打包预览应临时设置 `VITE_API_BASE_URL=/` 后构建，再执行 `npm.cmd run preview -- --host 0.0.0.0`。

双浏览器回归：在 frontend 设置 `PVP_LAN_ORIGIN=http://电脑IPv4地址:5173/`，执行 `node scripts/pvp-lan-smoke.mjs`。它分别从 localhost 和局域网来源创建房间，再互相加入，并检查房间请求及握手地址。
