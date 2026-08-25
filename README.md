# android-cn-apps

Mihomo classical rule-set，用 Android App 包名匹配国内应用并直连。当前包含 52 条规则，按通讯影音、电商生活、银行政务、办公服务、工具游戏和 realme/OPPO/ColorOS 生态分类。

## 使用

先开启 Mihomo 进程匹配：

```yaml
find-process-mode: always
```

添加 rule-provider：

```yaml
rule-providers:
  android-cn-apps:
    type: http
    behavior: classical
    format: yaml
    url: https://raw.githubusercontent.com/qwqgong-ui/android-cn-apps/main/android-cn-apps.yaml
    path: ruleset/android-cn-apps.yaml
    interval: 86400
```

在 `rules` 中引用：

```yaml
rules:
  # 先放广告拦截规则
  - RULE-SET,android-cn-apps,DIRECT
```

如果配置中的直连策略组名为 `🟢`，则改成：

```yaml
- RULE-SET,android-cn-apps,🟢
```

## 统一域名拦截规则

仓库每天聚合 4 个外部规则源和本仓库 `reject.yaml`，经解析、
小写化、精确去重和保守的后缀包含裁剪后，编译为单一 domain MRS：

- MetaCubeX `category-ads-all` (`.list`)
- MetaCubeX `category-httpdns-cn` (`.list`)
- wwqgtxx `reject` (`.list`)
- 217heidai `adblockmihomolite` (`.yaml`)
- 本仓库 `reject.yaml` (`custom-reject`)

四个外部源都拉取上游发布的规则文本，而不是它们同时发布的 `.mrs`。
`.mrs` 是上游用自己那一版 Mihomo 编译出来的二进制产物，直接解包会把合并
结果的语义绑定在别人的工具链上；改从文本拉取后，全部规则都由本仓库锁定的
Mihomo 版本编译。所有规则源（含 `reject.yaml`）还会先经过严格校验：
`mihomo convert-ruleset domain text` 对任何一行都照单全收，若上游改用
classical 规则（`DOMAIN-SUFFIX,example.com`）、Geosite 属性
（`keyword:`、`regexp:`）或 IP 字面量，这些无法匹配的条目会被静默写进
MRS；现在它们会直接让构建失败。

`reject-ip.mrs` / `custom-reject-ip` 仍是独立的 ipcidr 规则集，不参与聚合。

```yaml
rule-providers:
  reject-all:
    type: http
    behavior: domain
    format: mrs
    interval: 86400
    proxy: 🌐
    url: https://raw.githubusercontent.com/qwqgong-ui/android-cn-apps/refs/heads/main/reject-all.mrs
    path: ruleset/reject-all.mrs
  custom-reject-ip:
    type: http
    behavior: ipcidr
    format: mrs
    interval: 86400
    proxy: 🌐
    url: https://raw.githubusercontent.com/qwqgong-ui/android-cn-apps/refs/heads/main/reject-ip.mrs
    path: ruleset/custom-reject-ip.mrs

rules:
  - RULE-SET,reject-all,🛑
  - RULE-SET,custom-reject-ip,🛑,no-resolve
```

`reject.mrs` 继续只代表本仓库的 custom-reject，便于兼容旧配置；
`reject-all.mrs` 是新的统一路由拦截产物。`reject.yaml` 包含自定义域名规则，
HTTPDNS 域名已从
`BlockHttpDNS_No_Resolve.yaml` 和 `HTTPDNS.Block.list` 合并并去重。
两份上游中的 `IP-CIDR`/`IP-CIDR6` 因无法存入 domain MRS，统一放在
`reject-ip.yaml`。

手动构建需要 `mihomo`、Python 3 和 `curl`：

```shell
./scripts/build-reject-all.sh
```

GitHub Actions 每天 UTC 18:00（UTC+8 02:00）运行，也支持手动触发；
`reject.yaml` 或构建脚本修改时也会构建。工作流会校验规则语法、MRS behavior、
规则数、往返 dump、IP/CIDR 混入和 custom-reject 覆盖，并且仅在产物变化时提交。

## 限制

- `PROCESS-NAME` 在 Android 平台可匹配 App 包名；Windows 上运行的 Mihomo 只能匹配 Windows 本机进程。
- 本规则集必须使用 `behavior: classical`。Mihomo 的 MRS 格式目前仅支持 `domain` 和 `ipcidr`，无法存储 `PROCESS-NAME` 规则。
- 建议将广告拦截规则放在本规则集之前，以免因进程直连而绕过拦截。
