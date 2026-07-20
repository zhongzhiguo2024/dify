# Dify Fork 分支规范

> Fork 地址：`git@github.com:zhongzhiguo2024/dify.git`
> 上游仓库：`https://github.com/langgenius/dify.git`
> 当前锁定版本：**1.16.0**（上游暂无 v2.0.0 正式 tag）

---

## 分支策略

```
langgenius/dify (上游)
└── main ──────────────────────→ 上游最新代码（只读）

zhongzhiguo2024/dify (本 Fork)
├── main ──────────────────────→ ❌ 不要改！保持与上游 main 一致
├── develop ───────────────────→ ✅ 日常开发分支
├── test ──────────────────────→ ✅ 测试分支
└── custom/release ────────────→ ✅ 生产分支，基于 1.16.0，含 auto_login.py 等 patch
```

### 各分支用途

| 分支 | 用途 | 来源 | 合并方向 |
|------|------|------|---------|
| `main` | 上游镜像，**禁止直接修改** | 与 `langgenius/dify/main` 同步 | ← 仅从上游拉取 |
| `develop` | 日常开发，从 `custom/release` 创建 | 基于 `custom/release` | `develop` → `test` → `custom/release` |
| `test` | 测试验证 | 从 `develop` 合并 | `test` → `custom/release` |
| `custom/release` | 生产分支，含我们的 patch（如 `auto_login.py`） | 基于上游 `1.16.0` tag，定期从上游合并 | 最终合并目标 |

### 开发流程

```bash
# 1. 准备开发
git checkout develop
git merge custom/release          # 确保基于最新代码

# 2. 开发、测试
# ... 修改代码 ...
git add . && git commit -m "feat: xxxx"
git push origin develop

# 3. 合并到 test 验证
git checkout test
git merge develop
git push origin test

# 4. 测试通过后，合并到 custom/release（生产）
git checkout custom/release
git merge test
git push origin custom/release
```

### 拉取上游更新

```bash
cd /Users/gary/Desktop/work/barTech/agent-platform
./scripts/update-dify.sh
```

脚本执行：
1. 从 `upstream_http`（langgenius/dify via 127.0.0.1:7897）拉取最新 tag
2. 显示上游新增的 commit
3. 等你确认 → 合并到本地 `main`
4. 切到 `custom/release` → 合并 `main`
5. 推送到 origin

### 我们的 Patch

仅修改以下文件，**不改 Dify 其他代码**：

| 文件 | 用途 | 行数 |
|------|------|:---:|
| `api/controllers/console/auth/auto_login.py` | 一次性 code → Dify session 免登端点 | ~50 |
| `docker/nginx/conf.d/default.conf` | nginx 路由增量（+7 行） | +7 |
| `docker/.env` | 新增 `PLATFORM_JWT_PUBLIC_KEY` + `PLATFORM_PORTAL_URL` 等 | +3 |

### 严禁事项

- ❌ 不要直接改 `main` 分支
- ❌ 不要在 `custom/release` 上直接开发（先走 develop → test → custom/release）
- ❌ 不要修改 Dify 核心代码（除上述 3 个文件外）
- ❌ 不要从 `custom/release` 往回合并到 `main`
