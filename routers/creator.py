from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, Form
from oauth2.jwt_hashing import get_current_user
from sqlmodels.tables_schema import Users, Videos, Reports, WacthVideos, Trending, UpdateVideo, Requests,Comments, Subscription, LikesDislikes, Analytics, Channels, Complain, History,SubscriptionLink, Notificaions
from sqlmodel import Session, select, func, desc
from database.structure import get_session
from datetime import timedelta, datetime, date
from typing import Optional
import boto3
import uuid
from s3_worker.server import upload_to_s3
from s3_worker.worker import process_video
import asyncio 
from ws_router.websockets import active_connections
from push_notify.push_func import send_push_notifications

router = APIRouter(
    tags=['Creator']
)
 
@router.post('/upload_video')
async def upload_video(
                 file: UploadFile, session: Session = Depends(get_session),
                 title: str = Form(), description: str = Form(),
                 category: str = Form(), tags : str = Form(),
                 disable_comments : bool = Form(),
                 current_user : Users = Depends(get_current_user())):
    
    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")
    
    try:  
        file_name = file.filename.split(".")[-1] # automatically gets the name and extension i.e mp4
        unique_filename = f"{uuid.uuid4()}.{file_name}" # unique id and file name
        s3_key = f"uploads/{unique_filename}" # unique id and file name
        # file.file is a file-like object also automatically provided by FastAPI
        bucket_name = "my-fastapi-videos"
        public_url = upload_to_s3(file.file, s3_key, bucket=bucket_name, extra_args= {"ACL": "public-read"})
        
        video = Videos(
            creator_id = current_user.id,
            original_url = public_url,
            title = title,
            description = description,
            category= category,
            tags = tags,
            disable_comments = disable_comments,
            status = "processing"
        )
        
        session.add(video)
        session.commit()
        session.refresh(video)        

        process_video.delay(s3_key, bucket_name, video.id)

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=str(e))
    email = current_user.email
    if email in active_connections:
        asyncio.create_task(
            send_notification(
                email,
                "Your video has been uploaded successfully"
            )
        )    
    subscribers = session.exec(select(Subscription).where(Subscription.creator_id == current_user.id)).all()
    for sub in subscribers:
        send_push_notifications(session, sub.user_id, f"{current_user.name} just uploaded a new video!")
    
    return {
            "message": "Video processing started",
            "video_id": video.id
            }    
        
@router.get('/my_videos')        
def my_videos(session: Session = Depends(get_session),
              current_user : Users = Depends(get_current_user())):

    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")
    
    query = session.exec(select(Videos).where(Videos.creator_id == current_user.id)).all()
    if not query:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND,
                            detail = "No videos uploaded yet")
        
    return query

@router.get('/view_most_viewed')    
def most_viewed(session: Session = Depends(get_session),
                current_user : Users = Depends(get_current_user())):

    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")
    
    first_query = session.exec(select(WacthVideos.creator_id, func.count(WacthVideos.id).label(
        "view_count")).group_by(WacthVideos.creator_id).where(WacthVideos.creator_id == current_user.id
        ).order_by(desc("view_count"))).all()
    
    if not first_query:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND,
                            detail = "No views yet")
    
    creator_ids = [r.creator_id for r in first_query]
    trending_videos = session.exec(select(Videos).where(Videos.creator_id.in_(creator_ids))).all()
    
    return trending_videos
    
@router.get('/update_video_details')    
def update_video( update : UpdateVideo, video_id : int,
                 session: Session = Depends(get_session),
                 current_user : Users = Depends(get_current_user())):

    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")

    query = session.get(Videos, video_id)
    
    if not query:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND,
                            detail = f"Video with id {video_id} not found")
    
    else:
        for key, value in update.model_dump(exclude_unset=True).items():
            if value not in (None,"", "string"):
               setattr(query, key, value) 
                  
    session.add(query)           
    session.commit()
    
    return {"message" : "Video details updated successfully"}

