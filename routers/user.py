from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, Form
from oauth2.jwt_hashing import get_current_user
from sqlmodels.tables_schema import Users, Videos, Reports, UpdateVideo,Trending, Comments, Requests,WacthVideos, History,Subscription, SubscriptionLink, Notificaions, LikesDislikes, Analytics, Channels, Complain
from sqlmodel import Session, select, func, desc, delete
from database.structure import get_session
from datetime import timedelta, datetime, date
from typing import Optional
from ws_router.websockets import active_connections
import asyncio
from push_notify.push_func import send_push_notifications

router = APIRouter(
    tags=['User']
)
@router.post('/become_a_creator')
async def become_a_creator(description : str = Form(...), 
                     session: Session = Depends(get_session),
                     current_user : Users = Depends(get_current_user())):
    
    if current_user.role != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are already a creator")
        
    create_request = Requests(
        
        user_id = current_user.id,
        request_type = "Become a creator",
        description = description,
        status = "pending",
        is_accepted = None,
        created_at = datetime.utcnow()
    )
    
    session.add(create_request)
    session.commit()
    session.refresh(create_request)
    
    email = current_user.email
    if email in active_connections:
        asyncio.create_task(
            send_notification(
                email,
                "Your request has been sent you will be notified soon. Thankyou!"
            )
        )
    
    return {
    'message' : 'Your request to become a creator has been submitted for review,You will be notified.'}
    
    
@router.post('/create_channel')
async def create_channel(channel_name : str = Form(...), content_type : str = Form(...),
                     session: Session = Depends(get_session),
                     current_user : Users = Depends(get_current_user())):
    
    if current_user.role != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are already a creator")

    approval = session.exec(select(Requests).where(Requests.user_id == current_user.id)).first()
    if not approval :
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "You haven't made arequest yet for a channel. Please make a request..")
    if  approval.is_accepted != True:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Your request to become a creator has been rejected.")
    
    update_status = session.get(Users, current_user.id)
    update_status.role = "creator"
    
    create_channel = Channels(
        
        creator_id = current_user.id,
        name = channel_name,
        content_type = content_type,
        created_at = datetime.utcnow()
    )

    session.add(create_channel)
    session.commit()
    session.refresh(create_channel)
    
    email = current_user.email
    if email in active_connections:
        asyncio.create_task(
            send_notification(
                email,
                "Congratulations you have officially created your channel"
            )
        )
    
    return {'message' : 'Channel created successfully'}    

@router.post('/user/play_video')
async def play_video(video_id : int, 
               session: Session = Depends(get_session),
               current_user : Users = Depends(get_current_user())):
    
    if current_user.role != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are already a creator")
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

@router.post('/user/pause_video')
async def pause_video(watch_id : int, 
               session: Session = Depends(get_session),
               current_user : Users = Depends(get_current_user())):
      
    if current_user.role != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are already a creator")      
      
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
        
@router.post('/user/resume_video')
async def resume_video(watch_id : int, 
               session: Session = Depends(get_session),
               current_user : Users = Depends(get_current_user())):

    if current_user.role != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are already a creator")

    timestamp = datetime.utcnow()  
    
    watch = session.get(WacthVideos, watch_id)
    
    if not watch :
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "Watch session not found")

    watch.last_stop = timestamp
 
    session.commit()    
    
    return {"message": "Video resumed"}  
    
@router.post('/user/end_video')
async def end_video(watch_id : int,
               session: Session = Depends(get_session),
               current_user : Users = Depends(get_current_user())):
      
    if current_user.role != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are already a creator")      
      
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

@router.get('/user/get_url')
def set_quality(video_id : int, quality : str,
            session: Session = Depends(get_session)):
    
    video = session.select(Videos).where(Videos.id == video_id).first()
    if quality == "1080p":
        return video.url_1080p
    elif quality == "720p":
        return video.url_720p
    elif quality == "480p":
        return video.url_480p
    elif quality == "360p":
        return video.url_360p
    elif quality == "144p":
        return video.url_144p
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Video not available in this quality")
        
@router.post('/user/subscribe')
async def subscribe(creator_id : int,
              session: Session = Depends(get_session),
              current_user : Users = Depends(get_current_user())):

    if current_user.role != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are already a creator")

    query = session.exec(select(Channels).where(Channels.creator_id == creator_id)).first()
    if not query:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "No creator or channel found")
    
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
    send_push_notifications(session, query.creator_id, f"{current_user.name} just subscribed to your channel")
    
    return {'message' : f'Subscribed to {query.name} successfully'}

