# ============================================================
# 配置
# ============================================================

# 飞书多维表格
BASE_TOKEN = "WoV5b0tNLa2ivgsXiFCc4X4cnse"
TABLE_ID   = "tblriEgkdfJHu0Gh"

# 字段 ID（从飞书 Base 获取）
FIELD_DATE    = "fldof2SgQX"   # 采集日期
FIELD_STATUS  = "fldfhviVpZ"   # 是否可用（默认"待审核"）
FIELD_SOURCE  = "fld1j6Fa87"   # 来源平台
FIELD_TITLE   = "fldfD4DH44"   # 标题
FIELD_CAT     = "fldWokpWWp"   # 类别
FIELD_HOT     = "fld7RKtJm7"   # 热度
FIELD_URL     = "fld4Vt8uju"   # 原始链接
FIELD_NOTE    = "fldDyPONW7"   # 备注

# 分类关键词（与飞书 Base 类别选项对应）
CATEGORIES = {
    "游戏":    ["游戏", "开服", "停服", "抽卡", "版本", "角色", "联动", "IP", "手游", "端游"],
    "动漫":    ["动画", "番剧", "轻小说", "漫画", "二次元", "声优", "OVA"],
    "影视":    ["电影", "电视剧", "综艺", "定档", "开播", "热播", "演员", "导演"],
    "泛娱乐":  ["明星", "热搜", "话题", "粉丝", "演唱会", "出道", "塌房", "恋情"],
    "体育":    ["足球", "篮球", "奥运", "世界杯", "欧冠", "NBA", "CBA", "网球"],
    "AI":      ["大模型", "AI", "LLM", "ChatGPT", "GPT", "Claude", "DeepSeek", "AGI"],
    "小说":    ["网文", "起点", "晋江", "阅文", "小说", "IP改编", "作者"],
}

# 热度判断：正文/摘要字数
HOT_HIGH  = "高"
HOT_MED   = "中"
HOT_LOW   = "低"

# 去重窗口（天）：同类标题在 N 天内出现视为重复
DEDUP_WINDOW_DAYS = 3