@router.delete('/creator/delete_video')
async def delete_video(video_id : int,
                 session:Session = Depends(get_session),
                 current_user : Users = Depends(get_current_user())):

    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")
    
    first_query = session.exec(select(Videos).where(Videos.id == video_id,
                                Videos.creator_id == current_user.id)).first()
    if not first_query:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND,
                            detail=f"Video with id {video_id} not found")
        
    second_query = session.exec(select(WacthVideos).where(WacthVideos.video_id == video_id)).all()
    session.delete(first_query)
    for views in second_query:
        session.delete(views)
        
    session.commit()
    
    email = current_user.email
    if email in active_connections:
        asyncio.create_task(
            send_notification(
                email,
                "Your video has been deleted successfully"
            )
        )
    return {'message' : 'Video deleted successfully'}

@router.post('//creator/play_video')
def play_video(video_id : int, 
               session: Session = Depends(get_session),
               current_user : Users = Depends(get_current_user())):
    
    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")
    timestamp = datetime.utcnow()
    
    video = session.get(Videos, video_id)
    if not video or video.status != "available":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "Video not found or not available")
        
    query = session.exec(select(WacthVideos).where(WacthVideos.video_id == video_id, 
                                       WacthVideos.creator_id == video.creator_id,
                                       WacthVideos.user_id == current_user.id)).first()  
    
    if not query:  
        watch = WacthVideos(
            video_id = video_id,
            creator_id = video.creator_id,
            user_id = current_user.id,
            start_time = timestamp,
            last_stop = timestamp,
            end_time = None,
            duration = 0
        )
        session.add(watch)    
        session.refresh(watch)
        
    store_history = History(
        video_id = video_id,
        video_url = video.original_url,
        user_id = current_user.id,
        watched_at = timestamp
    )
    session.add(store_history)
    
    analytics = session.exec(select(Analytics).where(Analytics.video_id == video_id)).first() 
    if analytics:
        analytics.views += 1   
        
    engagement = Analytics(
        video_id = video_id,
        creator_id = video.creator_id,
        likes = 0,
        dislikes = 0,
        comments = 0,
        watch_time = 0
        )
    if watch is not None:
        engagement.views += 1
        
    session.add(engagement)
    session.refresh(engagement)
    session.commit()

    
    return {"message": f"Video started", "watch_id" : watch.id}

@router.post('/creator/pause_video')
def pause_video(watch_id : int, 
               session: Session = Depends(get_session),
               current_user : Users = Depends(get_current_user())):
      
    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")     
      
    timestamp = datetime.utcnow()  
    watch = session.get(WacthVideos, watch_id)
    
    if not watch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "Watch session not found")

    delta = (timestamp - watch.last_stop).total_seconds()
    watch.duration += int(delta)
    watch.last_stop = None
        
    session.commit()

    
    return {"message": "Video paused"} 
        
@router.post('/creator/resume_video')
def resume_video(watch_id : int, 
               session: Session = Depends(get_session),
               current_user : Users = Depends(get_current_user())):

    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")

    timestamp = datetime.utcnow()  
    
    watch = session.get(WacthVideos, watch_id)
    
    if not watch :
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "Watch session not found")

    watch.last_stop = timestamp
 
    session.commit()    
    
    return {"message": "Video resumed"}  
    
@router.post('/creator/end_video')
def end_video(watch_id : int,
               session: Session = Depends(get_session),
               current_user : Users = Depends(get_current_user())):
      
    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")
        
    timestamp = datetime.utcnow()  
    
    watch = session.get(WacthVideos, watch_id)
    
    if not watch :
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "Watch session not found")

    delta = (timestamp - watch.last_stop).total_seconds()
    watch.duration += int(delta)
    watch.end_time = timestamp
    
    analytics = session.exec(select(Analytics).where(Analytics.video_id == watch.video_id)).first()
    if analytics:
        analytics.watch_time += watch.duration
    
    session.commit()

    return {"message": "Video ended"} 

