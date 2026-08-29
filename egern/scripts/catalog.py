from __future__ import annotations

PUBLIC_RAW_BASE = (
    "https://raw.githubusercontent.com/M0ON-W/"
    "flclash-dynamic-strategy-portable/main/egern"
)

COMMITS = {
    "fmz": "2d95818e34fa2eada06b114f9968a5283beb06de",
    "app2smile": "df6366a7024e0b3f0aa3510c5b791eea6f3cba89",
    "bili": "43b07841fa55ba77e29d478cab0be44c8b49a3c2",
    "qingrex": "913ec005f544221e6c56a7d0ecec81c4b3b914bb",
    "zmqcherish": "1d9f51bc9a0077d81998bb503ee6158ca83faa73",
    "ishowshu": "64dca36e675911f7751eae5d839c2e1e3b02e843",
    "keywos": "e38265cc902852aa8ec6ec831509ea0be6492260",
}

MODULES = [
    {
        "id": "wechat-official-account",
        "app": "微信公众号",
        "repo": "fmz",
        "source_rel": "Surge/module/split/partW/WeChatOfficialAccount.sgmodule",
        "artifact": "modules/gpl-3.0/wechat-official-account.sgmodule",
        "license": "GPL-3.0",
        "review_status": "approved",
        "default_enabled": True,
        "notes": "仅过滤公众号文章广告和推荐内容。",
    },
    {
        "id": "wechat-mini-program",
        "app": "微信小程序",
        "repo": "qingrex",
        "source_rel": "Surge/微信小程序去广告.sgmodule",
        "artifact": None,
        "license": "unclear-aggregation",
        "review_status": "held",
        "default_enabled": False,
        "notes": "含银行、支付与会员相关接口；不进入增强版，仅由域名规则提供有限覆盖。",
    },
    {
        "id": "weibo",
        "app": "微博",
        "repo": "fmz",
        "source_rel": "Surge/module/weibo.module",
        "artifact": "modules/gpl-3.0/weibo-ad-only.sgmodule",
        "license": "GPL-3.0",
        "review_status": "approved-sanitized",
        "default_enabled": True,
        "notes": "删除自定义皮肤、非会员皮肤及会员图标三条非广告功能。",
    },
    {
        "id": "zhihu",
        "app": "知乎",
        "repo": "fmz",
        "source_rel": "Surge/module/split/partZ/Zhihu.sgmodule",
        "artifact": "modules/gpl-3.0/zhihu.sgmodule",
        "license": "GPL-3.0",
        "review_status": "approved",
        "default_enabled": True,
        "notes": "vip_tab 仅移除会员页面内的推广卡片，不更改会员状态。",
    },
    {
        "id": "bilibili",
        "app": "哔哩哔哩",
        "repo": "bili",
        "source_rel": "template/surge.handlebars",
        "artifact": "modules/apache-2.0/bilibili-ad-only.sgmodule",
        "license": "Apache-2.0",
        "review_status": "approved-sanitized",
        "default_enabled": True,
        "notes": "基于 v0.6.24 模板生成，删除番剧 payment 字段改写。",
    },
    {
        "id": "amap",
        "app": "高德地图",
        "repo": "qingrex",
        "source_rel": "Surge/高德地图去广告.sgmodule",
        "artifact": None,
        "license": "unclear-aggregation",
        "review_status": "held",
        "default_enabled": False,
        "notes": "聚合模块会改写支付成功和会员提示接口，且嵌套脚本不可完整固定；不启用 MITM。",
    },
    {
        "id": "xianyu",
        "app": "闲鱼",
        "repo": "fmz",
        "source_rel": "Surge/module/split/partX/XianYu.sgmodule",
        "artifact": "modules/gpl-3.0/xianyu.sgmodule",
        "license": "GPL-3.0",
        "review_status": "approved",
        "default_enabled": True,
        "notes": "推广卡片与广告接口净化，外部脚本固定到审查提交。",
    },
    {
        "id": "taobao",
        "app": "淘宝",
        "repo": "fmz",
        "source_rel": "Surge/module/split/partT/Taobao.sgmodule",
        "artifact": "modules/gpl-3.0/taobao.sgmodule",
        "license": "GPL-3.0",
        "review_status": "approved",
        "default_enabled": True,
        "notes": "仅广告与推广内容净化。",
    },
    {
        "id": "jd",
        "app": "京东",
        "repo": "fmz",
        "source_rel": "Surge/module/split/partJ/JD.com.sgmodule",
        "artifact": "modules/gpl-3.0/jd.sgmodule",
        "license": "GPL-3.0",
        "review_status": "approved",
        "default_enabled": True,
        "notes": "仅广告与推广内容净化。",
    },
    {
        "id": "pinduoduo",
        "app": "拼多多",
        "repo": "fmz",
        "source_rel": "Surge/module/split/partP/Pinduoduo.sgmodule",
        "artifact": "modules/gpl-3.0/pinduoduo.sgmodule",
        "license": "GPL-3.0",
        "review_status": "approved",
        "default_enabled": True,
        "notes": "仅广告与推广内容净化。",
    },
    {
        "id": "tieba",
        "app": "百度贴吧",
        "repo": "app2smile",
        "source_rel": "module/tieba.sgmodule",
        "artifact": "modules/mit/tieba.sgmodule",
        "license": "MIT",
        "review_status": "approved",
        "default_enabled": True,
        "notes": "广告 JSON/Proto 与广告域名净化。",
    },
    {
        "id": "smzdm",
        "app": "什么值得买",
        "repo": "fmz",
        "source_rel": "Surge/module/split/partS/SMZDM.sgmodule",
        "artifact": "modules/gpl-3.0/smzdm-ad-only.sgmodule",
        "license": "GPL-3.0",
        "review_status": "approved-sanitized",
        "default_enabled": True,
        "notes": "删除三个 /vip 路径脚本，只保留普通页面广告净化。",
    },
    {
        "id": "netease-music",
        "app": "网易云音乐",
        "repo": "fmz",
        "source_rel": "Surge/module/split/partW/NetEaseCloudMusic.sgmodule",
        "artifact": "modules/gpl-3.0/netease-music.sgmodule",
        "license": "GPL-3.0",
        "review_status": "approved",
        "default_enabled": True,
        "notes": "仅广告内容净化，外部脚本固定到审查提交。",
    },
    {
        "id": "douyin-mainland",
        "app": "大陆抖音",
        "repo": "local-rules",
        "source_rel": "rules/ad-sdk.yaml",
        "artifact": None,
        "license": "project",
        "review_status": "domain-only",
        "default_enabled": True,
        "notes": "不使用香港抖音模块；只拦截明确字节广告 SDK 域名。",
    },
    {
        "id": "qq-main",
        "app": "QQ 主应用",
        "repo": "local-rules",
        "source_rel": "rules/ad-sdk.yaml",
        "artifact": None,
        "license": "project",
        "review_status": "domain-only",
        "default_enabled": True,
        "notes": "不使用 QQ 音乐模块；只拦截明确腾讯广告 SDK 域名。",
    },
]

