import json
import os
import subprocess
import requests

RULE_DIR = "rules"


def ensure_rule_dir():
  if not os.path.exists(RULE_DIR):
    os.makedirs(RULE_DIR)


def load_yaml_payload(url):
  print(f"下载: {url}")
  r = requests.get(url, timeout=120)
  r.raise_for_status()
  lines = r.text.splitlines()

  payload = []
  in_payload = False
  for line in lines:
    stripped = line.strip()
    if stripped.startswith("payload:"):
      in_payload = True
      continue
    if in_payload:
      if stripped.startswith("- ") or stripped.startswith("+."):
        payload.append(stripped)
  return payload


def normalize_domain(raw_line):
  """把 payload 原始行统一解析成 (domain, is_wildcard)。

  - 去掉 "- " 前缀
  - 去掉单/双引号
  - domain 统一小写，去掉 "+." 通配符前缀后剩下的部分作为 base domain
  - is_wildcard 表示原始规则是否为 "+.example.com" 泛域名写法
    （泛域名会匹配自身及所有子域，精确写法只匹配自身这一个 host）
  """
  s = raw_line.removeprefix("- ").strip()
  s = s.strip("'\"")
  if not s:
    return None, False
  is_wildcard = s.startswith("+.")
  domain = s[2:] if is_wildcard else s
  return domain.lower(), is_wildcard


def build_white_sets(white_lines):
  """白名单拆成两个集合：

  - white_exact: 精确匹配域名（只放行这一个 host）
  - white_wildcard: 泛域名 base（放行自身及所有子域）
  """
  white_exact = set()
  white_wildcard = set()
  for line in white_lines:
    domain, is_wildcard = normalize_domain(line)
    if not domain:
      continue
    if is_wildcard:
      white_wildcard.add(domain)
    else:
      white_exact.add(domain)
  return white_exact, white_wildcard


def is_covered_by_wildcard(domain, wildcard_base):
  """domain 是否等于 wildcard_base 本身，或是它的子域"""
  return domain == wildcard_base or domain.endswith("." + wildcard_base)


def classify_against_white(domain, is_wildcard, white_exact, white_wildcard):
  """判断一条黑名单规则相对白名单的关系，返回三种结果之一：

  "auto"    —— 白名单能完整覆盖这条黑名单规则的拦截范围，可安全自动剔除
  "review" —— 白名单与黑名单存在部分重叠，但覆盖不完整，
             自动剔除可能误放行其他子域或误删其他未涉及的规则，
             转入人工复核名单，不自动改动
  None     —— 白名单与之无关，正常保留在黑名单里
  """
  if not is_wildcard:
    # 黑名单是精确域名：只要有任意等于或覆盖它的白名单条目，即可完整覆盖
    if domain in white_exact:
      return "auto"
    if any(is_covered_by_wildcard(domain, w) for w in white_wildcard):
      return "auto"
    # 白名单里有该域名的子域被放行，说明可能存在关联但不构成完整覆盖
    if any(
        is_covered_by_wildcard(w, domain) for w in white_exact | white_wildcard
    ):
      return "review"
    return None
  else:
    # 黑名单是泛域名（拦截自身+所有子域）：
    # 只有当白名单同样是覆盖自身+所有子域的泛域名，且范围等于或更大时，才算完整覆盖
    if domain in white_wildcard:
      return "auto"
    if any(is_covered_by_wildcard(domain, w) for w in white_wildcard):
      return "auto"
    # 白名单只放行了其中某个精确子域，或放行的泛域名范围更窄——都只是部分覆盖
    if domain in white_exact:
      return "review"
    if any(
        is_covered_by_wildcard(w, domain) for w in white_exact | white_wildcard
    ):
      return "review"
    return None


def clean_blacklist(black_lines, white_exact, white_wildcard):
  """清洗一份黑名单：

  返回 (保留的规则, 自动剔除的规则, 转人工复核的规则)
  """
  clean, removed_auto, review = [], [], []
  for line in black_lines:
    domain, is_wildcard = normalize_domain(line)
    if domain is None:
      clean.append(line)
      continue

    result = classify_against_white(
        domain, is_wildcard, white_exact, white_wildcard
    )
    if result == "auto":
      removed_auto.append(line.removeprefix("- ").strip().strip("'\""))
    elif result == "review":
      review.append(line.removeprefix("- ").strip().strip("'\""))
      clean.append(line)  # 不确定的规则默认保留在黑名单里，避免误放行广告
    else:
      clean.append(line)
  return clean, removed_auto, review


# 修改点：支持在头部添加自定义说明的 YAML 写入函数
def write_payload_yaml(path, title, source, removed_cnt, lines):
  with open(path, "w", encoding="utf-8") as f:
    f.write(f"# {title}\n")
    f.write(f"# 来源: {source}\n")
    f.write(f"# 自动移除白名单冲突: {removed_cnt} 条\n")
    f.write(f"# 最终条数: {len(lines)} 条\n")
    f.write("# ----------------------------------------\n")
    f.write("payload:\n")
    for line in lines:
      f.write("  " + line + "\n")