@router.post('/subscribe_unsubscribe')
async def subscribe(creator_id : int,
              session: Session = Depends(get_session),
              current_user : Users = Depends(get_current_user())):
   
    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")

    query = session.exec(select(Channels).where(Channels.user_id == creator_id)).first()
        
    if query:
        subscribe = Subscription(
            user_id = current_user.id,
            creator_id = creator_id,
            notifications = True
        )
        session.add(subscribe)
        session.refresh(subscribe)
        link = SubscriptionLink(
            subsription_id = subscribe.id,
            user_id = current_user.id
        )
        session.add(link)
        session.refresh(link)
    
    engagement = Analytics(
        creator_id = creator_id
    )    
    if subscribe:
        engagement.subscribers += 1
    session.commit()
    
    email = current_user.email
    if email in active_connections:
        asyncio.create_task(
            send_notification(
                email,
                f"Subscribed to {query.name}"
            )
        )
    
    send_push_notifications(session, query.user_id, f"{current_user.name} just subscribed to you")
        
    return {'message' : f'Subscribed to {query.name} successfully'}

@router.delete('/unsubscribe')
async def unsubscribe(creator_id : int,
                session: Session = Depends(get_session),
                current_user : Users = Depends(get_current_user())):
    
    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")   
    
    query = session.exec(select(Subscription).where(Subscription.creator_id == creator_id,
                            Subscription.user_id == current_user.id)).first()
    engagement = session.exec(select(Analytics).where(Analytics.creator_id == creator_id)).first()
    
    if not query and engagement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "Subscription not found")
        
    session.delete(query)
    session.commit()
    if engagement.subscribers > 0:
        engagement.subscribers -= 1
    
    email = current_user.email
    if email in active_connections:
        asyncio.create_task(
            send_notification(
                email,
                f"Unsubscribed to {query.name}"
            )
        )
    
    return {'message' : 'Unsubscribed successfully'}    
        
@router.post('/turn_off_notifications')
async def turn_off_notifications(creator_id : int, notify : bool = False,
                    session: Session = Depends(get_session),
                    current_user : Users = Depends(get_current_user())):

    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")

    query = session.exec(select(Subscription).where(Subscription.creator_id == creator_id,
                                                    Subscription.user_id == current_user.id)).first()
    if not query:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "Subscription not found")
        
    query.notifications = notify
    session.add(query)
    session.commit()
    
    email = current_user.email
    if email in active_connections:
        asyncio.create_task(
            send_notification(
                email,
                "Notifications turned off"
            )
        )
    
    return {'message' : 'Notification preference updated successfully'}

@router.get('/get_notifications')
def get_notifications(session: Session = Depends(get_session),
                        current_user : Users = Depends(get_current_user())):

    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")

    query = session.exec(select(Notificaions).where(Notificaions.user_id == current_user.id,
                                                    Notificaions.is_read == False)).all()
    if not query:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "No new notifications")
        
    for notify in query:
        notify.is_read = True
        session.add(notify)
        
    session.commit()
    return {'notifications' : query}
    
@router.post('/comment')
def post_comment(video_id : int, text : str = Form(),
                 session: Session = Depends(get_session),
                 current_user : Users = Depends(get_current_user())):

    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")

    video = session.get(Videos, video_id)
    if not video or video.status != "available":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "Video not found or not available")
        
    if video.disable_comments:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail = "Comments are disabled for this video")
        
    comment = Comments(
        video_id = video_id,
        parent_comment_id = None,
        user_id = current_user.id,
        text = text,
        is_like = None,
        created_at = date.today()
    )
    session.add(comment)
    session.refresh(comment)
    
    engagement = Analytics(
        video_id = video_id,
        creator_id = video.creator_id
    )
    if comment is not None:
        engagement.comments += 1
    
    session.add(engagement)

    session.commit()
    
    send_push_notifications(session, video.creator_id, f"{current_user.name} just commented on your video")    
    
    return {'message' : 'Comment posted successfully'}    

@router.post('/reply_comment')
def reply_comment(video_id : int, parent_comment_id : int,
                  text : str = Form(), session: Session = Depends(get_session),
                    current_user : Users = Depends(get_current_user())):

    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")
        
    comments = session.get(Videos, video_id)
    if comments.disable_comments:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail = "Comments are disabled for this video")
        
    query = session.exec(select(Comments).where(Comments.id == parent_comment_id)).first()
    if not query:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "Parent comment not found")
    
    comment = Comments(
    video_id = video_id,
    parent_comment_id = parent_comment_id,
    user_id = current_user.id,
    text = text, 
    is_like= None,
    created_at = date.today()
    )
    session.add(comment)
    session.refresh(comment)

    engagement = Analytics(
    video_id = video_id,
    creator_id = comments.creator_id
    )
    if query is not None:
        engagement.comments += 1
    
    send_push_notifications(session, query.user_id, f"{current_user.name} just replied to your comment")
    session.commit()
    return {'message' : 'Reply posted successfully'}

