    flowchart TD
    subgraph Frontend ["前端 (Browser / Vue 3 + Vite)"]
        UI["UI 界面 (选牌键盘、场况设置)"]
        State["Pinia / 响应式状态 (当前14张牌、得牌设置)"]
        Client["Axios / Fetch 请求模块"]
        UI --> State
        State --> Client
    end

    subgraph Backend ["后端 (FastAPI Web Service)"]
        API["/api/recommend 路由接口"]
        Schema["Pydantic 数据校验 (HandRequest, RecommendResponse)"]
        Engine["台州麻将决策引擎"]
        
        subgraph Logic ["算法子模块"]
            Mapper["牌面归一化映射 (白板替身 / 百搭 JOKER 转换)"]
            WinCheck["和牌 / 向听数判定 (带 JOKER 的回溯算法)"]
            EVCalc["单向听有效进张与台州胡头估值 (EV 评分)"]
        end
        
        API --> Schema
        Schema --> Engine
        Engine --> Mapper
        Mapper --> WinCheck
        WinCheck --> EVCalc
    end

    Client -->|HTTP POST JSON 数据| API
    EVCalc -->|返回最优切牌与 EV 列表| API
    API -->|JSON 响应| Client
    Client -->|渲染结果卡片| UI