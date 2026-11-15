# 企业书

独立的企业研究工作台：组织企业档案、八章企业书、专题、生命周期、披露资料、研究与估值、跟踪复盘和整本版本。后端使用 Python 标准库和 SQLite，前端使用原生 JavaScript。仓库包含一个已发布的正式案例：**中国石油（601857.SH / 00857.HK）企业书修订版**，研究时点为 2026 年 11 月 13 日。

## 本地运行

需要 Python 3.10 或更新版本。从仓库根目录运行：

```sh
python3 enterprise_research/research/petrochina_book_20261115/install.py
python3 enterprise_research/app.py
```

打开 [http://127.0.0.1:8778](http://127.0.0.1:8778)，从企业目录点开「中国石油」。初始化使用仓库内固定输入，无需联网、API Key 或预装数据库。重复执行初始化会保留已有版本。两个命令均可用 `--data-dir` 指定同一个独立数据目录（默认 `enterprise_research/data/`），服务可用 `--port` 更换端口。

程序仅监听本机。行业监测的自动联网采集默认关闭，可按需用 `--schedule-monitor` 开启。工作区内的市场刷新或资料采集可按需手动运行。

## 代码和案例入口

- [后端和 HTTP API](enterprise_research/app.py)；[网页路由和工作台](enterprise_research/static/app.js)；[整本前端](enterprise_research/static/model-books.js)。
- [资料和固定版本](enterprise_research/SOURCE_DATA.md)；[外部 Agent 接口](enterprise_research/MODEL_BOOKS.md)；[审阅和发布流程](enterprise_research/EDITORIAL_WORKFLOW.md)。
- [正式案例说明](enterprise_research/research/petrochina_book_20261115/README.md)；[可编辑正文](enterprise_research/research/petrochina_book_20261115/企业书.md)；[离线整本](enterprise_research/research/petrochina_book_20261115/exports/中国石油企业书_修订版.html)（克隆后用浏览器打开）。

初始化会在本地分配新的公司、整本和上传文件 ID。案例的正文、原件、来源页码、已发表的估值条件和五张原图来自正式发布版；原工作库、公司历史草稿、个人记录和账本不在仓库内。

## 验证

```sh
python3 -m unittest discover -s enterprise_research/tests
```

测试使用临时目录，不写本地案例。编辑案例展示时看 `enterprise_research/static/model-books.js`；修改业务逻辑时优先复用源码和已有测试。建议在分支提交改动并开 Pull Request。