@router.delete('/delete_comment')
async def delete_comment(comment_id : int, creator_id : int,
                   video_id,
                   session: Session = Depends(get_session),
                   current_user : Users = Depends(get_current_user())):

    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")
        
        
    engagement = session.exec(select(Analytics).where(Analytics.video_id == video_id,
                            Analytics.creator_id == creator_id)).first() 
    comment = session.get(Comments, comment_id)
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "Comment not found")
      
    session.delete(comment)

    comment_replies = session.exec(select(Comments).where(Comments.parent_comment_id == comment_id)).all()
    delete_count = 1 + len(comment_replies) # if no parent len is 0 count is 1
    
    try:
        if engagement.comments >= delete_count:       
            engagement.comments -= delete_count 
        else:
            raise ValueError("Engagement comments are zero or less than delete count")
    except ValueError as e: 
        print(f"Error: {e}")  
        
    for reply in comment_replies: # deleting all replies from comments table
            session.delete(reply)     

    session.commit()    
   
    return {'message' : 'Comment and its replies deleted successfully'} 

@router.post('/report_video')
async def report_video(video_id : int, report : str = Form(),
                 session: Session = Depends(get_session),
                 current_user : Users = Depends(get_current_user())):

    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")

    query = session.exec(select(Users).where(Users.role == "admin"))
    
    video = session.get(Videos, video_id)
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "Video not found")
        
    report = Reports(
        video_id = video_id,
        comment_id = None,
        reporter_id = current_user.id,
        report = report,
        status = "pending",
        posted_at = date.today()
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    
    email = current_user.email
    if email in active_connections:
        asyncio.create_task(
            send_notification(
                email,
                "Your report has been submitted successfully"
            )
        )
    
    for x in query:
            send_push_notifications(session, query.user_id, f"{current_user.name} just submitted  report")
        
    return {'message' : 'Video reported successfully'}


@router.post('/report_comment')
async def report_comment(
                    comment_id : int, report : str = Form(),
                    session: Session = Depends(get_session),
                    current_user : Users = Depends(get_current_user())):
  
     if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")    

     admins = session.exec(select(Users).where(Users.role == "admin")).all()
    

     query = session.exec(select(Comments).where(Comments.id == comment_id)).first()
     if not query:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                             detail = "Comment not found")
          
     report = Reports(
          video_id = None,
          comment_id = comment_id,
          reporter_id = current_user.id,
          report = report,
          status = "pending",
          posted_at = date.today()
     )
     session.add(report)
     session.commit()
     session.refresh(report)
     
     email = current_user.email
     if email in active_connections:
        asyncio.create_task(
            send_notification(
                email,
                "Your report has been submitted successfully"
            )
        )
     for admin in admins:
            send_push_notifications(session, admin.user_id, f"{current_user.name} just submitted  report")
     return {'message' : 'Comment reported successfully'}
 
    
@router.post('/like_dislike') 
def like_dislike(video_id : int, is_like : bool | None ,
                 session: Session = Depends(get_session),
                 current_user : Users = Depends(get_current_user())):
    
    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")    
    
    if current_user.role != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are already a creator")    
    
    video = session.get(Videos, video_id)
    if not video or video.status != "available":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "Video either removed or unavailable") 
    
    analytics = session.exec(select(Analytics).where(Analytics.video_id == video_id)).first()
    if not analytics:
        analytics = Analytics(
        video_id = video_id,
        creator_id = video.creator_id
        )
        session.add(analytics)
        
    confirmation = session.exec(select(LikesDislikes).where(LikesDislikes.video_id == video_id,
                                LikesDislikes.user_id == current_user.id)).first()
    
    if not confirmation:
        reaction = LikesDislikes(
            video_id = video_id,
            user_id = current_user.id,
            is_like = is_like
        )
        
        if is_like:
            analytics.likes += 1
        else:
            analytics.dislikes += 1    
            
        session.add(reaction)

    else:
        if confirmation.is_like != is_like:
            if is_like:
                analytics.likes += 1
                analytics.dislikes -= 1
            else:
                analytics.dislikes += 1
                analytics.likes -= 1

            confirmation.is_like = is_like        
             
    session.commit()       
    
    # no option for None i.e no like or dislike
    state = "liked" if is_like else "disliked"
    
    send_push_notifications(session, video.creator_id, f"{current_user.name} just {state} your video")
    return {'message' : f'Video {state} successfully'}


