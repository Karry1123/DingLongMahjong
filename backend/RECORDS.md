# PvE 牌谱存储

`GET /api/game/records` 返回最近 10 局的结算摘要，包含四方相对座位的净分、胡数与计分项，不包含牌墙或暗手。`GET /api/game/records/{game_id}` 返回完整牌谱，供赛后逐步复盘使用。

正式结算时 `POST /api/game/record` 归档一局，返回 `GM-xxxxxx` 编号；
`GET /api/game/records/{game_id}` 取回开局四家手牌、发牌后完整牌墙、逐步动作快照与结算结果。
重复提交相同 `round_id` 返回原编号。数据库只保留最新 10 局。

- 本地默认 SQLite：`backend/data/game_records.sqlite3`，或设置 `GAME_RECORD_DB_PATH`。
- 云端持久化：设置 `DATABASE_URL=postgresql://...`，服务将使用 PostgreSQL；
  `GAME_RECORD_DB_PATH` 若同时存在则优先使用 SQLite。

Render 免费 Web Service 的本地文件系统是临时的；要在休眠、重启后保留牌谱，必须配置持久数据库。
当前仓库没有数据库凭据，部署时在服务环境变量中设置 `DATABASE_URL`。
