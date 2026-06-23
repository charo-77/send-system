# 项目结构说明 — milu_publish_reverse_20260513

更新时间：2026-06-23

## 项目定位

这是一个百家号/百度创作后台图文自动发布脚本项目。

核心目标：读取本地 Word/docx 文章，使用已登录浏览器会话，通过 Playwright 自动完成：

1. 进入百家号图文编辑页
2. 插入/导入文档
3. 根据文章图片数量选择封面策略
   - 无图：官方 AI 封图
   - 单图：单图封面
   - 多图：三图封面
4. 自动选择活动
5. 点击发布并识别发布结果

## 当前已知主线

根据 `HANDOVER.md` / `PROGRESS.md`，截至 2026-05-26：

- 无图文章链路已实跑通过：导入文档 → 官方 AI封图 → 自动参加活动 → 发布成功
- 单图文章链路已实跑通过：导入文档 → 单图封面 → 自动参加活动 → 发布成功
- 三图文章链路已实跑通过：导入文档 → 三图封面 → 自动参加活动 → 发布成功

## 关键目录

```text
D:\milu_publish_reverse_20260513\
├─ src\                         # 正式代码主目录
├─ HANDOVER.md                   # 交接说明，记录当前稳定结论和运行命令
├─ PROGRESS.md                   # 工程进度
├─ RUNBOOK.md                    # 运行手册/排障手册
├─ WORKBOARD.md                  # 工作看板
├─ README.md                     # 早期说明，当前有编码损坏迹象
├─ requirements.txt              # Python 依赖
├─ launch_*.bat / *.ps1          # 启动脚本
└─ debug_*.py / fix*.py           # 历史调试脚本，部分仍可能有参考价值
```

## `src/` 关键文件初步分工

```text
src/run_publish_draft.py              # 单篇/批量发布入口之一，处理文章、封面模式、结果记录
src/browser_publish.py                # 核心浏览器自动化发布逻辑
src/articles.py                       # docx 文章和图片提取
src/cookies.py                        # cookie/session 读取
src/publish_monitor.py                # 发布过程监控/状态记录
src/status_labels.py                  # 状态中文展示
src/account_manager_qt.py             # 账号管理 GUI
src/account_store.py                  # 账号数据存储逻辑
src/account_browser_*.py              # 账号浏览器/会话工作区/客户端/Hub
src/run_publish_pool.py               # 发布池入口
src/run_publish_folder_and_archive.py # 文件夹发布并归档
src/run_publish_multi_windows_from_xlsx.py # 多窗口/Excel 批量发布
src/run_publish_two_windows_from_xlsx.py   # 双窗口/Excel 批量发布
src/worker_pool_xlsx.py               # Excel 工作者池相关
src/build_worker_pool_from_xlsx.py    # 从 Excel 构建 worker pool
src/publish_live_monitor_qt.py        # 发布实时监控 GUI
src/publish_pool_monitor_bridge.py    # 发布池与监控桥接
src/recover_processing_pool.py        # 恢复处理中任务
src/rebuild_publish_ledger.py         # 重建发布台账
src/cleanup_*.py                      # 清理账号/配额/实名等数据
src/startup_smoke_check.py            # 启动冒烟检查
```

## 目前备份策略

本仓库备份的是“工程逻辑”，不是浏览器登录态或运行垃圾。

已通过 `.gitignore` 排除：

- `edge_profile*` / `edge_profiles*` / `bjh_browser_data/`：浏览器 profile，可能含登录态、缓存、Cookie
- `runtime/` / `runtime_*` / `debug/` / `tmp/`：运行输出和调试产物
- `__pycache__/`：Python 编译缓存
- `ck.txt` / `*.db` / `*.sqlite*`：本地账号/session/数据库类文件
- `*.xlsx` / `*.docx`：本地数据输入
- `*.png` / `*.jpg` 等图片和截图

这样上传 GitHub 更安全，也更便于后续改代码。

## 修改前建议

1. 优先改 `src/` 下正式主线代码。
2. 大量根目录 `debug_*.py` 是历史探针，除非需要回溯页面细节，否则不要把它们当正式入口。
3. 修改涉及发布行为时，先保留 `--keep-open-on-failure` / `--keep-open-after-success`，方便人工验收。
4. 发布/审核流程不要自己加平台外规则提前拦截；如果平台/浏览器阻挡，就按发布失败处理。
