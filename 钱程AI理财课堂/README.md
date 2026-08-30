# 钱程｜AI 理财启蒙课

钱程是一套面向理财初学者的 AI 互动课程，不是开放式理财聊天机器人。六门课都有固定、可验证的教学主线；学习者的选择、理由、追问和老师的解释则因人而异。

产品只做金融素养教育：不推荐真实产品，不给出买卖指令、仓位、资产配置比例或收益承诺。

## 产品闭环

每门课约 10–20 分钟，包含 8 个回合：

1. 生活情境开场
2. 初始判断
3. 专属动手实验
4. 情境变量改变
5. 第一段 AI 自由讨论
6. 迁移到新情境
7. 第二段 AI 自由讨论
8. 行动卡与复述

AI 对话轮数不限，聊天不会自动推进课程。用户主动继续时才进入下一回合；暂时不想回答可以标记“待回看”，结课后再补。六门课分别保存进度，支持退出续学和单课从头学习。

## 六门课

1. 我的钱有任务：用途、日期与现金流优先级
2. 先给生活装一把伞：生活缓冲与选择权
3. 产品不是名字，是任务：期限、变化与取用规则
4. 收益、风险和时间的跷跷板：看见真实取舍
5. 把未来日期放到今天：目标、阶段点与下一步
6. 市场热闹时，先按暂停：情绪、核验与反诈

## 技术结构

```text
client/   Taro 4 + React + TypeScript；同源编译 H5 和微信小程序
backend/  FastAPI + Kimi；课件检索、输出校验、合规回退、静态资源服务
docs/     产品设计、开发计划和部署前检查
```

正式小程序是 Taro 原生构建，不使用 `web-view`。旧静态 HTML Demo 和旧小程序承载壳已移除，避免误开错误版本。

## 本地运行 H5

要求 Node.js 20+、Python 3.11+。

```bash
cd client
npm ci
npm run build:h5

cd ../backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example ../.env
python -m app.server
```

打开 `http://127.0.0.1:8000`。FastAPI 会直接托管 `client/dist/h5`，前端和 API 同源。

## Kimi 配置

密钥只存在服务端，前端和微信小程序包中没有 Key。根目录 `.env` 支持：

```dotenv
MOONSHOT_API_KEY=你的服务端密钥
KIMI_MODEL=kimi-k2.6
```

本机也可以用 `KIMI_SHARED_KEY_PATH` 指向已有密钥文件。腾讯云部署时应改用控制台的加密环境变量 `MOONSHOT_API_KEY`，不能上传本机密钥文件。

模型只收到当前课程、当前回合、最近最多 8 轮对话和本回合允许引用的课件片段。返回内容必须满足结构化字段、课件 evidence_id 白名单与合规规则；任一校验失败即切换到课件驱动的本地安全回答。

## 微信小程序构建

微信小程序只能使用已备案并配置 HTTPS 的后端域名；构建脚本会拒绝空地址、HTTP 地址和本机地址：

```bash
API_BASE=https://你的域名 npm run build:weapp
```

在上传前，把 `client/project.config.json` 中的 `touristappid` 替换成真实小程序 AppID，并在微信公众平台配置服务器域名。

## 容器构建

Dockerfile 使用两阶段构建：Node 阶段生成 H5，Python 阶段安装 FastAPI、复制静态产物并按平台提供的 `PORT` 启动。

```bash
docker build -t qiancheng-learning .
docker run --rm -p 8000:8000 -e MOONSHOT_API_KEY=你的密钥 qiancheng-learning
```

镜像不会复制 `.env`、本机 Key、`node_modules` 或旧 Demo。

## 验证

```bash
cd backend
python -m pytest -q

cd ../client
npm run typecheck
npm test -- --run
npm run build:h5
API_BASE=https://你的域名 npm run build:weapp
```

部署前还需完成腾讯云登录、域名/HTTPS、小程序 AppID 与服务器域名配置。这些属于账号侧操作，代码准备完成后再逐步执行。