@router.delete('/user/unsubscribe')
async def unsubscribe(creator_id : int,
                session: Session = Depends(get_session),
                current_user : Users = Depends(get_current_user())):
    
    if current_user.role != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are already a creator")    
    
    query = session.exec(select(Subscription).where(Subscription.creator_id == creator_id,
                            Subscription.user_id == current_user.id)).first()
    engagement = session.exec(select(Analytics).where(Analytics.creator_id == creator_id)).first()
    
    if not query or not engagement:
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
        
@router.post('/user/turn_off_notifications')
async def turn_off_notifications(creator_id : int, notify : bool = False,
                    session: Session = Depends(get_session),
                    current_user : Users = Depends(get_current_user())):

    if current_user.role != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are already a creator")

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
                f"Notifications turned off"
            )
        )
    return {'message' : 'Notification preference updated successfully'}

@router.get('/user/get_notifications')
def get_notifications(session: Session = Depends(get_session),
                        current_user : Users = Depends(get_current_user())):

    if current_user.role != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are already a creator")

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
    
@router.post('/user/comment')
async def post_comment(video_id : int, text : str = Form(),
                 session: Session = Depends(get_session),
                 current_user : Users = Depends(get_current_user())):

    if current_user.role != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are already a creator")

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

@router.post('/user/reply_comment')
async def reply_comment(video_id : int, parent_comment_id : int,
                  text : str = Form(), session: Session = Depends(get_session),
                    current_user : Users = Depends(get_current_user())):

    if current_user.role != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not authorised")
        
    query = session.exec(select(Comments).where(Comments.id == parent_comment_id)).first()
    if not query:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "Parent comment not found")
    
    comments = session.exec(select(Videos).where(Videos.id == video_id)).first()
    if comments.disable_comments == True:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail = "Comments are disabled for this video")
        

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
        
    session.commit()
    
    send_push_notifications(session, query.user_id, f"{current_user.name} just replied to your comment")
    return {'message' : 'Reply posted successfully'}

@router.delete('/user/delete_comment')
async def delete_comment(comment_id : int, creator_id : int,
                   video_id,
                   session: Session = Depends(get_session),
                   current_user : Users = Depends(get_current_user())):

    if current_user.role != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are already a creator")

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

@router.post('/user/report_video')
async def report_video(video_id : int, report : str = Form(),
                 session: Session = Depends(get_session),
                 current_user : Users = Depends(get_current_user())):

    if current_user.role != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are already a creator")
        
    admins = session.exec(select(Users).where(Users.role == "admin")).all()
    
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
    for admin in admins:
            send_push_notifications(session, admin.user_id, f"{current_user.name} just reported a video")
            
    return {'message' : 'Video reported successfully'}


@router.post('/user/report_comment')
async def report_comment(
                    comment_id : int, report : str = Form(),
                    session: Session = Depends(get_session),
                    current_user : Users = Depends(get_current_user())):
  
     if current_user.role != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are already a creator")    

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
            send_push_notifications(session, admin.user_id, f"{current_user.name} just reported a video")    
     return {'message' : 'Comment reported successfully'}
 

    
@router.post('/user/like_dislike') 
async def like_dislike(video_id : int, is_like : bool ,
                 session: Session = Depends(get_session),
                 current_user : Users = Depends(get_current_user())):
    
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
    
    state = "liked" if is_like else "disliked"
    
    send_push_notifications(session, video.creator_id, f"{current_user.name} just {state} your video") 
    return {'message' : f'Video {state} successfully'}


@router.get('/user/liked_videos')
async def liked_videos(session: Session = Depends(get_session),
                current_user : Users = Depends(get_current_user())):
        
    if current_user.role != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are already a creator")        
        
    liked = session.exec(select(LikesDislikes).where(LikesDislikes.user_id == current_user.id,
                            LikesDislikes.is_like == True)).all()
    if not liked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail= "No liked videos found")
        
    liked_videos_id = [l.video_id for l in liked]     
        
    liked_videos = session.exec(select(Videos).where(Videos.id.in_(liked_videos_id))).all()
    return {'liked_videos' : liked_videos}
    
   
