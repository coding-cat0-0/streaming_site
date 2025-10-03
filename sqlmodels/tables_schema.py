from datetime import datetime, date
from sqlmodel import SQLModel, Field, Relationship
from pydantic import field_validator 
import re
from typing import Optional, List


class UserInput(SQLModel):
    name : str
    email : str
    password : str
    @field_validator('email')
    def email_must_be_valid(cls, v):    
        if not re.search(r"\w+@(\w+\.)?\w+\.(com)$",v, re.IGNORECASE):
            raise ValueError("Invalid email format")
        else:
            return v
    @field_validator('password')    
    def password_must_be_strong(cls, p):
             if not re.search(r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[!@#$%&*^_-])[A-Za-z\d!@#$%^&_*-]{8,}$",p):
                 raise ValueError("Invalid Password")
             else:
                    return p   
class UserLogin(SQLModel):

    email : str
    password : str
    @field_validator('email')
    def email_must_be_valid(cls, v):    
        if not re.search(r"\w+@(\w+\.)?\w+\.(com)$",v, re.IGNORECASE):
            raise ValueError("Invalid email format")
        else:
            return v
    @field_validator('password')    
    def password_must_be_strong(cls, p):
             if not re.search(r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[!@#$%&*^_-])[A-Za-z\d!@#$%^&_*-]{8,}$",p):
                 raise ValueError("Invalid Password")
             else:
                    return p                  
                
class Users(SQLModel, table = True):                
            
      id : int = Field(default = None,primary_key = True) 
      name : str = Field(default = None, nullable = False)   
      role : Optional[str] = Field(default = "user")
      email : str = Field(default=None, nullable = False)
      password : str = Field(default = None, nullable = False)     
      created_at :  date = Field(default = date.today(), nullable = False)
      is_banned : bool = Field(default=False)
      suspended_until : bool = Field(default=False)
      otp_code : datetime = Field(default=None, nullable= True) 
      otp_created_at : datetime = Field(default=None, nullable= True) 
      
class ForgetPassword(SQLModel):
    password : str
    otp_code : int      
    @field_validator('password')    
    def password_must_be_strong(cls, p):
             if not re.search(r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[!@#$%&*^_-])[A-Za-z\d!@#$%^&_*-]{8,}$",p):
                 raise ValueError("Invalid Password")
             else:
                    return p         
                
class Videos(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    creator_id : int = Field(default=None, foreign_key="users.id")
    title: str
    description: str | None = None
    category: str | None = None
    tags : str | None = None
    disable_comments: bool = Field(default=False)
    original_url: str | None = None  # full URL to original uploaded video in S3
    hls_url : str | None = None
    url_1080p: str | None = None   # full URL to S3/CloudFront video
    url_720p: str | None = None
    url_480p: str | None = None
    url_360p: str | None = None
    url_144p: str | None = None
    thumbnail_url: str | None = None
    status : str = Field(default="processing")  # processing, available, failed
    copyright_flag: bool = Field(default=False)

class UpdateVideo(SQLModel):                   
    title :str | None = None
    description : str | None = None
    category : str | None = None
    tags : str | None = None
                
class Reports(SQLModel, table= True):
        id : int = Field(default=None, primary_key=True)
        video_id : int | None = Field(default=None, foreign_key="videos.id")
        comment_id : int | None = Field(default=None, foreign_key="comments.id")
        reporter_id : int = Field(default=None, foreign_key="users.id")
        report : int | None = None
        status : str = Field(default = "pending")
        posted_at : datetime = Field(default_factory=datetime.utcnow())
        

class WacthVideos(SQLModel, table=True):
    id : int = Field(default=None, primary_key=True)
    video_id : int = Field(default=None, foreign_key="videos.id")
    creator_id : int = Field(default=None, foreign_key="users.id")
    user_id : int = Field(default=None, foreign_key="users.id")
    start_time :Optional[datetime] = Field(default = None, nullable = False)
    last_stop : Optional[datetime] = Field(default = None, nullable = False)
    end_time : Optional[datetime] = Field(default = None, nullable = False)
    duration : Optional[int] = Field(default = 0, nullable = False)  # in seconds
    

class Comments(SQLModel, table=True):
    id : int = Field(default=None, primary_key=True)
    user_id : int = Field(default=None, foreign_key="users.id")
    video_id : int = Field(default=None, foreign_key="videos.id")
    # Top level comment can have many replies
    parent_comment_id : int | None = Field(default=None, foreign_key="comments.id")

    text : str = Field(default=None)
    created_at : Optional[datetime] = Field(default= None )
    is_like : Optional[bool] = Field(default=None)  # True for like, False for dislike
    parent: "Comments" = Relationship(
        back_populates="replies",
        sa_relationship_kwargs={"remote_side": "Comments.id"}
    )

    replies: List["Comments"] = Relationship(
        back_populates="parent",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan"
        }
    )

          
          
class SubscriptionLink(SQLModel, table=True):
    subsription_id : int = Field(default=None, foreign_key="subscription.id", primary_key=True)
    user_id : int = Field(default=None, foreign_key="users.id", primary_key=True)
    
    
class Subscription(SQLModel, table=True):
    id : int = Field(default=None, primary_key=True)
    user_id : int = Field(default=None, foreign_key="users.id")    
    creator_id : int = Field(default=None, foreign_key="users.id")
    notifications : bool = Field(default=True)
    
class Notificaions(SQLModel, table = True):
    id : int = Field(default=None, primary_key=True)
    user_id : int = Field(default=None, foreign_key="users.id")    
    message : str  = Field(default=None)
    is_read : bool = Field(default=False)
    created_at : Optional[datetime] = Field(default = None )  
    
class LikesDislikes(SQLModel, table=True):
    id : int = Field(default=None, primary_key=True)
    video_id : int = Field(default=None, foreign_key="videos.id")    
    user_id : int = Field(default=None, foreign_key="users.id")
    is_like : bool = Field(default=True)  # True for like, False for dislike    
    
class Analytics(SQLModel, table=True):
    id : int = Field(default=None, primary_key=True)
    video_id : int = Field(default=None, foreign_key="videos.id")    
    creator_id : int = Field(default=None, foreign_key="users.id")
    views : int | None = Field(default=0)
    likes : int | None = Field(default=0)
    dislikes : int | None = Field(default=0)
    comments : int | None = Field(default=0)
    subscription : int | None = Field(default=0)
    watch_time : int | None = Field(default=0)  # in seconds
    
class Channels(SQLModel, table=True):
    id : int = Field(default=None, primary_key=True)
    creator_id : int = Field(default=None, foreign_key="users.id")
    name : str = Field(default=None)
    content_type : str | None = Field(default = None)
    created_at : Optional[datetime] = Field(default = None )    
    
class Complain(SQLModel, table = True):
    id : int = Field(default=None, primary_key=True)
    user_id : int = Field(default=None, foreign_key="users.id")
    subject : str = Field(default=None)
    issue : str = Field(default=None)
    status : str = Field(default="pending")  # pending, resolved, rejected
    created_at : Optional[datetime] = Field(default = None )    
    
class History(SQLModel, table = True):
    id : int = Field(default=None, primary_key=True)
    user_id : int = Field(default=None, foreign_key="users.id")
    video_id : int = Field(default=None, foreign_key="videos.id")
    video_url : str | None = Field(default=None)
    watched_at : Optional[datetime] = Field(default = None )    
   
class Requests(SQLModel, table=True):
    id : int = Field(default=None, primary_key=True)
    user_id : int = Field(default=None, foreign_key="users.id")
    request_type : str = Field(default=None)  # e.g., "feature", "bug", "other"
    description : str = Field(default=None)
    status : str = Field(default="pending")  # pending, in_progress, completed, rejected
    is_accepted : bool | None = Field(default=False)
    created_at : Optional[datetime] = Field(default = None )   
    
class Trending(SQLModel, table = True):
    id : int = Field(default=None, primary_key=True)    
    creator_id : int = Field(default=None, foreign_key="users.id")
    video : str = Field(default = None , foreign_key = "videos.original_url" )
    views : int = Field(default = None)
    duration : int = Field(default = None)