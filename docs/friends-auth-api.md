# 账号 / 好友 / 邀请对战 协议契约（v1）

本文件是后端与前端（网页 + App）共享的接口契约。实施期间后端与前端并行开发，**以本文件为准**；需要改动契约时先改本文件再改代码。

## 0. 范围与设计决定

- 取消六位房间号与公开匹配；对战只能通过"邀请好友"发起。
- 新用户必须用 **账号 + 密码 + 注册码** 注册；注册码由站长在本地用 CLI 生成，导入服务端后一次性使用。
- 认证采用 **单一不透明 Bearer token**（随机 256 位，服务端存 SHA-256 摘要，30 天有效，可撤销）。不做 refresh 轮换，不用 cookie（网页托管在 Vercel/GitHub Pages，API 在 Render，跨站 cookie 不可靠）。
  - 网页端：token 存 `localStorage`（key `dl.auth.token`）。
  - App 端：token 存 Capacitor 安全存储；平台层统一通过 `platform/secureSession.js` 暴露 `get/set/clear`。
- 密码哈希：Python 标准库 `hashlib.scrypt`（n=2**14, r=8, p=1，随机 16 字节盐），格式 `scrypt$<n>$<r>$<p>$<salt_b64>$<hash_b64>`。不新增第三方依赖。
- 存储：沿用项目现有模式。`DATABASE_URL` 存在时用 PostgreSQL（psycopg），否则用 SQLite（`AUTH_DB_PATH`，默认 `backend/data/auth.sqlite3`）。所有 SQL 写成两种方言都能跑的子集（`?` 占位符由存储层转换为 `%s`），测试用 SQLite。
- 时间统一 ISO 8601 UTC 字符串；倒计时继续用 `server_time` / `start_at` 毫秒时间戳。
- 错误统一：`{"detail": "<中文可直接展示的消息>", "code": "<snake_case>"}`。401 未登录/失效，403 无权限，404 不存在或不可见，409 状态冲突，422 校验失败，429 限流。
- 用户 ID 为 UUID 字符串。账号 4~24 位 ASCII 字母/数字/下划线，忽略大小写唯一。昵称沿用现有校验（最多 6 字、不得冒充 AI 1~4 号）。密码 8~64 字符。

## 1. 注册码 CLI（仅站长本地）

```
python backend/scripts/registration_codes.py generate --count 20 --batch 2026-10 --expires-in-days 30 --out <私有目录>/codes-2026-10.txt --manifest <私有目录>/codes-2026-10.json
python backend/scripts/registration_codes.py import --manifest <私有目录>/codes-2026-10.json [--dry-run]
python backend/scripts/registration_codes.py revoke --batch 2026-10
python backend/scripts/registration_codes.py list [--batch 2026-10]
```

- 码格式：`XXXX-XXXX-XXXX-XXXX`（Base32 无易混淆字符，≥80 位熵）；服务端比对前去掉 `-`、转大写后求 SHA-256。
- `codes-*.txt` 是明文码（发给用户），`manifest` 只含摘要 + 批次 + 失效时间；`import` 读取 `DATABASE_URL`/`AUTH_DB_PATH` 环境变量，重复导入幂等，已用/已撤销的码不会被重置。
- 默认拒绝覆盖已存在的输出文件。

## 2. 数据表

| 表 | 字段 |
| --- | --- |
| `users` | `id` PK, `account`, `account_normalized` UNIQUE, `display_name`, `password_hash`, `created_at` |
| `registration_codes` | `code_digest` PK, `batch` , `expires_at`, `used_by` NULL, `used_at` NULL, `revoked_at` NULL, `created_at` |
| `auth_tokens` | `token_digest` PK, `user_id`, `client_type` ('web'/'native'), `expires_at`, `revoked_at` NULL, `created_at` |
| `friendships` | `id` PK, `user_low`, `user_high`, `requested_by`, `status` ('pending'/'accepted'), `created_at`, `updated_at`; UNIQUE(user_low,user_high) |
| `matches` | `id` PK, `host_id`, `status` ('inviting'/'waiting'/'countdown'/'playing'/'finished'/'cancelled'/'aborted'), `start_at` NULL, `created_at`, `updated_at` |
| `match_members` | `match_id`, `user_id`, `seat` (1~4), `ready` INT, `joined_at`; PK(match_id,user_id); UNIQUE(match_id,seat) |
| `invitations` | `id` PK, `match_id`, `inviter_id`, `invitee_id`, `status` ('pending'/'accepted'/'declined'/'expired'/'cancelled'), `expires_at`, `created_at`, `responded_at` NULL |

约束：一个用户同一时间只能在一个未结束（`inviting/waiting/countdown/playing`）的 match 中；同一 match 对同一 invitee 最多一个 pending 邀请；只有 accepted 好友可被邀请。

## 3. HTTP API（前缀 `/api`）

所有需要登录的接口带 `Authorization: Bearer <token>`。

### 3.1 账号

| 方法 路径 | 请求 | 响应 |
| --- | --- | --- |
| `POST /auth/register` | `{account, password, display_name, registration_code}` | `201 {user:{id,account,display_name}, token, expires_at}` 注册成功即登录 |
| `POST /auth/login` | `{account, password, client_type?}` | `200 {user, token, expires_at}`；失败统一 `401 {"detail":"账号或密码错误","code":"invalid_credentials"}` |
| `POST /auth/logout` | — | `204`，撤销当前 token |
| `GET /me` | — | `{id, account, display_name, active_match_id}` |
| `PATCH /me` | `{display_name}` | `{id, account, display_name}` |
| `POST /auth/change-password` | `{current_password, new_password}` | `204`，撤销除当前以外的所有 token |

