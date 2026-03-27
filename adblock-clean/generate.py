import requests

def load_rules(url):
    print(f"Downloading: {url}")
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    return resp.text.splitlines()

def remove_exact_matches(black_lines, white_url):
    print(f"Downloading whitelist: {white_url}")
    resp = requests.get(white_url, timeout=90)
    resp.raise_for_status()
    white_set = set()
    for line in resp.text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith('#'):
            white_set.add(stripped)
            if stripped.startswith('- '):
                white_set.add(stripped[2:].strip())
    print(f"Whitelist unique rules: {len(white_set)}")

    removed = 0
    clean_lines = []
    for line in black_lines:
        stripped = line.strip()
        if stripped in white_set or (stripped.startswith('- ') and stripped[2:].strip() in white_set):
            removed += 1
            continue
        clean_lines.append(line)
    return clean_lines, removed

def save_file(filename, lines, version, removed):
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# Clean Adblock {version} - 只删除与白名单完全相同的条目\n")
        f.write("# Black: 217heidai/adblockfilters\n")
        f.write("# White: 045200/ad-filter\n")
        f.write(f"# Removed exact matches: {removed}\n")
        f.write(f"# Remaining rules: {len(lines)}\n\n")
        for line in lines:
            f.write(line + "\n")
    print(f"✅ 生成 {filename} 完成！剩余 {len(lines)} 条规则（删除 {removed} 条）")

def main():
    white_url = "https://raw.githubusercontent.com/045200/ad-filter/multi/allow_clash.yaml"

    # 处理完整版
    print("\n=== 处理完整版 (Full) ===")
    full_url = "https://raw.githubusercontent.com/217heidai/adblockfilters/main/rules/adblockmihomo.yaml"
    full_lines = load_rules(full_url)
    clean_full, removed_full = remove_exact_matches(full_lines, white_url)
    save_file("adblock-clean-full.yaml", clean_full, "Full", removed_full)

    # 处理精简版
    print("\n=== 处理精简版 (Lite) ===")
    lite_url = "https://raw.githubusercontent.com/217heidai/adblockfilters/main/rules/adblockmihomolite.yaml"
    lite_lines = load_rules(lite_url)
    clean_lite, removed_lite = remove_exact_matches(lite_lines, white_url)
    save_file("adblock-clean-lite.yaml", clean_lite, "Lite", removed_lite)

if __name__ == "__main__":
    main()
