import os,re
from datetime import datetime,timezone
from pathlib import Path
import httpx
from fastapi import FastAPI,HTTPException,Depends
from fastapi.responses import HTMLResponse,Response
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from pydantic import BaseModel,Field
from jose import jwt,JWTError
from passlib.context import CryptContext
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

ROOT=Path(__file__).parent; SECRET=os.getenv('SECRET_KEY',''); ALGO='HS256'; pwd=CryptContext(schemes=['bcrypt'],deprecated='auto'); bearer=HTTPBearer(auto_error=False)
app=FastAPI(title='Mikhal Messenger'); app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
client=AsyncIOMotorClient(os.environ['DATABASE_URL'],serverSelectionTimeoutMS=5000) if os.getenv('DATABASE_URL') else None
db=client[os.getenv('MONGODB_DB_NAME','mikhal_messenger')] if client else None
def now(): return datetime.now(timezone.utc).isoformat()
def oid(v):
 try:return ObjectId(v)
 except:raise HTTPException(400,'Invalid ID')
def needdb():
 if db is None:raise HTTPException(503,'Add DATABASE_URL in Render Environment.')
def pub(u):return {'id':str(u['_id']),'username':u['username'],'nickname':u.get('nickname',u['username']),'bio':u.get('bio',''),'is_ai':bool(u.get('is_ai'))}
def issue(uid):
 if not SECRET:raise HTTPException(503,'Add SECRET_KEY in Render Environment.')
 from datetime import timedelta
 return jwt.encode({'sub':str(uid),'exp':datetime.utcnow()+timedelta(days=7)},SECRET,algorithm=ALGO)
async def me(c:HTTPAuthorizationCredentials=Depends(bearer)):
 needdb()
 if not c:raise HTTPException(401,'Sign in required')
 try:u=await db.users.find_one({'_id':oid(jwt.decode(c.credentials,SECRET,algorithms=[ALGO])['sub'])})
 except Exception:raise HTTPException(401,'Session expired')
 if not u:raise HTTPException(401,'User not found')
 return u
class Register(BaseModel): username:str=Field(min_length=3,max_length=24); nickname:str=Field(min_length=1,max_length=40); password:str=Field(min_length=8,max_length=128); bio:str=''
class Login(BaseModel): username:str;password:str
class Contact(BaseModel): username:str
class Space(BaseModel): title:str=Field(min_length=1,max_length=80);kind:str='group';usernames:list[str]=[]
class Message(BaseModel): conversation_id:str;text:str=Field(min_length=1,max_length=10000)
class Prompt(BaseModel): message:str=Field(min_length=1,max_length=10000)
class ImagePrompt(BaseModel): prompt:str=Field(min_length=1,max_length=1800)
class Weather(BaseModel): lat:float;lon:float
AIRCRAFT=[{'id':x,'name':n,'type':t,'source':'https://github.com/amvlab/aircraft-models','license':'CC BY 4.0; credit amvlab/aircraft-models'} for x,n,t in [('a320','Airbus A320','Airliner'),('a350','Airbus A350','Long-haul'),('a380','Airbus A380','Superjumbo'),('b737','Boeing 737','Airliner'),('b787','Boeing 787 Dreamliner','Long-haul'),('evtol','eVTOL','Electric'),('drone','Drone','UAV'),('a320-plain','A320 plain livery','Airliner'),('b737-plain','B737 plain livery','Airliner'),('b787-plain','B787 plain livery','Long-haul')]]
@app.get('/',response_class=HTMLResponse)
async def home():return (ROOT/'index.html').read_text()
@app.get('/api/health')
async def health():return {'status':'ok','database_configured':db is not None,'groq_configured':bool(os.getenv('GROQ_API_KEY')),'cloudflare_configured':bool(os.getenv('CLOUDFLARE_ACCOUNT_ID') and os.getenv('CLOUDFLARE_API_TOKEN')),'weather_configured':bool(os.getenv('OPENWEATHER_API_KEY')),'cesium_configured':bool(os.getenv('CESIUM_ION_TOKEN'))}
@app.post('/api/auth/register')
async def register(d:Register):
 needdb(); un=d.username.strip().lower()
 if not re.fullmatch(r'[a-z0-9_.-]{3,24}',un):raise HTTPException(400,'Use 3–24 letters, digits, dot, underscore or hyphen for username.')
 if await db.users.find_one({'username':un}):raise HTTPException(409,'Username already taken')
 u={'username':un,'nickname':d.nickname.strip(),'bio':d.bio[:240],'password_hash':pwd.hash(d.password),'contacts':[],'created_at':now()}; res=await db.users.insert_one(u);u['_id']=res.inserted_id
 ai=await db.users.find_one({'username':'mikhal_ai'})
 if not ai:
  r=await db.users.insert_one({'username':'mikhal_ai','nickname':'Михаль AI','bio':'Твой встроенный ИИ-помощник','password_hash':'disabled','is_ai':True,'contacts':[],'created_at':now()});ai=await db.users.find_one({'_id':r.inserted_id})
 await db.users.update_one({'_id':u['_id']},{'$addToSet':{'contacts':str(ai['_id'])}})
 await db.conversations.insert_one({'kind':'direct','title':'Михаль AI','members':[str(u['_id']),str(ai['_id'])],'created_by':str(u['_id']),'created_at':now(),'last_message':'Привет! Я Михаль — твой ИИ-помощник.'})
 return {'token':issue(u['_id']),'user':pub(u)}
