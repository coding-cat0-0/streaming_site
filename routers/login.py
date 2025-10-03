from fastapi import APIRouter
from datetime import timedelta
from sqlmodel import SQLModel
from typing import Annotated
from database.structure import get_session
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodels.tables_schema import Users, UserInput, UserLogin, ForgetPassword
from oauth2.jwt_hashing import create_access_token, hash_password, check_hashed_password, get_current_user
from sqlmodel import Session, select
from email.mime.text import MIMEText
import smtplib
from datetime import datetime, timedelta, date
import random

router = APIRouter(
    tags = ['Authentication']
)

# signup router
@router.post('/user_signup')
def create_account(user : UserInput,
             session : Session = Depends(get_session)):
    
    query = session.exec(select(Users).where(Users.email == user.email)).first()
    if query:
        raise HTTPException(status_code=status.HTTP_302_FOUND,
                            detail = "Email already taken use a different one")
    new_user = Users(
        name = user.name,
        #role = "user",
        email = user.email,
        password = hash_password(user.password),
        created_at = date.today()
    )    
    session.add(new_user)
    session.commit()
    session.refresh(new_user)
    return {'message' : 'Account succesfully created!'}

# login router
@router.post('/user_login')
def acc_login(user :UserLogin,
              session: Session = Depends(get_session)):
    
    query = session.exec(select(Users).where(Users.email == user.email)).first()
        
    if query.email !=  user.email:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "Wrong email",
                            headers={"WWW-Authenticate": "Bearer"}
                    )
        
    if not check_hashed_password(user.password, query.password):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "Invalid password") 
     
    if query.is_banned:
             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                 detail = 'Your account has been banned')
             
    if query.suspended_until and query.suspended_until > datetime.utcnow():
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                 detail = f'Your account has been suspended until {query.suspended_until}')

    access_token = create_access_token(data = {'sub' : query.email,
                                    'id' : query.id, 'role' : query.role})
    
    return {'access_token' : access_token, 'token_type' : 'bearer'}    
        

# Generating OTP
def send_otp(to_email: str, otp : str):
    sender_email = "test@sample.com"
    msg = MIMEText(f"Your OTP is {otp}")
    msg['Subject'] = "OTP for login"
    msg['To'] = to_email
    msg['From'] = sender_email 
    server = smtplib.SMTP('localhost', 8025)
    server.send_message(msg)
  
# Router for generating otp  
@router.post('/generate_otp')
def generate_otp(email : str, session: Session = Depends(get_session)):
    otp = str(random.randint(100000, 999999))
    user_obj = select(Users).where(Users.email == email)
    generate = session.exec(user_obj).first()
    if generate:
        generate.otp_code = otp
        generate.otp_created_at = datetime.utcnow()      
        
        session.add(generate)
        session.commit()
        send_otp(generate.email, otp)

        return {"message": "OTP sent to your email"}  
    
    else: 
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found")    
  
# Updating password      
@router.post('/update_password')
def update_password(user : ForgetPassword,
                    session: Session = Depends(get_session)):
    query = select(Users).where(Users.otp_code == user.otp_code)
    user_obj = session.exec(query).first()
    
    if user_obj is not None:
       
        if datetime.utcnow() > user_obj.otp_created_at + timedelta(minutes=2):
            user_obj.otp_code = None
            user_obj.otp_created_at = None
            session.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP expired, please request a new one") 
        else:
            user_obj.password = hash_password(user.password)
            user_obj.otp_code = None
            user_obj.otp_created_at = None
            session.commit()
            return {"message" : "Password changed successfully"}
         
    else: 
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "No user found")
                
  