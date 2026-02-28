# US SLG Weekly Video Ads Analyzer 📊🧠

一个由 AI 驱动的全自动买量素材分析引擎。本项目旨在自动化爬取、分析和提炼美国市场头部 SLG（策略类）手游在主流广告网络（Applovin, Facebook）上的优质视频素材，并最终生成一份具有深度行业洞察的战略指导 HTML 报告。

依托于高效且强大的多模态推理模型（Google Gemini 2.5 Flash 及最新前沿的 Gemini 3.1 Pro Preview），本工具能以前所未有的速度和深度，彻底替代传统的人工看周报流程。

---

## 🌟 核心引擎与工作流

本工具的设计遵循一个高效的自动化流水线（Pipeline）：

1. **情报收集 (`src/fetcher.py`)**：从全球顶尖的数据分析平台 **Sensor Tower** 自动拉取过去 7 天内，美国区双端（iOS/Android）表现最顶级的 60 个 SLG 视频广告。
2. **多模态结构化洞察 (`src/analyzer.py`)**：
   - **海量并发拆解**：动用 15 组并发线程，指派视觉模型（支持 `gemini-2.5-flash` 与 `gemini-3.1-pro-preview`）对这 60 个单独的视频进行逐帧拆解。核心提取 5 大维度：*前3秒钩子设计、情绪导向、内容结构、核心爆点/爽点、文案特征*。
   - **降本增效**：得益于 Flash 模型的强劲性能与高并发上限，单周分析视频的账单总额被极大地压缩，并彻底撇去了早期复杂的低清晰度兜底逻辑。
3. **排名趋势追踪与持久化 (`main.py`)**：自动读取上一周的历史榜单存档数据并比对，追踪每个爆款素材周排行变化趋势（上升、下降、新上榜）。所有原始数据通过 GitHub Action 自动归档至 `archive/` 目录以便做永久追溯。
4. **宏观战略大盘研判 (`src/analyzer.py`)**：剥离庞杂的视频原生数据后，将 60 份高度压缩的文本情报统一喂给大模型推理，由它以“买量战略总监”的视角，萃取全渠道投放规律、提炼竞品创新打法，并对下周的素材团队提出**落地方向建议**。
5. **终极视觉呈现 (`src/renderer.py`)**：基于定制的高级 HTML/CSS 模板构建，为这份冰冷的纯文字洞察披上美观、易读的网页高亮外衣。生成的单网页完全支持双击本地运行，更具备浏览器 LocalStorage 无服务端安全鉴权特性，支持无缝独立分发！

---

## 🚀 部署与使用 (本地运行)

### 1. 环境准备
确保你的本地安装有 Python (推荐 3.10+ 版本)。
```bash
# 克隆或下载本仓库
git clone https://github.com/你的名字/us-slg-weekly-ads.git
cd us-slg-weekly-ads

# 安装依赖项
pip install -r requirements.txt
```

### 2. 配置通行密钥 (Secrets)
在项目根目录新建一个名为 `.env` 的文件（请注意，**这个文件千万不能上传到 GitHub！已被列入 .gitignore**）。
在里面填入你的私人 API 授权：

```env
GEMINI_API_KEY=AIzaSy...或者sk-...
SENSOR_TOWER_API_KEY=你的SensorTower密钥...
REPORT_OUTPUT_DIR=reports
```

### 3. 一键出大片
```bash
python main.py
```
终端跑完进度条后，去根目录双击打开 `index.html`（页面会自动重定向跳转）或者进 `archive/` 文件夹里寻找这周最新生成的 `.html` 周报页面以享用 AI 大作！

---

## ☁️ 全自动云端挂机 (GitHub Actions)

为了实现彻底的双手解放，本项目已经内嵌了基于 `ubuntu-latest` 的云端伺服器定时工作流配置 (`.github/workflows/weekly_report.yml`)。

**这套配置将在 每周一北京时间早上 08:30 准时打卡上班！**

### 如何开启“睡后周报”？
1. 在网页端登录你的 GitHub 仓库。
2. 转到仓库的 **Settings (设置)** 工具栏。
3. 在左侧面板的 **Security** 分类下找到 **Secrets and variables > Actions**。
4. 建立名称为 `GEMINI_API_KEY` 和 `SENSOR_TOWER_API_KEY`（如有）的两个机密配置，并粘贴你的真实密钥。
5. 下周一早晨醒来，直接前往仓库的 **Actions** 菜单栏，点击最新成功的运行记录，在屏幕最底部的 **Artifacts** 处直接下载并查阅新鲜出炉的网页报告包！

---

## 📝 架构设计声明与拓展
- 兜底熔断机制：在任何单个视频遭遇网络 404 死链、或者免费版大模型触发了 429 请求超限时，本程序均写有完备的 Fallback Mock 异常降级代码，绝不引发整个并发队列系统崩溃。
- 如遇后续第三方 API Base URL 变更（例如使用代理的 sk- key），请前往 `analyzer.py` 的初始化代码块挂载您的中转 `base_url`。
- 本项目严禁用于倒卖或商用的侵权用途，代码基于公开网络结构探索与探讨为核心目的。
