# 发布清单（dsh-visio）

## 1. 提交并打 tag

```bash
git add -A
git commit -m "Release 1.24.0"
git tag v1.24.0
git push && git push --tags
```

## 2. 本地自检

```bash
npm pack --dry-run          # 20 files / ~123 kB
pytest tests/test_engine.py -q      # 40 passed
node tests/test_client_render.mjs   # 3 checks
```

## 3. 发布到 npm

```bash
npm login
npm publish --access public
# 验证插件管理器能看到它
pnpm view dsh-visio name version engines peerDependencies dsh --json
```

## 4. 收录进插件市场索引

DSH 默认不带索引源。两个办法：

- 自建索引：把 `publish/index-entry.json` 放到任意 https 静态地址，用户在
  Plugins → Discover → Index sources 添加该地址即可。
- 社区清单（awesome-dsh-plugin / dsh-plugin-catalog，1 万+ 条目）：向
  https://github.com/awesome-dsh-plugin/awesome-dsh-plugin 提 PR，按它的条目格式
  加一行 `- [SamyiHu/dsh-visio](https://github.com/SamyiHu/dsh-visio) — 说明`。
  收录条件只有一条：`dsh plugin add` 能装上（即声明了 `dsh.bundle`）。

## 5. 用户侧安装路径

- 应用内：Settings → Plugins → 搜 `dsh-visio`
- 命令行：`dsh plugin --profile desktop add dsh-visio`
