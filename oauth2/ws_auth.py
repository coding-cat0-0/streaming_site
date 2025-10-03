from datetime import datetime, timedelta
from typing import Dict
from database.structure import get_session
from decouple import config
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodels.tables_schema import Users
from sqlmodel import Session, select
import bcrypt
from typing import Annotated, Optional
from datetime import timedelta, timezone
from fastapi import WebSocket

SECRET_KEY: str = config('SECRET_KEY', cast=str, default='secret')
ALGORITHM: str = config('ALGORITHM', cast=str, default='HS256')
ACCESS_TOKEN_EXPIRE_MINUTES = 3000000
# Security scheme for FastAPI docs
bearer_scheme = HTTPBearer()

# Generate JWT
def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) +( expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM) #Creates a JWT token using the data, secret key, and algorithm.
    #The result is a long string — your access token.
    return encoded_jwt

# Decode JWT & get current websocket . 
async def get_current_ws(websocket : WebSocket,
                    session: Session = Depends(get_session),required_role: Optional[str] = None):
    
    # This is extracting the token from the WebSocket connection URL query parameters.     
    token = websocket.query_params.get("token") 
    if not token:
         print("No token found in query params")
         await websocket.close(code = status.WS_1008_POLICY_VIOLATION)
         return None
     
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print("JWT payload:", payload)
        username: str | None = payload.get("sub")
        user_id: int | None = payload.get("id")
        role : str |None = payload.get("role")
        #role = payload.get("role")
        #print("Decoded token payload:", payload)

        
        query = select(Users).where(Users.email == username, Users.id == user_id)
        user = session.exec(query).first()
        if user is None:
            print(f"User not found for email={username} and id={user_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Could not find user.....")
     
        if user.role != role:
         print("Role mismatch: Token role is", role, "but DB role is", user.role)
         await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
         return None
        
        if required_role and role != required_role:
                await websocket.close(code = status.WS_1008_POLICY_VIOLATION)
                return None
      
        return user
    except JWTError as e:
        print("JWT decode error:", e)
        await websocket.close(code = status.WS_1008_POLICY_VIOLATION)
        return None
