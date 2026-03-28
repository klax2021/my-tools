import requests

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

def main():
    # 上游规则（官方 Full + Lite）
    black_full_url = "https://raw.githubusercontent.com/217heidai/adblockfilters/main/rules/adblockmihomo.yaml"
    black_lite_url = "https://raw.githubusercontent.com/217heidai/adblockfilters/main/rules/adblockmihomolite.yaml"
    white_url = "https://raw.githubusercontent.com/045200/ad-filter/multi/allow_clash.yaml"

    print("加载 Full 黑名单...")
    black_full = load_yaml_payload(black_full_url)
    print("加载 Lite 黑名单...")
    black_lite = load_yaml_payload(black_lite_url)
    print("加载白名单...")
    white = load_yaml_payload(white_url)

    # 白名单匹配集合
    white_set = set()
    for line in white:
        s = line.removeprefix("- ").strip()
        if s:
            white_set.add(s)
            white_set.add("+" + s)

    # 清理 Full 版 + 记录被删除的域名
    clean_full = []
    removed_full = []
    for line in black_full:
        s = line.removeprefix("- ").strip()
        if s in white_set:
            removed_full.append(s)
            continue
        clean_full.append(line)

    # 清理 Lite 版
    clean_lite = []
    removed_lite = []
    for line in black_lite:
        s = line.removeprefix("- ").strip()
        if s in white_set:
            removed_lite.append(s)
            continue
        clean_lite.append(line)

    # 写入 Full
    with open("adblock-clean-full.yaml", "w", encoding="utf-8") as f:
        f.write("# 干净广告规则 Full（官方全量去白名单）\n")
        f.write("# 来源: 217heidai/adblockmihomo + 045200 白名单\n")
        f.write(f"# 移除冲突: {len(removed_full)}\n")
        f.write(f"# 最终条数: {len(clean_full)}\n\n")
        f.write("payload:\n")
        for line in clean_full:
            f.write("  " + line + "\n")

    # 写入 Lite
    with open("adblock-clean-lite.yaml", "w", encoding="utf-8") as f:
        f.write("# 干净广告规则 Lite（官方精简去白名单）\n")
        f.write("# 来源: 217heidai/adblockmihomolite + 045200 白名单\n")
        f.write(f"# 移除冲突: {len(removed_lite)}\n")
        f.write(f"# 最终条数: {len(clean_lite)}\n\n")
        f.write("payload:\n")
        for line in clean_lite:
            f.write("  " + line + "\n")

    # 生成删除明细
    all_removed = sorted(list(set(removed_full + removed_lite)))
    with open("removed_domains.txt", "w", encoding="utf-8") as f:
        f.write("# 因在白名单中、从黑名单剔除的域名（共 " + str(len(all_removed)) + " 条）\n")
        f.write("# Full 中删除: " + str(len(removed_full)) + " 条\n")
        f.write("# Lite 中删除: " + str(len(removed_lite)) + " 条\n\n")
        for domain in all_removed:
            f.write(domain + "\n")

    print("\n✅ 生成完成：")
    print("Full: " + str(len(clean_full)) + " 条（移除 " + str(len(removed_full)) + " 条）")
    print("Lite: " + str(len(clean_lite)) + " 条（移除 " + str(len(removed_lite)) + " 条）")
    print("📄 删除明细已保存到 removed_domains.txt")

if __name__ == "__main__":
    main()
