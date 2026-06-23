# RUNBOOK - milu_publish_reverse_20260513

更新时间：2026-05-27 22:02

## 1. 当前正式主线

这套项目当前正式主线已经实跑通过，且**不要回退旧路线**：

- 无图文章：`导入文档 -> 官方 AI封图 -> 自动参加活动 -> 发布成功`
- 单图文章：`导入文档 -> 单图封面 -> 自动参加活动 -> 发布成功`
- 三图文章：`导入文档 -> 三图封面 -> 自动参加活动 -> 发布成功`

硬约束：

1. 图文入口必须锁定 `type=news`
2. 无图文章必须走百家号官方免费 `AI封图`
3. 活动选择必须在封面后、发布前统一执行
4. 未指定活动名时，默认自动选择第一个可见活动
5. 不要回退到“AI后切本地上传选图”的旧失败路线

---

## 2. 常用运行命令

工作目录：

```powershell
cd /d D:\milu_publish_reverse_20260513
```

### 2.1 单篇发布

```powershell
python .\src\run_publish_draft.py \
  --url "https://baijiahao.baidu.com/builder/rc/edit?type=news" \
  --articles "C:\Users\Administrator\Desktop\mingming\军事" \
  --index 0 \
  --submit \
  --keep-open-on-failure \
  --keep-open-after-success \
  --debug-dir "D:\milu_publish_reverse_20260513\debug\single_run"
```

### 2.2 单篇发布 + 指定活动

```powershell
python .\src\run_publish_draft.py \
  --url "https://baijiahao.baidu.com/builder/rc/edit?type=news" \
  --articles "C:\Users\Administrator\Desktop\mingming\军事" \
  --index 0 \
  --activity "AI文史百工中国" \
  --submit \
  --keep-open-on-failure \
  --keep-open-after-success \
  --debug-dir "D:\milu_publish_reverse_20260513\debug\single_activity"
```

### 2.3 目录批量连续发布

```powershell
python .\src\run_publish_draft.py \
  --url "https://baijiahao.baidu.com/builder/rc/edit?type=news" \
  --articles "C:\Users\Administrator\Desktop\mingming\军事" \
  --all \
  --submit \
  --keep-open-on-failure \
  --debug-dir "D:\milu_publish_reverse_20260513\debug\batch_run"
```

### 2.4 批量试跑前几篇

```powershell
python .\src\run_publish_draft.py \
  --url "https://baijiahao.baidu.com/builder/rc/edit?type=news" \
  --articles "C:\Users\Administrator\Desktop\mingming\军事" \
  --all \
  --limit 2 \
  --submit \
  --keep-open-on-failure \
  --debug-dir "D:\milu_publish_reverse_20260513\debug\batch_limit2"
```

### 2.5 批量发布 + 保守重试

```powershell
python .\src\run_publish_draft.py \
  --url "https://baijiahao.baidu.com/builder/rc/edit?type=news" \
  --articles "C:\Users\Administrator\Desktop\mingming\军事" \
  --all \
  --submit \
  --max-retries 1 \
  --retry-delay-seconds 5 \
  --keep-open-on-failure \
  --debug-dir "D:\milu_publish_reverse_20260513\debug\batch_retry"
```

---

## 3. 输出文件怎么看

### 3.1 监控文件

运行后重点看：

- `发布监控.json`
- `发布监控.txt`
- `发布监控_UTF8.txt`

卡片/UI 现在至少会显示：

- 账号
- 文件夹
- 文章标题
- 封面模式
- 活动状态
- 已成功 / 计划发
- 当前状态

### 3.2 结构化结果文件

批量/单篇结果会持续写入：

- `publish_results.json`
- `batch_report.json`
- `batch_report.txt`

单篇或每篇结果里至少包含：

- `title`
- `docx_path`
- `cover_mode`
- `activity_status`
- `activity_name`
- `published`
- `success_url`
- `failure_code`
- `failure_reason`
- `attempt_no`
- `max_attempts`
- `retryable`

`batch_report.json` / `batch_report.txt` 会额外汇总：

- 总篇数 / 成功数 / 失败数
- 首次成功数
- 重试后成功数
- 按 `failure_code` 分组的失败统计
- 失败篇目标题清单

### 3.3 调试目录

每篇会有独立调试目录，常见内容：

- `result.json`
- `page_state.json`
- `after_publish.png`

---

## 4. 当前失败分类

当前已经接入的失败分类：

- `captcha`：百度验证码 / 安全验证未完成
- `wrong_entry`：未稳定进入 `type=news` 图文编辑页
- `doc_import_open`：导入文档入口或上传控件未成功触发
- `doc_import_materialize`：文档已上传但标题/正文未真正落地
- `cover_skipped`：封面流程因前置条件失败被跳过
- `cover_failed`：封面流程未确认完成
- `activity_mismatch`：指定活动未匹配成功
- `submit_click_failed`：发布按钮未成功点击
- `submit_no_success_marker`：已执行发布，但未识别到成功页标记
- `submit_unknown`：疑似已提交，但成功标记识别不完整
- `network`：疑似网络抖动或服务端临时异常
- `unknown`：未命中已知分类

说明：
- 这套分类是收尾阶段的“可读性分类”，不是重构主链
- 优先用于批量发布后快速看懂失败分布
- 当前默认建议只对这些失败码做保守重试：`network`、`wrong_entry`、`doc_import_open`、`submit_click_failed`、`submit_no_success_marker`、`submit_unknown`
- 默认不建议自动重试：`captcha`、`activity_mismatch`、`cover_failed`、`doc_import_materialize`

---

## 5. 已确认不要回退的路线

不要再做这些返工：

1. 不要把无图封面改回本地上传图
2. 不要把活动逻辑改回“只有传 `--activity` 才执行”
3. 不要把图文入口放松到可能误进“动态”
4. 不要重写已实跑通过的无图 / 单图 / 三图主链
5. 不要在人工验收时双开观察窗口

---

## 6. 当前最适合继续做的事

按优先级：

1. 继续清理 `browser_publish.py` 中真正无用的调试残留
2. 细化失败分类（尤其区分风控、验证码、活动未命中、封面未确认）
3. 观察一轮真实批量跑出来的 `publish_results.json`，再决定是否补重试策略

---

## 7. 一句话

**这项目现在该做的是固化、收尾、降返工，不是回头重写已经跑通的主链。**