@app.post('/api/auth/login')
async def login(d:Login):
 needdb();u=await db.users.find_one({'username':d.username.strip().lower()})
 if not u or u.get('is_ai') or not pwd.verify(d.password,u['password_hash']):raise HTTPException(401,'Incorrect username or password')
 return {'token':issue(u['_id']),'user':pub(u)}
@app.get('/api/me')
async def who(u=Depends(me)):return pub(u)
@app.get('/api/users/search')
async def search(q:str,u=Depends(me)):
 if len(q.strip())<2:return {'users':[]}
 cur=db.users.find({'username':{'$regex':re.escape(q.strip()),'$options':'i'},'_id':{'$ne':u['_id']},'is_ai':{'$ne':True}}).limit(20);return {'users':[pub(x) async for x in cur]}
@app.post('/api/contacts')
async def add(d:Contact,u=Depends(me)):
 t=await db.users.find_one({'username':d.username.strip().lower()})
 if not t:raise HTTPException(404,'User not found')
 if t['_id']==u['_id']:raise HTTPException(400,'Cannot add yourself')
 await db.users.update_one({'_id':u['_id']},{'$addToSet':{'contacts':str(t['_id'])}});await db.users.update_one({'_id':t['_id']},{'$addToSet':{'contacts':str(u['_id'])}})
 if not await db.conversations.find_one({'kind':'direct','members':{'$all':[str(u['_id']),str(t['_id'])]}}):await db.conversations.insert_one({'kind':'direct','title':t.get('nickname',t['username']),'members':[str(u['_id']),str(t['_id'])],'created_by':str(u['_id']),'created_at':now(),'last_message':''})
 return {'ok':True}
@app.get('/api/contacts')
async def contacts(u=Depends(me)):
 out=[]
 for x in u.get('contacts',[]):
  try:v=await db.users.find_one({'_id':oid(x)})
  except:v=None
  if v:out.append(pub(v))
 ai=await db.users.find_one({'username':'mikhal_ai'})
 if ai and all(x['id']!=str(ai['_id']) for x in out):out.insert(0,pub(ai))
 return {'contacts':out}
