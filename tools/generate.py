import requests
import subprocess
import os

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

def download_cdn_txt():
    url = "https://ruleset.skk.moe/Clash/domainset/cdn.txt"
    print(f"下载 CDN 域名集: {url}")
    r = requests.get(url, timeout=120)
    r.raise_for_status()

    path = os.path.join(RULE_DIR, "cdn.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(r.text)

    print(f"已保存: {path}")
    return path

def convert_to_mrs(input_file, output_file):
    print(f"转换为 MRS: {input_file} → {output_file}")
    subprocess.run([
        os.path.expanduser("~/.cache/mihomo/mihomo"),  # ←←← 这里是关键修改！
        "convert-ruleset",
        "domain",
        "yaml" if input_file.endswith(".yaml") else "text",
        input_file,
        output_file
    ], check=True)

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

    # 白名单集合
    white_set = set()
    for line in white:
        s = line.removeprefix("- ").strip()
        if s:
            white_set.add(s)
            white_set.add("+" + s)

    # Full 清洗
    clean_full, removed_full = [], []
    for line in black_full:
        s = line.removeprefix("- ").strip()
        if s in white_set:
            removed_full.append(s)
            continue
        clean_full.append(line)

    # Lite 清洗
    clean_lite, removed_lite = [], []
    for line in black_lite:
        s = line.removeprefix("- ").strip()
        if s in white_set:
            removed_lite.append(s)
            continue
        clean_lite.append(line)

    # 写入 Full
    full_yaml = os.path.join(RULE_DIR, "adblock-clean-full.yaml")
    with open(full_yaml, "w", encoding="utf-8") as f:
        f.write("payload:\n")
        for line in clean_full:
            f.write("  " + line + "\n")

    # 写入 Lite
    lite_yaml = os.path.join(RULE_DIR, "adblock-clean-lite.yaml")
    with open(lite_yaml, "w", encoding="utf-8") as f:
        f.write("payload:\n")
        for line in clean_lite:
            f.write("  " + line + "\n")

    # 删除明细
    removed_yaml = os.path.join(RULE_DIR, "removed_domains.yaml")
    all_removed = sorted(list(set(removed_full + removed_lite)))
    with open(removed_yaml, "w", encoding="utf-8") as f:
        for domain in all_removed:
            f.write(domain + "\n")

    print("广告规则生成完成")

    # 下载 CDN TXT
    cdn_txt = download_cdn_txt()

    # 转换广告规则为 MRS
    convert_to_mrs(full_yaml, os.path.join(RULE_DIR, "adblock-clean-full.mrs"))
    convert_to_mrs(lite_yaml, os.path.join(RULE_DIR, "adblock-clean-lite.mrs"))

    # 转换 CDN TXT 为 MRS
    convert_to_mrs(cdn_txt, os.path.join(RULE_DIR, "cdn.mrs"))

    print("全部规则生成完成！")
        # === 输出构建统计到 JSON 文件 ===
    import json

    # 读取 CDN 行数（跳过空行和注释）
    cdn_count = 0
    with open(cdn_txt, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                cdn_count += 1

    # 写入统计
    stats = {
        "adblock_full_count": len(clean_full),
        "adblock_lite_count": len(clean_lite),
        "cdn_count": cdn_count,
        "removed_full_count": len(removed_full),
        "removed_lite_count": len(removed_lite),
        "removed_unique_count": len(all_removed),
    }
    with open("rules_build_stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
