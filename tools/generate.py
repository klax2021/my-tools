from datetime import datetime, timezone
import json
import os
import subprocess
import requests

RULE_DIR = "rules"
CUSTOM_DIR = "custom"
STATS_FILE = "rules_build_stats.json"

# 奖励广告审核关键词（仅用于归类标记至 reward_review，不盲目剔除）
REWARD_KEYWORDS = (
    "reward",
    "incentive",
    "taskcenter",
    "admob",
    "union",
    "pangolin",
)


def ensure_dirs():
  os.makedirs(RULE_DIR, exist_ok=True)
  os.makedirs(CUSTOM_DIR, exist_ok=True)


def load_yaml_payload(url):
  """流式抓取并提取 payload 内容"""
  print(f"正在拉取上游: {url}")
  try:
    r = requests.get(url, timeout=120)
    r.raise_for_status()
  except Exception as e:
    print(f"拉取失败: {url}, 错误: {e}")
    return []

  payload = []
  in_payload = False
  for line in r.text.splitlines():
    stripped = line.strip()
    if stripped.startswith("payload:"):
      in_payload = True
      continue
    if in_payload and stripped.startswith("-"):
      payload.append(stripped)
  return payload


def load_local_yaml(file_path):
  """加载本地配置，如 custom/allow.yaml"""
  if not os.path.exists(file_path):
    return []
  print(f"加载本地白名单规则: {file_path}")
  with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()
  payload = []
  in_payload = False
  for line in lines:
    stripped = line.strip()
    if stripped.startswith("payload:"):
      in_payload = True
      continue
    if in_payload and stripped.startswith("-"):
      payload.append(stripped)
    elif not in_payload and stripped.startswith("-"):
      # 兼容没有 payload 标头的纯列表
      payload.append(stripped)
  return payload


def normalize_domain(raw_line):
  """标准化解析各种常见格式：

  - 'example.com'
  - '+.example.com'
  - 'DOMAIN-SUFFIX,example.com'
  - 'DOMAIN,example.com'
  返回: (domain_clean, is_wildcard)
  """
  s = raw_line.removeprefix("- ").strip().strip("'\"")
  if not s or s.startswith("#"):
    return None, False

  is_wildcard = False
  # 兼容 Clash 标准 DOMAIN/DOMAIN-SUFFIX 语法
  if "," in s:
    parts = [p.strip().strip("'\"") for p in s.split(",")]
    rule_type = parts[0].upper()
    domain = parts[1] if len(parts) > 1 else ""
    is_wildcard = rule_type in ("DOMAIN-SUFFIX", "+.")
  else:
    is_wildcard = s.startswith("+.")
    domain = s[2:] if is_wildcard else s

  domain = domain.lower().strip(".")
  return (domain, is_wildcard) if domain else (None, False)


def build_white_index(white_lists):
  """构建白名单两级索引：精准匹配集与泛域名匹配集"""
  exact_set = set()
  wildcard_set = set()

  for rule_list in white_lists:
    for line in rule_list:
      domain, is_wildcard = normalize_domain(line)
      if not domain:
        continue
      if is_wildcard:
        wildcard_set.add(domain)
      else:
        exact_set.add(domain)
  return exact_set, wildcard_set


def is_covered_by_wildcard(domain, wildcard_set):
  """高效逐级查找泛域名匹配（时间复杂度仅取决于域名深度，通常 <= 4 次计算）"""
  parts = domain.split(".")
  for i in range(len(parts)):
    parent = ".".join(parts[i:])
    if parent in wildcard_set:
      return True
  return False