def convert_to_mrs(input_file, output_file):
  print(f"转换为 MRS: {input_file} → {output_file}")
  subprocess.run(
      [
          os.path.expanduser("~/.cache/mihomo/mihomo"),
          "convert-ruleset",
          "domain",
          "yaml",
          input_file,
          output_file,
      ],
      check=True,
  )


def main():
  ensure_rule_dir()

  # 上游规则
  black_full_url = "https://raw.githubusercontent.com/217heidai/adblockfilters/main/rules/adblockmihomo.yaml"
  black_lite_url = "https://raw.githubusercontent.com/217heidai/adblockfilters/main/rules/adblockmihomolite.yaml"
  white_url = "https://raw.githubusercontent.com/045200/ad-filter/multi/allow_clash.yaml"

  print("加载 Full 黑名单...")
  black_full = load_yaml_payload(black_full_url)
  print("加载 Lite 黑名单...")
  black_lite = load_yaml_payload(black_lite_url)
  print("加载白名单...")
  white = load_yaml_payload(white_url)

  white_exact, white_wildcard = build_white_sets(white)
  print(
      f"白名单解析完成：精确域名 {len(white_exact)} 条，泛域名"
      f" {len(white_wildcard)} 条"
  )

  # Full / Lite 清洗（域名层级关系判断，而非单纯字符串相等）
  clean_full, removed_full, review_full = clean_blacklist(
      black_full, white_exact, white_wildcard
  )
  clean_lite, removed_lite, review_lite = clean_blacklist(
      black_lite, white_exact, white_wildcard
  )

  # 写入 Full / Lite（带注释头部）
  full_yaml = os.path.join(RULE_DIR, "adblock-clean-full.yaml")
  write_payload_yaml(
      full_yaml,
      "干净广告规则 Full（全量去白名单）",
      "217heidai/adblockmihomo + 045200 白名单",
      len(removed_full),
      clean_full,
  )

  lite_yaml = os.path.join(RULE_DIR, "adblock-clean-lite.yaml")
  write_payload_yaml(
      lite_yaml,
      "干净广告规则 Lite（精简去白名单）",
      "217heidai/adblockmihomolite + 045200 白名单",
      len(removed_lite),
      clean_lite,
  )

  # 自动剔除明细（高置信度，白名单完整覆盖，已从黑名单移除）
  removed_yaml = os.path.join(RULE_DIR, "removed_domains.yaml")
  all_removed = sorted(set(removed_full + removed_lite))
  with open(removed_yaml, "w", encoding="utf-8") as f:
    for domain in all_removed:
      f.write(domain + "\n")

  # 人工复核清单（部分重叠、不构成完整覆盖，仍保留在黑名单中，仅供你人工确认）
  review_yaml = os.path.join(RULE_DIR, "suspicious_review.yaml")
  all_review = sorted(set(review_full + review_lite))
  with open(review_yaml, "w", encoding="utf-8") as f:
    for domain in all_review:
      f.write(domain + "\n")

  print(
      f"广告规则生成完成（自动剔除 {len(all_removed)} 条，待人工复核"
      f" {len(all_review)} 条）"
  )

  # === CDN：下载并生成带完整注释的 cdn.yaml（不保存 .txt）===
  cdn_url = "https://ruleset.skk.moe/Clash/domainset/cdn.txt"
  print(f"下载并生成带完整注释的 CDN YAML: {cdn_url}")
  r = requests.get(cdn_url, timeout=120)
  r.raise_for_status()

  cdn_yaml = os.path.join(RULE_DIR, "cdn.yaml")
  lines = r.text.splitlines()
  payload_lines = []
  cdn_count = 0

  for line in lines:
    stripped = line.strip()
    if not stripped:
      # 空行 → 转为空注释行（YAML 序列中不能有裸空行）
      payload_lines.append("  #")
    elif stripped.startswith("#"):
      # 注释行 → 保留原内容，缩进两个空格
      payload_lines.append(f"  {line.rstrip()}")
    else:
      # 域名行 → 转为 - 'xxx'
      payload_lines.append(f"  - '{stripped}'")
      cdn_count += 1

  with open(cdn_yaml, "w", encoding="utf-8") as f:
    f.write("# CDN 域名集合 (来自于 skk.moe)\n")
    f.write(f"# 最终条数: {cdn_count} 条\n")
    f.write("# ----------------------------------------\n")
    f.write("payload:\n")
    for pline in payload_lines:
      f.write(pline + "\n")

  print(f"CDN 规则已保存为带完整注释的 YAML: {cdn_yaml} (共 {cdn_count} 条)")

  # 转换所有 YAML 为 MRS
  convert_to_mrs(full_yaml, os.path.join(RULE_DIR, "adblock-clean-full.mrs"))
  convert_to_mrs(lite_yaml, os.path.join(RULE_DIR, "adblock-clean-lite.mrs"))
  convert_to_mrs(cdn_yaml, os.path.join(RULE_DIR, "cdn.mrs"))

  print("全部规则生成完成！")


if __name__ == "__main__":
  main()
