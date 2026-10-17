"""Compatibility response for removed room-number matching."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
router=APIRouter(prefix='/api/rooms')
def removed():
    return JSONResponse(status_code=410,content={'detail':'房间号对战已升级为好友邀请，请更新客户端','code':'rooms_removed'})
router.add_api_route('',removed,methods=['POST'])
router.add_api_route('/{anything:path}',removed,methods=['GET'])
