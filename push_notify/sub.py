from fastapi import APIRouter, Body, Depends
from sqlmodel import SQLModel, Field, Session
from database.structure import get_session

class PushSubscription(SQLModel, table=True):
    id : int | None = Field(default=None, primary_key=True)
    user_id : int
    endpoint : str
    p256dh : str
    auth : str
    
router = APIRouter()

@router.post('/subscribe')
def susbcribe(body = Body(),
              session : Session = Depends(get_session)):    
    
    sub = body['subscribe']
    obj = PushSubscription(
        user_id = body.get('user_id'),
        endpoint = sub['endpoint'],
        p256dh = sub['keys']['p256dh'],
        auth = sub['keys']['auth']
    )
    session.add(obj)
    session.commit()
    session.refresh(obj)
    
    return {'message' : 'OK'}