from fastapi import APIRouter, HTTPException, status
from .sub import PushSubscription
from pywebpush import webpush, WebPushException
from oauth2.jwt_hashing import get_current_user
from database.structure import get_session
from sqlmodels.tables_schema import Users
from sqlmodel import SQLModel, Session, select
import asyncio

with open("vapid_private.pem", 'r') as f:
    VAPID_PRIVATE_KEY = f.read()
    
def send_push_notifications( session : Session,
                            user_id : int, msg : str):
    
    query = session.exec(select(PushSubscription).where(PushSubscription.user_id == user_id)).first()
    if not query:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND,
                            detail = "user not found")
    
    subscription = {
            'endpoint' : query.endpoint,
            'keys' : {
                'p256dh' : query.p256dh,
                'auth' : query.auth
            }
        }    
    
    try:
        webpush(
            subscription_info = subscription,
            data = msg,
            vapid_private_key = VAPID_PRIVATE_KEY,
            vapid_claims = {
                'sub' : 'test@example.gmail.com'
            }
        )
        
    except WebPushException as ex:    
        if ex.response is not None:
            try:
                extra = ex.response.json() # parsing the error msg into json
                print(f"Remote service replied with {extra.get('code')}:{extra.get('errno')}, {extra.get('message')}")
            except Exception:
                print("Remote service replied but response body is not valid JSON")        