@router.get('/liked_videos')
def liked_videos(session: Session = Depends(get_session),
                current_user : Users = Depends(get_current_user())):
        
    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")       
        
    liked = session.exec(select(LikesDislikes).where(LikesDislikes.user_id == current_user.id,
                            LikesDislikes.is_like == True)).all()
    if not liked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail= "No liked videos found")
        
    liked_videos_id = [l.video_id for l in liked]     
        
    liked_videos = session.exec(select(Videos).where(Videos.id.in_(liked_videos_id))).all()
    return {'liked_videos' : liked_videos}
    
   
@router.get('/your_subscribtions')    
def your_subscribtions(session: Session = Depends(get_session),
                      current_user : Users = Depends(get_current_user())):
    
    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")
        
        
    subscribtions = session.exec(select(Subscription).where(Subscription.user_id == current_user.id)).all()
    if not subscribtions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "No subscribtions found")
        
    creator_ids = [s.creator_id for s in subscribtions]
    creators = session.exec(select(Channels).where(Channels.user_id.in_(creator_ids))).all()
    
    return {'Channels' : creators.channel_name}


@router.post('/like_dislike_comment')
def like_dislike_comment(comment_id : int, is_like : bool,
                         session: Session = Depends(get_session),
                         current_user : Users = Depends(get_current_user())):
    
    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator") 
    
    comment = session.get(Comments, comment_id)
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "Comment not found")
        
    if comment.is_like == is_like:
        state = "like" if is_like else "dislike"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = f"You have already {state}d this comment")
        
    if is_like:
        comment.is_like = True
    else:
        comment.is_like = False
    session.commit()
    state = "liked" if is_like else "disliked"
    
    send_push_notifications(session, comment.user_id, f"{current_user.name} just {state} your comment")
    
    return {'message' : f'Comment {state} successfully'}


@router.post('/file_complaint')
async def file_a_complaint(subject : str = Form(),
                    issue: str = Form(),
                    session: Session = Depends(get_session),
                    current_user : Users = Depends(get_current_user())):
    
    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")
    
    admins = session.exec(select(Users).where(Users.role == "admin")).all()
    
    complain = Complain(    
        user_id = current_user.id,
        subject = subject,
        issue = issue,
        status = "pending",
        created_at = datetime.utcnow()
    )
    
    session.add(complain)
    session.commit()
    session.refresh(complain)
    
    email = current_user.email
    if email in active_connections:
        asyncio.create_task(
            send_notification(
                email,
                "Your complain has been submitted successfully. We will get back to you shortly"
            )
        )
    
    for admin in admins:
        send_push_notifications(session, admin.user_id, f"{current_user.name} just filed a complaint")
    
    return {'message' : 'Your complaint has been filed successfully, we will get back to you soon.'}


@router.get('/your_complaints')
def see_your_complaints_status(session: Session = Depends(get_session),
                         current_user : Users = Depends(get_current_user())):
    
    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")
    
    complaints = session.exec(select(Complain).where(Complain.user_id == current_user.id)).all()
    if not complaints:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "No complaints found")
        
    return {'complaints' : complaints}

@router.post('/toggle_comments')
async def toggle_comments(video_id : int,
                     enable : bool,
                     session: Session = Depends(get_session),
                     current_user : Users = Depends(get_current_user())):
    
    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")
        
    query = session.exec(select(Videos).where(Videos.id == video_id)).first()
    if not query:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND,
                            detail = f"Video with id {video_id} not found")
    
    query.disable_comments = enable
    session.commit()
    state = "enabled" if enable else "disabled"
    
    email = current_user.email
    if email in active_connections:
        asyncio.create_task(
            send_notification(
                email,
                f"Comments have been {state} for your video"
            )
        )
    
    return {"message": f"Comments {state} for this video"}