@router.get('/user/your_subscriptions')    
async def your_subscribtions(session: Session = Depends(get_session),
                      current_user : Users = Depends(get_current_user())):
    
    if current_user.role != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are already a creator")    
    
    subscribtions = session.exec(select(Subscription).where(Subscription.user_id == current_user.id)).all()
    if not subscribtions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "No subscribtions found")
        
    creator_ids = [s.creator_id for s in subscribtions]
    creators = session.exec(select(Channels).where(Channels.user_id.in_(creator_ids))).all()
    
    return {'Channels' : creators.channel_name}

@router.post('/user/like_dislike_comment')
async def like_dislike_comment(comment_id : int, is_like : bool,
                         session: Session = Depends(get_session),
                         current_user : Users = Depends(get_current_user())):
    
    if current_user.role != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are already a creator")    
    
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

@router.post('/user/file_complaint')
async def file_a_complaint(subject : str = Form(),
                    issue: str = Form(),
                    session: Session = Depends(get_session),
                    current_user : Users = Depends(get_current_user())):
    
    if current_user.role != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are already a creator")
        
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
                "Your complain has been filed. You will be informed shortly"
            )
        )
    
    for admin in admins:
            send_push_notifications(session, admin.id, f"{current_user.name} just filed a complaint")
    return {'message' : 'Your complaint has been filed successfully, we will get back to you soon.'}

@router.get('/user/your_complaints')
async def see_your_complaints_status(session: Session = Depends(get_session),
                         current_user : Users = Depends(get_current_user())):
    
    if current_user.role != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are already a creator")
    
    complaints = session.exec(select(Complain).where(Complain.user_id == current_user.id)).all()
    if not complaints:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "No complaints found")
        
    return {'complaints' : complaints}

@router.get('/user/see_history')
async def see_history(session: Session = Depends(get_session),
                 current_user : Users = Depends(get_current_user())):
    
    if current_user.role != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a user")
        
    history = session.exec(select(History).where(History.user_id == current_user.id)).all()
    if not history:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND,
                            detail = "No history found")
        
    return {'history' : history}

#delete account & history
@router.delete('/user/delete_account')
async def delete_account(session: Session = Depends(get_session),
                   current_user : Users = Depends(get_current_user())):
    
    if current_user.role != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not a user")    
    
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
  
    for c in comments:
        analytics = session.exec(select(Analytics).where(Analytics.video_id == c.video_id)).first()
        if analytics:
            analytics.comments -= 1
    
    for r in replies:
        analytics = session.exec(select(Analytics).where(Analytics.video_id == r.video_id)).first()
        if analytics:
            analytics.comments -= 1
    for l in like_dislike:
        analytics = session.exec(select(Analytics).where(Analytics.video_id == l.video_id)).first()
        if analytics:
            if l.is_like == True:
                analytics.likes -= 1
            else:    
                analytics.dislikes -= 1
    
    for v in watch_videos:
        analytics = session.exec(select(Analytics).where(Analytics.video_id == v.video_id)).first()
        if analytics:
            analytics.views -= 1
            analytics.watch_time -= v.duration
        
    for sub in subscribe:
     analytics = session.exec(select(Analytics).where(Analytics.creator_id == sub.creator_id)).first()
     if analytics:
        analytics.subscriber -= 1
     
    for obj in (comments + replies + subscribe + link + watch_videos + requests + complains
                + reports + like_dislike + history):
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
    
    return {'message' : 'acount deleted'}


@router.delete('/user/delete_history')
async def delete_history(
    session : Session = Depends(get_session),
    current_user : Users = Depends(get_current_user())):
    
    if current_user.role != "user":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail = "Only users are allowed to delete their history")
        
    history = session.exec(select(History).where(History.user_id == current_user.id)).all()
    if not history:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND,
                            detail = "No history found")
    session.delete(history)
    session.commit()
    
    email = current_user.email
    if email in active_connections:
        asyncio.create_task(
            send_notification(
                email,
                "Your report has been submitted successfully"
            )
        )
    
    return {'message' : 'history deleted successfully'}    


@router.get('/trending_videos')
def see_trending(
            session : Session = Depends(get_session),
            current_user : Users = Depends(get_current_user())):
    
    query = session.exec(select(Trending)).all()
    
    return query

async def send_notification(email:str, message:str):
    #print(f"Sending notification to {email}: {message}")
    if email in active_connections:
        await active_connections[email].send_json({
            "message": message
        })       
        
        