@app.post('/api/conversations')
async def create_space(d:Space,u=Depends(me)):
 if d.kind not in ('group','channel'):raise HTTPException(400,'kind must be group or channel')
 members=[str(u['_id'])]
 for un in d.usernames[:100]:
  x=await db.users.find_one({'username':un.lower().strip()})
  if x:members.append(str(x['_id']))
 doc={'kind':d.kind,'title':d.title.strip(),'members':list(set(members)),'created_by':str(u['_id']),'created_at':now(),'last_message':''};r=await db.conversations.insert_one(doc);doc['id']=str(r.inserted_id);return doc
@app.get('/api/conversations')
async def spaces(u=Depends(me)):
 cur=db.conversations.find({'members':str(u['_id'])}).sort('created_at',-1).limit(100);out=[]
 async for c in cur:out.append({'id':str(c['_id']),'kind':c['kind'],'title':c.get('title','Chat'),'last_message':c.get('last_message',''),'members_count':len(c.get('members',[]))})
 return {'conversations':out}
@app.get('/api/conversations/{cid}/messages')
async def messages(cid:str,u=Depends(me)):
 c=await db.conversations.find_one({'_id':oid(cid),'members':str(u['_id'])})
 if not c:raise HTTPException(404,'Conversation not found')
 cur=db.messages.find({'conversation_id':cid}).sort('created_at',1).limit(250);return {'messages':[{'id':str(m['_id']),'sender_id':m['sender_id'],'sender_name':m.get('sender_name','User'),'text':m['text'],'created_at':m['created_at'],'is_ai':m.get('is_ai',False)} async for m in cur]}
@app.post('/api/messages')
async def send(d:Message,u=Depends(me)):
 c=await db.conversations.find_one({'_id':oid(d.conversation_id),'members':str(u['_id'])})
 if not c:raise HTTPException(404,'Conversation not found')
 m={'conversation_id':d.conversation_id,'sender_id':str(u['_id']),'sender_name':u.get('nickname',u['username']),'text':d.text.strip(),'created_at':now()};r=await db.messages.insert_one(m);await db.conversations.update_one({'_id':c['_id']},{'$set':{'last_message':d.text[:180],'updated_at':now()}});return {'id':str(r.inserted_id),'message':m}
async def groq(prompt):
 key=os.getenv('GROQ_API_KEY')
 if not key:return 'ИИ не подключён: добавь GROQ_API_KEY в Render Environment.'
 body={'model':os.getenv('GROQ_MODEL','llama-3.3-70b-versatile'),'messages':[{'role':'system','content':'Ты Михаль — дружелюбный ИИ-помощник мессенджера. Отвечай на языке пользователя. Помогай с кодом, идеями и навигацией; не утверждай, что выполнил действие, если сервер его не выполнил.'},{'role':'user','content':prompt}],'temperature':0.6,'max_completion_tokens':1200}
 async with httpx.AsyncClient(timeout=60) as c:r=await c.post('https://api.groq.com/openai/v1/chat/completions',headers={'Authorization':'Bearer '+key},json=body)
 if r.status_code>=400:raise HTTPException(502,'Groq API error: '+r.text[:250])
 return r.json()['choices'][0]['message']['content']
@app.post('/api/assistant/chat')
async def ai_chat(d:Prompt,u=Depends(me)):
 answer=await groq(d.message);ai=await db.users.find_one({'username':'mikhal_ai'});c=await db.conversations.find_one({'kind':'direct','members':{'$all':[str(u['_id']),str(ai['_id'])]}})
 if c:
  await db.messages.insert_many([{'conversation_id':str(c['_id']),'sender_id':str(u['_id']),'sender_name':u.get('nickname',u['username']),'text':d.message,'created_at':now()},{'conversation_id':str(c['_id']),'sender_id':str(ai['_id']),'sender_name':'Михаль AI','text':answer,'created_at':now(),'is_ai':True}]);await db.conversations.update_one({'_id':c['_id']},{'$set':{'last_message':answer[:180]}})
 return {'reply':answer}
