# 企业书开发约定

先读 [README](README.md)，用其中两条命令在本机运行。应用目录是 `enterprise_research/`，仓库内仅有中国石油一个正式研究案例。

- 功能改动从实际路由、处理器或仓储层入手。针对改动运行 `python3 -m unittest discover -s enterprise_research/tests`；涉及界面时在本机打开实际案例查看。
- 中国石油的研究事实、引用页码、估值条件和原图是案例固定输入。功能改动保持这些内容；若明确要改研究，保留已发布版本，按 [整本接口](enterprise_research/MODEL_BOOKS.md) 追加，并核对 [编写标准](enterprise_research/WRITING_STANDARD.md)。
- 数据库、上传目录、本地设置和凭据保留在开发环境。提交代码、文档和确有需要的样例输入，把改动提交到工作分支，附测试结果。

## Gemini 和 Codex 的 GitHub 协作

1. 每项改动或可公开的研究稿从 `main` 新建工作分支，并开一个草稿 PR。PR 写明任务范围、采用的版本、改动和验证结果。报告随稿附原件入口与页码、关键计算和实际图表，按[编辑流程](enterprise_research/EDITORIAL_WORKFLOW.md)交稿。已发布的研究修订时追加版本。
2. Gemini 担任作者时，Codex 独立读稿、核对关键事实与计算，在该 PR 的对应行提意见。Gemini 在同一分支修订并逐项回应。Codex 回读修订稿后把 PR 交给用户决定是否合并。
3. 使用 Gemini 网页端时，从「导入代码」读取当前分支的快照。Gemini 返回稿件或统一 diff，并注明所用分支、对应文件和已做的验证。Codex 按原稿代提交，在 PR 标注作者与代提交人。修订时由 Codex 把 PR 意见和当前版本交给 Gemini，再把它的修订更新到同一 PR。
