# Egern 三组策略与大陆常用 App 去广告

本目录提供手机独立运行的 Egern 配置。私有版保留原订阅，并内置当前 Trojan 节点的 Egern 原生 UDP 快照，不依赖 Windows、Python、Mihomo 服务或后台服务器。

## 交付文件

- `Profile.example.yaml`：公开脱敏增强版模板，订阅地址为 `SUBSCRIPTION_URL`。
- `Profile.safe.example.yaml`：公开脱敏安全版；无模块、无 MITM，仅保留域名级广告规则。
- 仓库外私有目录中的 `Profile.enhanced.yaml` 与 `Profile.safe.yaml`：写入真实订阅 URL和本地 UDP 快照，严禁加入 Git。
- `Profile.rollback.yaml`：不含模块和本地节点的原订阅回滚版；若 UDP 修正版无法导入，可立即切回。
- `modules/manifest.yaml`：15 个应用的来源、提交、许可证、MITM 域名、脚本 URL、SHA-256 和审查状态。

## 策略与规则

- `净选`：仅匹配“台湾专线B”，每 600 秒用 Google 204 检测，50 ms 切换容差。
- `稳净`：同一候选池，使用 Egern `smart` 的延迟、抖动和成功率历史评分。
- `极速`：排除“台湾专线B”安全节点及流量、官网、套餐、到期、客服等说明节点，使用 Egern `smart` 持续综合多轮延迟、抖动、成功率和运行期故障动态选优，并显式允许 QUIC。
- `PROXY`：依次提供 `极速`、`稳净`、`净选`、`订阅`、`DIRECT`，普通流量默认进入 `极速`。

分流采用“极速优先”：PikPak、普通 Google、YouTube、Cloudflare 和国际 Apple/Microsoft 服务走 `极速`；只有 OpenAI、Gemini、Anthropic/Claude、Copilot 等对出口地区与 IP 风控更敏感的服务进入 `净选`。`极速`与安全池互不重叠，检测结果只保存在 Egern 的动态健康记录中，不会固定为某个节点；`稳净`保留为安全候选池的稳定型手动备选。

当前机场订阅的 Trojan 节点未下发 UDP 字段，而 Egern 的可选布尔字段缺省为 `false`。生成私有版时会把当前 Trojan 节点转换为 Egern 原生格式，显式设置 `udp_relay: true` 与 `block_quic: false`，并在节点名末尾增加 `[UDP]`。三个实际流量策略组只匹配带此标记的本地修正版，避免 Egern 选中同名但未启用 UDP 的远程节点；原订阅仍保留用于刷新来源。机场更换节点地址、密码或名称后，应在电脑上重新运行生成命令并重新导入，才能刷新本地 UDP 快照。

规则顺序固定为：必要放行和局域网 → AdvertisingLite 与广告 SDK → AI → Apple/Microsoft → 中国直连 → `PROXY`。错误的 `192.128.0.0/16` 已删除，链路本地地址使用 `169.254.0.0/16`。

## DNS 边界

默认 DNS 按中国/全球域名分别使用阿里、腾讯与 Cloudflare、Google DoH；代理服务器域名使用独立的加密 `proxy_nameservers`，IPv6 关闭并劫持 53 端口。

Egern 的 Bootstrap 只支持 UDP DNS，且始终直连。本配置显式使用 `223.5.5.5` 与 `119.29.29.29`，不引用系统 DNS，但这不等于“绝对零 DNS 泄漏”：启动时解析加密 DNS 服务器名和失败回退仍受 Bootstrap 机制约束。参见 [Egern DNS 文档](https://egernapp.com/docs/configuration/dns/)。

## 安装顺序

1. 先导入私有 `Profile.safe.yaml`，确认国内网页、国外网页、局域网、OpenAI/Gemini、Apple/Microsoft 和 DoH 均正常。
2. 审查通过后，需要把本目录的公开模块文件发布到配置中填写的 GitHub 路径。当前按要求没有提交或推送，因此这些仓库内模块 URL 在发布前会返回 404；这不影响安全版与域名广告规则。
3. 导入 `Profile.enhanced.yaml`，在 Egern 中安装并信任 CA，再逐个应用验收。Egern 支持 Surge 模块，参见 [官方 FAQ](https://egernapp.com/docs/faq/)。
4. 若登录、内容加载、支付、播放或网络出现异常，立即切回 `Profile.safe.yaml`；不需要删除配置或证书即可先恢复联网。

## 首版 15 项覆盖

| 应用 | 当前方式 | 初始状态 |
|---|---|---|
| 微信公众号 | 审查模块 | 待真机 |
| 微信小程序 | AdvertisingLite + 域名规则 | 深度模块暂缓：含银行/支付接口 |
| 微博 | 去会员图标/皮肤后的审查模块 | 待真机 |
| 知乎 | 审查模块 | 待真机 |
| 哔哩哔哩 | 删除 payment 字段改写后的审查模块 | 待真机 |
| 高德地图 | AdvertisingLite + 域名规则 | 深度模块暂缓：含支付成功接口 |
| 闲鱼 | 审查模块 | 待真机 |
| 淘宝 | 审查模块 | 待真机 |
| 京东 | 审查模块 | 待真机 |
| 拼多多 | 审查模块 | 待真机 |
| 百度贴吧 | 审查模块 | 待真机 |
| 什么值得买 | 删除 `/vip` 脚本后的审查模块 | 待真机 |
| 网易云音乐 | 审查模块 | 待真机 |
| 大陆抖音 | AdvertisingLite + 字节广告 SDK 域名 | 待真机；不使用香港抖音模块 |
| QQ 主应用 | AdvertisingLite + 腾讯广告 SDK 域名 | 待真机；不使用 QQ 音乐模块 |

“去广告”指尽可能覆盖可安全识别的广告。服务端拼接、证书固定、正文同域且无法可靠区分的广告可能无法移除。

## 更新与审计

- AdvertisingLite 与纯规则由 Egern 每日更新。
- 所有 MITM 模块和嵌套脚本固定到提交或 release，并设置 `update_interval: 0`。
- GitHub Actions 每日只生成上游差异报告，不自动改写、提交或发布 MITM 内容。
- `python egern/scripts/validate_egern.py` 检查公开配置；加 `--source <私有源Profile> --live-subscription` 可在本机验证订阅过滤和隐私扫描。
- 重新生成私有文件：

  `python egern/scripts/build_profiles.py --source <原Profile.yaml> --private-dir <仓库外目录>`

## 真机验收记录

每个应用记录“有效 / 部分有效 / 不适用 / 故障”，同时检查登录、正文、支付入口、播放和通知。填写模板见 [`真机验收记录.md`](真机验收记录.md)。真机结果完成前，本项目只满足静态交付，不宣称已完成手机端验收。
