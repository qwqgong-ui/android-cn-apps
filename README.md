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

## 限制

- `PROCESS-NAME` 在 Android 平台可匹配 App 包名；Windows 上运行的 Mihomo 只能匹配 Windows 本机进程。
- 本规则集必须使用 `behavior: classical`。Mihomo 的 MRS 格式目前仅支持 `domain` 和 `ipcidr`，无法存储 `PROCESS-NAME` 规则。
- 建议将广告拦截规则放在本规则集之前，以免因进程直连而绕过拦截。
