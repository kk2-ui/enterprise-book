# 企业书开发约定

先读 [README](README.md)，用其中两条命令在本机运行。应用目录是 `enterprise_research/`，仓库内的当前正式企业书和基础档案见 [企业书目录](enterprise_research/research/published_cases/README.md)。

- 功能改动从实际路由、处理器或仓储层入手。针对改动运行 `python3 -m unittest discover -s enterprise_research/tests`；涉及界面时在本机打开实际案例查看。
- 正式企业书的研究事实、引用页码、估值条件和原图是案例固定输入。功能改动保持这些内容；若明确要改研究，保留已发布版本，按 [整本接口](enterprise_research/MODEL_BOOKS.md) 追加，并核对 [编写标准](enterprise_research/WRITING_STANDARD.md)。
- 数据库、上传目录、本地设置和凭据保留在开发环境。提交代码、文档和确有需要的样例输入，把改动提交到工作分支，附测试结果。
