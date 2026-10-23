# 顶龙麻将 · 协作规则

## UI / 样式（必须遵守）

本项目有一套设计系统，规范在 `docs/design-system.md`，令牌在 `frontend/src/styles/tokens.css`，基础组件类在 `frontend/src/styles/components.css`，纹样在 `frontend/src/styles/patterns.css`。任何涉及前端样式的改动，先读规范再动手。

硬规则：

1. 颜色只用 `rgb(var(--token))` 或 `tailwind.config.js` 映射的色名（`ink / felt / gilt / highlight / ivory / jade / cinnabar / indigo / bamboo / fog`，以及 `accent / line / ok / warn / danger / info / paper` 等语义名）。禁止十六进制、`rgb()` 字面量和 Tailwind 自带色名（amber / emerald / rose / sky / slate …）。提交前跑 `cd frontend && npm run lint:colors`，不得新增 `lint-colors.allow.json` 条目。
2. 亮金 `--highlight` 只能出现在牌桌舞台内的焦点元素（财神、推荐出牌、轮到你）；品牌与按钮用哑金 `--accent / gilt-*`。
3. 牌面艺术色 `--tile-*` 与 UI 状态色 `--ok / --danger / --info` 互不引用。
4. 字体只用 `--font-display`（宋体标题、牌字）、`--font-body`、`--font-num`。
5. 新界面先用 `.ui-btn / .ui-card / .ui-modal / .ui-pill / .ui-wind / .ui-clock / .ui-toast` 组装；缺的组件先补进 `components.css` 或 `frontend/src/components/ui/`。
6. 纹样只用 `.ui-huiwen / .ui-yunwen / .ui-guijia / .ui-corner / .ui-seal / .ui-ruyi`，按 `docs/design-system.md` 第 4 节的位置表放置；牌桌中央、计时器、危险提示、表格、可见牌面不加纹样。
7. 一屏一个 primary 按钮；`--danger` 只用于不可逆操作；最小点击区 44px；`focus-visible` 用 accent 描边。
8. 1280×720 舞台内不新增包装节点，不给祖先加 `transform`，不取整现有 px 几何；改牌桌样式必须跑 `frontend/scripts/pve-stage-smoke.mjs`、`pve-worst-case.mjs`、`pve-landscape.mjs` 并附前后截图。
9. 原生侧同步值：`frontend/index.html` theme-color、`frontend/capacitor.config.ts`、`frontend/src/platform/native.js` 的背景色必须等于 `--ink-900`（#06221D）。
10. 设计系统预览页：`http://localhost:5173/?preview=design`；改了令牌或组件类要在这里过一遍。

## 其它

- 规则与配例：`rule.md`；架构：`docs/architecture.md`；发布流程：`DEPLOY.md`。
- 后端测试：`cd backend && python -m pytest`；前端构建：`cd frontend && npm run build`（需要 `VITE_API_BASE_URL`）。