def clean_rules(raw_rules, white_exact, white_wildcard):
  """清洗黑名单规则"""
  clean_payload = []
  removed_auto = []
  suspicious_review = []
  reward_review = []
  seen = set()

  for line in raw_rules:
    domain, is_wildcard = normalize_domain(line)
    if not domain:
      continue

    # 规范化唯一标识用于去重
    unique_key = f"+.{domain}" if is_wildcard else domain
    if unique_key in seen:
      continue
    seen.add(unique_key)

    rule_item = f"- '+.{domain}'" if is_wildcard else f"- '{domain}'"

    # 1. 判断是否被白名单泛域名涵盖
    if is_covered_by_wildcard(domain, white_wildcard):
      removed_auto.append(domain)
      continue

    # 2. 精确域名白名单命中
    if not is_wildcard and domain in white_exact:
      removed_auto.append(domain)
      continue

    # 3. 泛域名黑名单遇上精确白名单（部分重叠，进复核名单，仍保留拦截）
    if is_wildcard and domain in white_exact:
      suspicious_review.append(domain)
      clean_payload.append(rule_item)
      continue

    # 4. 激励广告/任务中心特征识别（保留拦截，但记录至单独清单备查）
    if any(k in domain for k in REWARD_KEYWORDS):
      reward_review.append(domain)

    clean_payload.append(rule_item)

  return clean_payload, removed_auto, suspicious_review, reward_review


def write_yaml(path, title, source, removed_cnt, lines):
  with open(path, "w", encoding="utf-8") as f:
    f.write(f"# {title}\n")
    f.write(f"# 规则生成来源: {source}\n")
    f.write(f"# 自动剔除冲突/白名单: {removed_cnt} 条\n")
    f.write(f"# 最终生效规则: {len(lines)} 条\n")
    f.write(
        "# 更新时间:"
        f" {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
    )
    f.write("# ----------------------------------------\n")
    f.write("payload:\n")
    for line in lines:
      f.write(f"  {line}\n")


def convert_to_mrs(input_file, output_file):
  mihomo_bin = os.path.expanduser("~/.cache/mihomo/mihomo")
  if not os.path.exists(mihomo_bin):
    print(f"未检测到 mihomo 二进制文件，跳过编译: {output_file}")
    return
  print(f"编译规则集为 MRS: {input_file} → {output_file}")
  subprocess.run(
      [
          mihomo_bin,
          "convert-ruleset",
          "domain",
          "yaml",
          input_file,
          output_file,
      ],
      check=True,
  )


def process_cdn(output_yaml):
  cdn_url = "https://ruleset.skk.moe/Clash/domainset/cdn.txt"
  cdn_count = 0
  payload_lines = []
  try:
    print(f"下载 CDN 规则: {cdn_url}")
    r = requests.get(cdn_url, timeout=120)
    r.raise_for_status()
    for line in r.text.splitlines():
      stripped = line.strip()
      if not stripped:
        payload_lines.append("  #")
      elif stripped.startswith("#"):
        payload_lines.append(f"  {line.rstrip()}")
      else:
        payload_lines.append(f"  - '{stripped}'")
        cdn_count += 1
  except Exception as e:
    print(f"CDN 抓取失败: {e}")

  with open(output_yaml, "w", encoding="utf-8") as f:
    f.write("# CDN 域名集合 (来自于 skk.moe)\n")
    f.write(f"# 最终条数: {cdn_count} 条\n")
    f.write("# ----------------------------------------\n")
    f.write("payload:\n")
    for pline in payload_lines:
      f.write(f"{pline}\n")
  return cdn_count


