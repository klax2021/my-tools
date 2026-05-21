import json
from datetime import datetime, timezone, timedelta

# 读取统计
with open("rules_build_stats.json", "r", encoding="utf-8") as f:
    stats = json.load(f)

# 强制使用 UTC+8 时间
utc8 = timezone(timedelta(hours=8))
build_time = datetime.now(utc8).strftime("%Y-%m-%d %H:%M:%S (UTC+8)")

# 计算合计规则数
total_rules = (
    stats["adblock_full_count"] +
    stats["adblock_lite_count"] +
    stats["cdn_count"]
)

# 读取 README
with open("README.md", "r", encoding="utf-8") as f:
    content = f.read()

# 构建新的统计表格
stats_md = f"""<!-- STATS_START -->
📊 **本次构建统计**

| 项目 | 数量 |
|------|------|
| Adblock Full 规则 | {stats["adblock_full_count"]:,} 条 |
| Adblock Lite 规则 | {stats["adblock_lite_count"]:,} 条 |
| CDN 域名 | {stats["cdn_count"]:,} 条 |
| **白名单剔除项** | |
| &nbsp;&nbsp;– Full 中删除 | {stats["removed_full_count"]:,} 条 |
| &nbsp;&nbsp;– Lite 中删除 | {stats["removed_lite_count"]:,} 条 |
| &nbsp;&nbsp;– 去重后总计 | {stats["removed_unique_count"]:,} 条 |
| **合计有效域名规则** | **{total_rules:,} 条** |
| 构建时间 | {build_time} |
<!-- STATS_END -->"""

# 替换或追加
marker_start = "<!-- STATS_START -->"
marker_end = "<!-- STATS_END -->"

if marker_start in content and marker_end in content:
    start_idx = content.find(marker_start)
    end_idx = content.find(marker_end) + len(marker_end)
    new_content = content[:start_idx] + stats_md + content[end_idx:]
else:
    # 如果没有标记，追加到文件末尾
    new_content = content.rstrip() + "\n\n" + stats_md

# 写回 README
with open("README.md", "w", encoding="utf-8") as f:
    f.write(new_content)

print("✅ README 统计已更新")
