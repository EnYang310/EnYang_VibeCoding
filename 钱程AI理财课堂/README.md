# 钱程｜AI 理财启蒙课

钱程是一套面向理财初学者的 AI 互动课程，不是开放式理财聊天机器人。六门课都有固定、可验证的教学主线；学习者的选择、理由、追问和老师的解释则因人而异。

产品只做金融素养教育：不推荐真实产品，不给出买卖指令、仓位、资产配置比例或收益承诺。

## 在线体验

- [在线体验：钱程｜AI 理财启蒙课](https://qiancheng-ai-finance-agent-287874-10-1325700028.sh.run.tcloudbase.com/#/pages/index/index)
- [GitHub 源码：EnYang310/EnYang_VibeCoding](https://github.com/EnYang310/EnYang_VibeCoding)

> 云端服务采用按需启动。首次访问若暂未加载，请等待 **30–60 秒**，再退出并重新打开体验链接；服务唤醒后可正常进入课程。

## 产品截图

<table>
  <tr>
    <td align="center"><img src="docs/images/portfolio/course-home.jpg" width="260" alt="课程首页与学习地图"><br><b>课程地图</b><br>六门课与单课进度一目了然</td>
    <td align="center"><img src="docs/images/portfolio/lesson-visual-cards.jpg" width="260" alt="可视化理财讲解卡片"><br><b>可视化讲解</b><br>把抽象的理财判断拆成顺序、因果与对比</td>
    <td align="center"><img src="docs/images/portfolio/lesson-interaction.jpg" width="260" alt="互动选择与老师讲解"><br><b>选择后继续上课</b><br>老师围绕学生的选择给出针对性讲解</td>
  </tr>
</table>

## 一、它在解决什么问题

理财初学者并不缺“要记账、要储蓄、要分散风险”这类结论，真正缺的是在工资到账、房租临近、临时支出、朋友推荐产品等场景里，知道该先问什么、先判断什么。

钱程不把用户直接交给一个开放式聊天框，而是设计成由 AI 老师带领的互动课堂：每门课有明确的学习主线和生活情境，学生可以作出选择、追问、反驳或举例；老师则根据课件与当前对话进行讲解，并把关键关系组织成可阅读、可回看的教学卡片。

### 核心产品判断

1. **先讲真实处境，再讲概念**：不从术语开始，而从“这笔钱什么时候要用”“少了会发生什么”开始。
2. **AI 负责教学，不替学生做决定**：老师解释判断依据、纠正误区并追问；不推荐具体金融产品，也不提供买卖指令。
3. **结构化课程与自由讨论可以共存**：学生随时提问，也可以主动点击“进入下一场景”；未答的题会保留，课程不会因一次追问失去主线。
4. **把重点做成可视化内容，而非堆成一段长文字**：顺序、因果、比较、清单和行动提醒分别用不同卡片呈现。

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

学生可以自由追问，也可以随时主动进入下一场景；暂时不想回答的选择题会保留为待回看。六门课分别保存进度，支持退出续学和单课从头学习。

## 六门课

1. 我的钱有任务：用途、日期与现金流优先级
2. 先给生活装一把伞：生活缓冲与选择权
3. 产品不是名字，是任务：期限、变化与取用规则
4. 收益、风险和时间的跷跷板：看见真实取舍
5. 把未来日期放到今天：目标、阶段点与下一步
6. 市场热闹时，先按暂停：情绪、核验与反诈

## 技术结构

```text
client/   Taro 4 + React + TypeScript；面向移动端 H5 的课程界面
backend/  FastAPI + Kimi；课件检索、输出校验、合规回退、静态资源服务
docs/     产品设计、开发计划和部署前检查
```

FastAPI 直接托管构建后的 H5 静态资源，前端页面与 API 同源；旧静态 HTML Demo 已移除，避免误开错误版本。

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

密钥只存在服务端，前端不会包含 Key。根目录 `.env` 支持：

```dotenv
MOONSHOT_API_KEY=你的服务端密钥
KIMI_MODEL=kimi-k2.6
```

本机也可以用 `KIMI_SHARED_KEY_PATH` 指向已有密钥文件。腾讯云部署时应改用控制台的加密环境变量 `MOONSHOT_API_KEY`，不能上传本机密钥文件。

模型只收到当前课程、当前回合、最近最多 8 轮对话和本回合允许引用的课件片段。返回内容必须满足结构化字段、课件 evidence_id 白名单与合规规则；任一校验失败即切换到课件驱动的本地安全回答。

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
```

部署前还需完成腾讯云登录、环境变量配置与域名/HTTPS 配置。这些属于账号侧操作，代码准备完成后再逐步执行。