def main():
  ensure_dirs()

  # -------------------- 规则订阅源定义 --------------------
  # 黑名单
  black_full_url = "https://raw.githubusercontent.com/217heidai/adblockfilters/main/rules/adblockmihomo.yaml"
  black_lite_url = "https://raw.githubusercontent.com/217heidai/adblockfilters/main/rules/adblockmihomolite.yaml"
  black_10007_url = "https://raw.githubusercontent.com/lingeringsound/10007_rules/master/clash/block.yaml"

  # 白名单与防误杀（045200 + 10007激励广告放行 + 本地自定义文件）
  white_045200_url = (
      "https://raw.githubusercontent.com/045200/ad-filter/multi/allow_clash.yaml"
  )
  reward_10007_url = "https://raw.githubusercontent.com/lingeringsound/10007_rules/master/clash/reward.yaml"
  custom_allow_file = os.path.join(CUSTOM_DIR, "allow.yaml")

  # -------------------- 抓取与载入 --------------------
  print(">>> 正在拉取黑名单源...")
  raw_full = load_yaml_payload(black_full_url)
  raw_lite = load_yaml_payload(black_lite_url)
  raw_10007 = load_yaml_payload(black_10007_url)

  # 全量聚合黑名单
  merged_full = raw_full + raw_10007
  merged_lite = raw_lite + raw_10007

  print(">>> 正在拉取白名单及纠偏放行清单...")
  white_045200 = load_yaml_payload(white_045200_url)
  reward_10007 = load_yaml_payload(reward_10007_url)
  custom_allow = load_local_yaml(custom_allow_file)

  white_exact, white_wildcard = build_white_index(
      [white_045200, reward_10007, custom_allow]
  )
  print(
      f"白名单构建完成：精准域名 {len(white_exact)} 条，泛域名"
      f" {len(white_wildcard)} 条"
  )

  # -------------------- 清洗流程 --------------------
  print(">>> 正在清洗 Full 规则...")
  clean_full, removed_full, sus_full, rew_full = clean_rules(
      merged_full, white_exact, white_wildcard
  )
  print(">>> 正在清洗 Lite 规则...")
  clean_lite, removed_lite, sus_lite, rew_lite = clean_rules(
      merged_lite, white_exact, white_wildcard
  )

  # -------------------- 写入规则文件 --------------------
  full_yaml = os.path.join(RULE_DIR, "adblock-clean-full.yaml")
  lite_yaml = os.path.join(RULE_DIR, "adblock-clean-lite.yaml")
  cdn_yaml = os.path.join(RULE_DIR, "cdn.yaml")

  write_yaml(
      full_yaml,
      "干净广告规则 Full",
      "217heidai + 10007 (整合过滤版)",
      len(removed_full),
      clean_full,
  )
  write_yaml(
      lite_yaml,
      "干净广告规则 Lite",
      "217heidai-lite + 10007 (精简过滤版)",
      len(removed_lite),
      clean_lite,
  )
  cdn_count = process_cdn(cdn_yaml)

  # 汇总输出审计报告
  all_removed = sorted(set(removed_full + removed_lite))
  all_suspicious = sorted(set(sus_full + sus_lite))
  all_rewards = sorted(set(rew_full + rew_lite))

  with open(
      os.path.join(RULE_DIR, "removed_domains.yaml"), "w", encoding="utf-8"
  ) as f:
    for domain in all_removed:
      f.write(f"{domain}\n")

  with open(
      os.path.join(RULE_DIR, "suspicious_review.yaml"), "w", encoding="utf-8"
  ) as f:
    for domain in all_suspicious:
      f.write(f"{domain}\n")

  with open(
      os.path.join(RULE_DIR, "reward_review.yaml"), "w", encoding="utf-8"
  ) as f:
    for domain in all_rewards:
      f.write(f"{domain}\n")

  # -------------------- 编译 MRS 二进制 --------------------
  convert_to_mrs(full_yaml, os.path.join(RULE_DIR, "adblock-clean-full.mrs"))
  convert_to_mrs(lite_yaml, os.path.join(RULE_DIR, "adblock-clean-lite.mrs"))
  convert_to_mrs(cdn_yaml, os.path.join(RULE_DIR, "cdn.mrs"))

  # -------------------- 生成 Actions 所需统计文件 --------------------
  stats_payload = {
      "adblock_full_count": len(clean_full),
      "adblock_lite_count": len(clean_lite),
      "cdn_count": cdn_count,
      "removed_full_count": len(removed_full),
      "removed_lite_count": len(removed_lite),
      "removed_unique_count": len(all_removed),
  }

  with open(STATS_FILE, "w", encoding="utf-8") as f:
    json.dump(stats_payload, f, ensure_ascii=False, indent=2)

  print(f"✅ 统计文件生成完毕: {STATS_FILE}")
  print(
      f"🚀 全部处理完毕！Full: {len(clean_full)} 条, Lite:"
      f" {len(clean_lite)} 条, 剔除白名单: {len(all_removed)} 条"
  )


if __name__ == "__main__":
  main()