REPO_ROOT_NAMES = {
    "fmz": "wool_scripts",
    "app2smile": "app2smile-rules",
    "bili": "bili-adblock",
    "qingrex": "loon-kiss-surge",
    "zmqcherish": "proxy-script",
    "ishowshu": "ishowshu-qx",
    "keywos": "keywos-rule",
}


def source_url(item: dict) -> str:
    rel = item["source_rel"].replace("\\", "/")
    repo = item["repo"]
    if repo == "fmz":
        return f"https://raw.githubusercontent.com/fmz200/wool_scripts/{COMMITS[repo]}/{rel}"
    if repo == "app2smile":
        return f"https://raw.githubusercontent.com/app2smile/rules/{COMMITS[repo]}/{rel}"
    if repo == "bili":
        return "https://github.com/BiliUniverse/ADBlock/releases/tag/v0.6.24"
    if repo == "qingrex":
        return f"https://raw.githubusercontent.com/QingRex/LoonKissSurge/{COMMITS[repo]}/{rel}"
    return f"{PUBLIC_RAW_BASE}/{rel}"


def enabled_module_urls() -> list[dict]:
    result = []
    for item in MODULES:
        if item["default_enabled"] and item["artifact"]:
            result.append(
                {
                    "name": f"{item['app']}去广告（已审查）",
                    "url": f"{PUBLIC_RAW_BASE}/{item['artifact']}",
                    "update_interval": 0,
                    "enabled": True,
                }
            )
    return result
