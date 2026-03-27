# 生成完整广告规则
with open("adblock-clean-full.yaml", "w", encoding="utf-8") as f:
    f.write("""payload:
  - '+.doubleclick.net'
  - '+.googleadservices.com'
  - '+.ads.youtube.com'
  - '+.ad.com'
""")

# 生成精简版广告规则
with open("adblock-clean-lite.yaml", "w", encoding="utf-8") as f:
    f.write("""payload:
  - '+.doubleclick.net'
  - '+.googleadservices.com'
""")
