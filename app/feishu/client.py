"""Only message previews and attachment downloads; no Drive/Wiki mirrors."""
from __future__ import annotations
import json,time
from functools import lru_cache
import httpx
from app.config import settings

class FeishuClient:
    BASE='https://open.feishu.cn/open-apis'
    def __init__(self,app_id,app_secret):
        self.app_id=app_id;self.app_secret=app_secret
        self._token=None;self._expires=0
        self._client=httpx.AsyncClient(timeout=30)

    @staticmethod
    def _check(r):
        r.raise_for_status()
        data=r.json()
        if data.get('code',0)!=0:raise RuntimeError('feishu_api_error code='+str(data.get('code')))
        return data

    async def _tenant_token(self):
        if self._token and self._expires>time.time():return self._token
        r=await self._client.post(self.BASE+'/auth/v3/tenant_access_token/internal',json={'app_id':self.app_id,'app_secret':self.app_secret})
        data=self._check(r)
        if not data.get('tenant_access_token'):raise RuntimeError('feishu_auth_failed')
        self._token=data['tenant_access_token'];self._expires=time.time()+max(0,int(data.get('expire',0))-120)
        return self._token

    async def _auth_headers(self):return {'Authorization':'Bearer '+await self._tenant_token()}

    async def _reply(self,message_id,msg_type,content):
        r=await self._client.post(self.BASE+'/im/v1/messages/'+message_id+'/reply',headers=await self._auth_headers(),json={'msg_type':msg_type,'content':json.dumps(content,ensure_ascii=False)})
        self._check(r)

    async def reply_text(self,message_id,text):await self._reply(message_id,'text',{'text':text})
    async def reply_card(self,message_id,card):await self._reply(message_id,'interactive',card)

    async def download_message_file(self,message_id,file_key,file_type):
        r=await self._client.get(self.BASE+'/im/v1/messages/'+message_id+'/resources/'+file_key,params={'type':file_type},headers=await self._auth_headers())
        r.raise_for_status();return r.content

@lru_cache(maxsize=1)
def get_feishu_client():return FeishuClient(settings.feishu_app_id,settings.feishu_app_secret)
