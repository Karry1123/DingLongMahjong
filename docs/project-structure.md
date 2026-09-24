mahjong-advisor/
├── backend/                  # Python 后端工程
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py           # FastAPI 入口，定义 CORS、路由挂载
│   │   ├── schemas.py        # Pydantic 结构定义 (输入手牌格式、输出推荐格式)
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── constants.py  # 牌型定义 (万条筒字)、胡头底分常量
│   │   │   ├── mapper.py     # 规则预处理：白板替身与得牌 JOKER 映射
│   │   │   ├── evaluator.py  # 和牌与向听数计算回溯核心
│   │   │   └── ev_engine.py  # 切牌推荐与台州胡头/硬胡加权计算
│   │   └── api/
│   │       ├── __init__.py
│   │       └── routes.py     # API 接口实现 (/api/recommend)
│   ├── requirements.txt      # 依赖库清单 (fastapi, uvicorn, pydantic)
│   └── run.py                # 快速本地启动脚本 (python run.py)
│
├── frontend/                 # Vue 3 前端工程
│   ├── src/
│   │   ├── assets/           # 麻将牌 SVG/PNG 图标或样式文件
│   │   ├── components/       # 界面组件
│   │   │   ├── TilePicker.vue   # 选牌键盘 (万/条/筒/字)
│   │   │   ├── HandBar.vue      # 当前已选 14 张手牌展示栏
│   │   │   ├── GameConfig.vue   # 选财神“得”、庄闲设置条
│   │   │   └── ResultCard.vue   # 最优切牌推荐与 EV 详情列表
│   │   ├── services/
│   │   │   └── api.js        # 封装与后端通信的 fetch/axios 请求
│   │   ├── App.vue           # 根组件 (整合各功能模块)
│   │   └── main.js           # 前端主入口
│   ├── index.html
│   ├── package.json          # Node 依赖配置
│   └── vite.config.js        # Vite 打包与开发服务配置
│
└── README.md                 # 项目运行与启动说明