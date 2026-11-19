# 企业书

独立的企业研究工作台：组织企业档案、八章企业书、专题、生命周期、披露资料、研究与估值、跟踪复盘和整本版本。后端使用 Python 标准库和 SQLite，前端使用原生 JavaScript。[当前企业书目录](enterprise_research/research/published_cases/README.md)收录八家正式整本和一份基础档案，可直接在 GitHub 阅读。

## 本地运行

需要 Python 3.10 或更新版本。从仓库根目录运行：

```sh
python3 enterprise_research/research/published_cases/install.py
python3 enterprise_research/app.py
```

打开 [http://127.0.0.1:8778](http://127.0.0.1:8778)，从企业目录点开任一企业。初始化使用仓库内固定输入，无需联网、API Key 或预装数据库。重复执行初始化会保留已有版本。两个命令均可用 `--data-dir` 指定同一个独立数据目录（默认 `enterprise_research/data/`），服务可用 `--port` 更换端口。

程序仅监听本机。行业监测的自动联网采集默认关闭，可按需用 `--schedule-monitor` 开启。工作区内的市场刷新或资料采集可按需手动运行。

中国石油与已保存海尔档案的工作库支持共用三区块市场观察。服务运行期间按交易时区自动更新日线和 CFETS 中间价，页面提供「更新行情」和历史截止控件。来源、首次拉取、网络恢复及实盘核对见 [市场观察更新说明](enterprise_research/MARKET_OBSERVATION.md)。

## 代码和案例入口

- [后端和 HTTP API](enterprise_research/app.py)；[网页路由和工作台](enterprise_research/static/app.js)；[整本前端](enterprise_research/static/model-books.js)。
- [资料和固定版本](enterprise_research/SOURCE_DATA.md)；[外部 Agent 接口](enterprise_research/MODEL_BOOKS.md)；[审阅和发布流程](enterprise_research/EDITORIAL_WORKFLOW.md)。
- [当前企业书与基础档案](enterprise_research/research/published_cases/README.md)
- [中国石油原示例](enterprise_research/research/petrochina_book_20261115/README.md)，含初版的离线整本及固定资料示例。

当前企业书包含各版正文、专题、图表和现有估值，原件优先使用公开链接。当前版本的本地安装保留已有企业书。协作仓库只收录出版内容与公开来源索引，固定资料全文、工作库和个人研究记录留在原工作区。

## 验证

```sh
python3 -m unittest discover -s enterprise_research/tests
```

测试使用临时目录，不写本地案例。编辑案例展示时看 `enterprise_research/static/model-books.js`；修改业务逻辑时优先复用源码和已有测试。建议在分支提交改动并开 Pull Request。
