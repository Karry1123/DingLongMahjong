# 推荐技术栈
针对小白入门、AI 结对编程体验以及后期扩展性，最推荐的组合是：

前端：Vue 3 (SFC 单文件组件) + Vite + Tailwind CSS（UI 组件库推荐可选 Element Plus 或 shadcn-vue）

后端：Python 3.11+ + FastAPI + Pydantic + Uvicorn

数据交换：RESTful JSON API

# 为什么选这个组合？
### 优势所在安装与启动成本极低：
后端只需要在电脑上装好 Python，终端执行两句命令：pip install fastapi uvicorn，随后 uvicorn app.main:app --reload 就能跑起来，自带交互式接口文档（直接访问 http://localhost:8000/docs 就能测试接口）。
前端通过 Node.js 执行 npm create vite@latest frontend -- --template vue，几秒内即可初始化完毕并秒级热重载。
### AI（大模型）写代码适配度最高：
Python + Pydantic 是目前 AI 代码生成质量最高的后端组合之一。定义清楚输入输出的数据类后，AI 在生成算法回溯函数（向听数、顺子刻子拆解） 时报错极少。   
Vue 3 SFC（单文件组件） 把 HTML、JavaScript、CSS 放在同一个 .vue 文件里。对于编程新手来说，让 AI 帮你写组件时，AI 能直接扔给你一个完整的 .vue 代码文件，复制粘贴即可见效，不需要在多个文件之间反复跳转。
### 算法表达清晰自然：
麻将的核心在数据分析、字典计数、排列组合。Python 内置的 collections.Counter、切片以及列表推导式在写麻将逻辑（如白板替换、统计单张有效牌）时，比 JavaScript 或编译型语言更加精炼易懂。   
### 后续扩展容易：
以后想给算法加入蒙特卡洛模拟、死牌过滤或者基于机器学习的牌效模型时，Python 拥有最丰富的数据科学生态；
后续做手机拍照识牌（OCR）时，Python 后端可以直接接入现成的开源视觉库或云端识别 API，无需重构技术底座。