限流：`/auth/login` 与 `/auth/register` 同一 IP 每分钟 10 次，超出 429。

### 3.2 好友

| 方法 路径 | 请求 | 响应 |
| --- | --- | --- |
| `GET /users/search?account=<完整账号>` | — | `{items:[{id, account, display_name, relationship}]}`，`relationship` ∈ `none/self/friend/outgoing/incoming`；最多 1 条 |
| `GET /friends` | — | `{items:[{id, account, display_name, online:bool, in_match:bool}]}` |
| `POST /friend-requests` | `{target_user_id}` | `201 {id, status}`；若对方已向我申请，直接成为好友并返回 `{id,status:'accepted'}` |
| `GET /friend-requests` | — | `{incoming:[{id, from:{id,account,display_name}, created_at}], outgoing:[{id, to:{...}, created_at}]}` |
| `POST /friend-requests/{id}/accept` | — | `{id, status:'accepted'}` |
| `POST /friend-requests/{id}/reject` | — | `204`（拒绝或撤回均用此接口，由申请双方任一方调用） |
| `DELETE /friends/{user_id}` | — | `204`，同时取消双方间未完成邀请 |

### 3.3 邀请与对局

| 方法 路径 | 请求 | 响应 |
| --- | --- | --- |
| `POST /matches` | `{invitee_ids:[1~3 个 user id]}` | `201 {match}`；发起人自动入席（座位 1）并标记 ready；非好友 → 403；自己已在对局中 → 409 |
| `POST /matches/{id}/invitations` | `{invitee_ids:[...]}` | `{match}`，仅 host、仅 `inviting/waiting` 阶段可补邀 |
| `GET /invitations` | — | `{items:[{id, match_id, inviter:{id,account,display_name}, members_count, expires_at}]}` 我收到的 pending 邀请 |
| `POST /invitations/{id}/accept` | — | `{match}`；事务内：校验好友关系、未过期、我不在其他对局；入席最小空座并 ready |
| `POST /invitations/{id}/decline` | — | `204` |
| `GET /matches/{id}` | — | `{match}`，仅成员可见，其余 404 |
| `POST /matches/{id}/start` | — | `{match}`；仅 host；真人 ≥2；取消剩余 pending 邀请、锁定名单、空位补 AI、进入 3 秒倒计时（复用 RoomsManager 倒计时） |
| `POST /matches/{id}/leave` | — | `204`；开局前离席；host 离席 = 取消对局；对局中离席 = 结束整桌（沿用现有解散语义） |
| `GET /me/match-history?limit=20&cursor=` | — | `{items:[{match_id, finished_at, members:[{display_name, seat, score}], hands:int}], next_cursor}` |

`match` 对象：

```json
{
  "id": "uuid", "status": "inviting", "host_id": "uuid",
  "members": [{"user_id":"uuid","account":"a","display_name":"张三","seat":1,"ready":true,"online":true}],
  "invitations": [{"id":"uuid","invitee":{"id":"uuid","account":"b","display_name":"李四"},"status":"pending","expires_at":"..."}],
  "ai_seats": [3,4],
  "start_at": null, "server_time": 1760000000000
}
```

邀请有效期 120 秒；过期由服务端在读取时惰性标记。

### 3.4 旧接口

`/api/rooms/*` 全部移除；保留 `GET /api/rooms/{anything}` 与 `POST /api/rooms` 返回 `410 {"detail":"房间号对战已升级为好友邀请，请更新客户端","code":"rooms_removed"}`。

## 4. WebSocket

### 4.1 社交通道 `GET /api/realtime/ws`

- 连接后 5 秒内客户端发送 `{"type":"authenticate","token":"<bearer token>"}`，否则关闭 (4401)。
- 成功后服务端回 `{"type":"authenticated","user_id":"..."}`。
- 推送（仅作提示，客户端收到后重新拉取对应列表）：
  - `{"type":"friend_request"}`、`{"type":"friend_update"}`
  - `{"type":"invitation","invitation_id":"..."}`、`{"type":"invitation_update","match_id":"..."}`
  - `{"type":"match_update","match_id":"..."}`
- 客户端 `{"type":"ping"}` → `{"type":"pong"}`。
- 在线状态：有社交通道连接即视为 `online`。

### 4.2 对局通道 `GET /api/matches/{id}/ws`

- 同样首条消息 `authenticate`；非成员关闭 (4403)。
- 鉴权后立即收到本人视角完整快照（沿用现有 room socket 的 `state` 消息结构，`client_id` 概念替换为 `user_id`，昵称来自账号）。
- 客户端消息保持现有集合：`seat`、`ready`、`opening_complete`、`game_action`、`next_hand`、`leave`、`ping`；`game_id/revision/action_id` 防过期机制不变。
- 同一用户同一对局只允许一条控制连接；第二条连接返回 `{"type":"error","code":"already_connected"}` 并关闭 (4409)。
- 断线不再立即解散：标记离线，60 秒宽限；等待/倒计时阶段断线取消倒计时；对局中服务端时钟照常运行；宽限超时 → 结束整桌（`aborted`），原因 `disconnect_timeout`。
- 服务重启：启动时把所有未结束 match 标为 `aborted`，释放成员。

## 5. 前端路由（hash 模式，网页与 App 共用）

```
#/login  #/register
#/home   #/friends  #/friends/requests
#/invite  #/matches/:id/waiting  #/matches/:id/play
#/records  #/settings
#/pve  #/sandbox          （现有模式，保持不变）
```

未登录访问除 `/login` `/register` 外的页面 → 跳 `/login?redirect=`。旧链接 `#/pvp`、`#/pvp/room/123456` → 提示"房间号对战已升级为好友邀请"后跳 `/home`。
