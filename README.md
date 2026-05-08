# 新闻采集工具

热点新闻自动采集 → 去重 → 入库飞书多维表格。

## 数据源

| 平台 | 采集内容 |
|------|---------|
| TapTap | 热门话题（hashtags） |
| B站 | 动画/游戏/番剧/生活/影视 热榜 |
| 百度贴吧 | 热门话题 |
| 微博 | 热搜 TOP20 |
| 抖音 | 热点榜 |
| 今日头条 | 热搜 |

## 定时

- **自动**: 每天北京时间 10:00（GitHub Actions cron: `0 2 * * *`）
- **手动**: GitHub Actions 页面 → `热点新闻采集` → Run workflow

## 本地调试

```bash
# 安装依赖（实际上不需要 pip install，脚本全部用标准库）
cd scripts
python main.py

# 查看结果
cat result.json
```

## GitHub Secrets 配置

在 GitHub 仓库 `Settings → Secrets and variables → Actions` 中添加：

| Secret 名称 | 说明 | 获取方式 |
|------------|------|---------|
| `LARKSUITE_TOKEN` | 飞书 User Access Token | 运行 `larksuite-cli auth login` 后在 `~/.config/larksuite-cli/credentials.json` 中获取 |
| `LARKSUITE_REFRESH_TOKEN` | 刷新 Token | 同上 |

> **重要**：Token 有效期约 30 天，建议在 GitHub Secrets 中设置过期提醒，到期前重新生成。

## 工作流程

1. `collect_taptap.py` / `collect_bilibili.py` / `collect_kaola.py` 并行采集
2. `dedup.py` 与当日已有记录比对，过滤重复
3. `ingest.py` 写入飞书 Base（默认状态：待审核）
4. 结果摘要保存到 `result.json`，供 GitHub Actions 日志查看

## 飞书 Base 表结构

| 字段 | 类型 | 说明 |
|------|------|------|
| 采集日期 | 日期 | 自动填写当天 |
| 是否可用 | 单选 | 默认"待审核" |
| 来源平台 | 文本 | 如"贴吧""B站""TapTap" |
| 标题 | 文本 | |
| 类别 | 单选 | 自动分类：游戏/动漫/影视/泛娱乐/体育/AI/小说 |
| 热度 | 单选 | 自动判断：高/中/低 |
| 原始链接 | 文本 | 点击跳转 |
| 备注 | 文本 | 正文摘要或热度数值 |