@router.get('/get_subscribers')
def get_subscribers(session: Session = Depends(get_session),
                    current_user : Users = Depends(get_current_user())):
    
    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")    
    
    query = session.exec(select(Subscription).where(Subscription.creator_id == current_user.id)).all()
    if not query:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND,
                            detail = "No subscribers found")
    
    subscribers_id = [s.user_id for s in query]    
    subscribers = session.exec(select(Users).where(Users.id.in_(subscribers_id))).all()
    
    return {"subscribed accounts" : subscribers.name, "total_subscribers" : len(subscribers)}

    
@router.get('/analytics')  
def analytics(
                session: Session = Depends(get_session),
                current_user : Users = Depends(get_current_user())):
    
    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")
        
    get_analytics = session.exec(select(Analytics).where(Analytics.creator_id == current_user.id)).all()
    
    if not get_analytics:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND,
                            detail = "No analytics data found")
        
    return {'analytics' : get_analytics}

@router.get('/see_history')
def see_history(session: Session = Depends(get_session),
                 current_user : Users = Depends(get_current_user())):
    
    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")
        
    history = session.exec(select(History).where(History.user_id == current_user.id)).all()
    if not history:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND,
                            detail = "No history found")
        
    return {'history' : history}

# delete account & history
@router.delete('/delete_creator_account')
async def delete_account(
    session : Session = Depends(get_session),
    current_user : Users = Depends(get_current_user())):

    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a creator")
            
    user = session.get(Users, current_user.id)
    
    
    history = session.exec(select(History).where(History.user_id == current_user.id)).all()
    comments = session.exec(select(Comments).where(Comments.user_id == current_user.id)).all()
    comments_id = [c.id for c in comments]
    
    replies = session.exec(select(Comments).where(Comments.parent_comment_id.in_(comments_id))).all()
    reports = session.exec(select(Reports).where(Reports.reporter_id == current_user.id)).all()
    like_dislike = session.exec(select(LikesDislikes).where(LikesDislikes.user_id == current_user.id)).all()
    requests = session.exec(select(Requests).where(Requests.user_id == current_user.id)).all()
    channels = session.exec(select(Channels).where(Channels.creator_id == current_user.id)).all()
    watch_videos = session.exec(select(WacthVideos).where(WacthVideos.user_id == current_user.id)).all()
    complains = session.exec(select(Complain).where(Complain.user_id == current_user.id)).all()
    subscribe = session.exec(select(Subscription).where(Subscription.user_id == current_user.id)).all()
    link = session.exec(select(SubscriptionLink).where(SubscriptionLink.user_id == current_user.id)).all()
    analytics = session.exec(select(Analytics).where(Analytics.creator_id == current_user.id)).all()
    trending = session.exec(select(Trending).where(Trending.creator_id == current_user.id)).all()
     
    for obj in (comments + replies + subscribe + link + watch_videos + requests + complains
                + reports + like_dislike + history + analytics + trending):
        session.delete(obj)
        
    session.delete(user)
    session.commit()
    
    email = current_user.email
    if email in active_connections:
        asyncio.create_task(
            send_notification(
                email,
                "Your account has been deleted"
            )
        )
    return {'message' : 'Account deleted'}


@router.delete('/delete_history')
async def delete_history(
    session : Session = Depends(get_session),
    current_user : Users = Depends(get_current_user())):
    
    if current_user.role != "creator":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail = "You are not a creator")
        
    history = session.exec(select(History).where(History.user_id == current_user.id)).all()
    session.delete(history)
    session.commit()
    
    email = current_user.email
    if email in active_connections:
        asyncio.create_task(
            send_notification(
                email,
                "Your history has been deleted"
            )
        )
    
    return {'message' : 'history deleted successfully'}   

@router.get('/trending_videos')
def see_your_trending_videos(
    session : Session = Depends(get_session),
    current_user : Users = Depends(get_current_user())):
    
    query = session.exec(select(Trending).where(Trending.creator_id == current_user.id))

async def send_notification(email:str, message:str):
    #print(f"Sending notification to {email}: {message}")
    if email in active_connections:
        await active_connections[email].send_json({
            "message": message
        })        