@app.post('/api/assistant/image')
async def image(d:ImagePrompt,u=Depends(me)):
 acc,key=os.getenv('CLOUDFLARE_ACCOUNT_ID'),os.getenv('CLOUDFLARE_API_TOKEN')
 if not acc or not key:raise HTTPException(503,'Set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN')
 model=os.getenv('CLOUDFLARE_IMAGE_MODEL','@cf/black-forest-labs/flux-1-schnell');url=f'https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/{model}'
 async with httpx.AsyncClient(timeout=120) as c:r=await c.post(url,headers={'Authorization':'Bearer '+key},json={'prompt':d.prompt[:1800],'steps':4})
 if r.status_code>=400:raise HTTPException(502,'Cloudflare AI error: '+r.text[:250])
 img=r.json().get('result',{}).get('image')
 if not img:raise HTTPException(502,'No image returned')
 return {'image_data':'data:image/jpeg;base64,'+img}
@app.post('/api/weather')
async def weather(d:Weather,u=Depends(me)):
 key=os.getenv('OPENWEATHER_API_KEY')
 if not key:raise HTTPException(503,'Set OPENWEATHER_API_KEY')
 async with httpx.AsyncClient(timeout=20) as c:
  a=await c.get('https://api.openweathermap.org/data/2.5/weather',params={'lat':d.lat,'lon':d.lon,'appid':key,'units':'metric'});b=await c.get('https://api.openweathermap.org/data/2.5/forecast',params={'lat':d.lat,'lon':d.lon,'appid':key,'units':'metric'})
 if a.status_code>=400:raise HTTPException(502,'OpenWeather request failed')
 x=a.json();f=b.json() if b.status_code<400 else {};return {'place':x.get('name') or f'{d.lat:.3f}, {d.lon:.3f}','temp':x.get('main',{}).get('temp'),'feels_like':x.get('main',{}).get('feels_like'),'humidity':x.get('main',{}).get('humidity'),'wind':x.get('wind',{}).get('speed'),'description':(x.get('weather') or [{}])[0].get('description',''),'forecast':[{'time':i.get('dt_txt'),'temp':i.get('main',{}).get('temp'),'description':(i.get('weather') or [{}])[0].get('description','')} for i in f.get('list',[])[:8]]}
@app.get('/api/aircraft')
async def aircraft():return {'aircraft':AIRCRAFT,'note':'Model directory: amvlab/aircraft-models; verify exact GLB file names and provide attribution.'}
@app.get('/api/config')
async def config(u=Depends(me)):return {'cesium_token':os.getenv('CESIUM_ION_TOKEN',''),'has_cesium':bool(os.getenv('CESIUM_ION_TOKEN'))}
@app.get('/api/github/inspect')
async def github_inspect(url:str,u=Depends(me)):
 from urllib.parse import urlparse
 p=urlparse(url)
 if p.netloc.lower() not in ('github.com','www.github.com'):raise HTTPException(400,'Only github.com URLs are supported')
 parts=p.path.strip('/').split('/')
 if len(parts)<2:raise HTTPException(400,'Provide repository URL')
 async with httpx.AsyncClient(timeout=20,headers={'Accept':'application/vnd.github+json','User-Agent':'MikhalMessenger'}) as c:r=await c.get(f'https://api.github.com/repos/{parts[0]}/{parts[1]}')
 if r.status_code>=400:raise HTTPException(502,'Could not load GitHub repository metadata')
 x=r.json();return {'name':x.get('full_name'),'description':x.get('description'),'language':x.get('language'),'stars':x.get('stargazers_count'),'url':x.get('html_url')}
@app.get('/api/download/code')
async def download_code(filename:str,content:str,u=Depends(me)):
 name=re.sub(r'[^a-zA-Z0-9._-]','_',filename)[:80] or 'mikhal.txt';return Response(content=content[:500000],media_type='text/plain; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="{name}"'})
@app.on_event('shutdown')
async def close():
 if client:client.close()
