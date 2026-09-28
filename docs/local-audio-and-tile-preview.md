# 本地语音与图形牌面

运行后端：在 `backend` 执行 `.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000`。
运行前端：在 `frontend` 执行 `npm run dev -- --host 0.0.0.0 --port 5178`。

- 游戏：<http://127.0.0.1:5178/>
- 全部条筒牌面及字牌试听：<http://127.0.0.1:5178/?preview=tiles>
- 本地截图：`frontend/tests/artifacts/meld-grid/`。

## 语音

创建引擎、页面挂载、用户手势解锁和微信就绪事件都不发起语音请求。
只有实际 `playAction` 才请求对应的 `/audio/data/*.dat`。请求使用
`Accept: application/octet-stream`，开发/预览服务器与 Vercel 配置返回
`Content-Type: application/octet-stream` 和 `X-Content-Type-Options: nosniff`。

本机下载器曾把 `.wav`、`.bin` 请求截成 HTTP 204，因此不能仅依靠 Accept 请求头。
`prepare-voice-data.mjs` 在 npm dev/build 前将每个录音打包为 MJVOICE1 数据：8 字节版本头，
后接逐字节 XOR 0xa5 的录音内容。这只是可逆的传输格式，不是加密或权限保护。
浏览器 fetch ArrayBuffer 后只在内存还原、decodeAudioData，按牌码缓存 AudioBuffer；
并发加载共享同一个 Promise。不会创建 audio 元素、媒体 URL 或 Blob URL。
失败时走现有语音合成兼容逻辑，不自动重试；下一次真实动作可以重试。
卸载后，未完成的请求不能再播放或写回缓存。

生成的 dat 文件不纳入版本控制；源 WAV 保留，npm dev/build 自动重新生成。
开发构建也可用 `npm run build -- --mode development`。
任何网页实现都不能约束第三方下载器未来的任意拦截规则。

标准 API 参考：[MDN decodeAudioData](https://developer.mozilla.org/en-US/docs/Web/API/BaseAudioContext/decodeAudioData)。

## 牌面与验证

`TileArtwork.vue` 是正式牌面与预览共享的 18 种 SVG 图案，`MahjongTile.vue` 统一提供牌体、横置、标记和无障碍名称。
万子保留数字与万字之间的比例字距。辅助选牌、响应操作、上帝视角及结算小牌也使用共享图形。

- `node --test tests/*.test.js`：含零预加载、并发去重、缓存回放、静音、失败重试、卸载竞态、38 个资源逐字节还原及图形牌面验证。
- `node scripts/pve-meld-grid-smoke.mjs`：固定牌局布局、结算 SVG、真实浏览器 fetch/解码、可信点击播放及缓存检查。
- `pve-stage-smoke.mjs` 完整对局检查本次在自摸提示步骤超时；此前的两次出牌与横竖屏部分完成。未修改该脚本或游戏规则。

所有修改仅在本地，未提交或推送。
