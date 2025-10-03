from fastapi import APIRouter, Depends, HTTPException, status, Form
from oauth2.jwt_hashing import get_current_user
from sqlmodels.tables_schema import Users, Videos, Reports, WacthVideos, Analytics, Subscription,LikesDislikes, Comments, Complain, Channels, Requests
from sqlmodel import Session, select, func, desc
from database.structure import get_session
from datetime import timedelta, datetime
from typing import Optional
from ws_router.websockets import active_connections
import asyncio
from push_notify.push_func import send_push_notifications

router = APIRouter(
    tags=['Admin']
)

@router.get('/see_trending')
def see_trending(session:Session = Depends(get_session), 
                 current_user : Users = Depends(get_current_user())):
    
    query = (select(WacthVideos.video_id, func.count(WacthVideos.id).label("video_count")
             ).group_by(WacthVideos.video_id).order_by(desc("video_count")
                                                      ).limit(10))
    
    result = session.exec(query).all()
    video_id = [r.video_id for r in result]
    trending_videos = session.exec(select(Videos).where(Videos.id.in_(video_id))).all()
    
    return trending_videos
    
    
@router.get('/view_reports')
def get_reports(session: Session = Depends(get_session),
                current_user : Users = Depends(get_current_user())):
    
    query = session.exec(select(Reports)).all()
    if not query:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND,
                            detail = "No reports filed")
    
    return query

#  APPLY NOTIFICATIONS
@router.put('/ban_or_suspend_user')
async def perform_ban_suspension(user_id : int, ban : bool = False, suspended_days : int = 0,
                           session : Session = Depends(get_session),
                           current_user : Users = Depends(get_current_user())):
    
    query = session.exec(select(Users).where(Users.id == user_id)).first()
    if not query:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND,
                          detail = "User not found")
        
    if ban == True:
        query.is_banned = True
        query.suspended_until = None
    
    elif  suspended_days > 0:
        query.is_banned = False
        query.suspended_until = datetime.utcnow() + timedelta(days=suspended_days)
      
    session.add(query)
    session.commit()
        
    state = "banned" if ban else "suspended"    
        
    email = current_user.email
    if email in active_connections:
        asyncio.create_task(
            send_notification(
                email,
                f"User has been {state}"
            )
        )    
    
    send_push_notifications(session, query.id, f"Your account has been {state} due to constant reports filed against you")
    
    return {'message' : 'User has been sanctioned'}    

#  APPLY NOTIFICATIONS
@router.delete('/delete_videos')
async def delete_video(video_id : int,
                 session:Session = Depends(get_session),
                 current_user : Users = Depends(get_current_user())):
    
    query = session.exec(select(Videos).where(Videos.id == video_id)).first()
    if not query:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND,
                            detail = f"Video with id {video_id} not found")
        
    session.delete(query)
    session.commit()    
    
    email = current_user.email
    if email in active_connections:
        asyncio.create_task(
            send_notification(
                email,
                "Your report has been submitted successfully"
            )
        )

    send_push_notifications(session, query.creator_id, "Your video has been taken down as it didnt follow our platform's guidelines")
    return {'message' : 'Video has been deleted'}

#  APPLY NOTIFICATIONS
@router.put('/copyright_strike')
def copyright(video_id : int,
                 session:Session = Depends(get_session),
                 current_user : Users = Depends(get_current_user())):
    
    query = session.exec(select(Videos).where(Videos.id == video_id)).first()
    if not query:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND,
                            detail = f"Video with id {video_id} not found")
    
    query.copyright_flag = True
    
    session.add(query)
    session.commit()

    send_push_notifications(session, query.creator_id, f"Your {query.title} video violates our copyright policies")

    return {'message' : 'Video has been copyrighted'}


@router.get('/view_analytics')
def view_analytics(session: Session = Depends(get_session),
                   current_user : Users = Depends(get_current_user())):    
        
    get_analytics = session.exec(select(Analytics)).all()
    return {'analytics' : get_analytics}    


@router.get('/view_users')
def view_users(session: Session = Depends(get_session),
                   current_user : Users = Depends(get_current_user())):    
        
    get_users = session.exec(select(Users).where(Users.role == "user")).all()
    return {'users' : get_users}


@router.get('/view_creators')
def view_creators(session: Session = Depends(get_session),
                  current_user : Users = Depends(get_current_user())):
    
    get_creators = session.exec(select(Users).where(Users.role == "creator")).all()
    return {'creators' : get_creators}


@router.get('/view_channels')
def view_channels(session: Session = Depends(get_session),
                  current_user : Users = Depends(get_current_user())):
    
    get_channels = session.exec(select(Channels)).all()
    
    return {'channels' : get_channels}


@router.get('/see_complains')
def see_complains(session: Session = Depends(get_session),
                  current_user : Users = Depends(get_current_user())):
    
    get_complains = session.exec(select(Complain)).all()
    return {'complains' : get_complains}

@router.put('/resolve_complain')
def resolve_complain(complain_id : int, 
                     session: Session = Depends(get_session),
                     current_user : Users = Depends(get_current_user())):
    
    complaint = session.get(Complain, complain_id)
    if not complaint:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND,
                            detail="Complain not found")
    complaint.status = "resolved"
    session.commit()
    
    return {'message' : 'Complain status updated'}   

@router.put('/resolve_report')
def take_action_on_reports(report_id : int, action : str = Form(...),
                           session: Session = Depends(get_session),
                           current_user : Users = Depends(get_current_user())):
    
    report = session.get(Reports, report_id)
    if not report:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND,
                            detail="Report not found")
    if not action:
        raise HTTPException(status_code = status.HTTP_400_BAD_REQUEST,
                            detail="Action is required")

    send_push_notifications(session, report.reporter, "Required actions have been taken based on your report")

    report.action_taken = action
    session.commit()
    
    return {'message' : 'Report action updated'}


@router.get('/see_requests')
def see_channel_requests(session: Session = Depends(get_session),
                         current_user : Users = Depends(get_current_user())):
    
    requests = session.exec(select(Requests).where(Requests.status == "pending")).all()
    if not requests:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND,
                            detail="No pending requests")
        
    return {'requests' : requests}


@router.put('/approve_or_reject_request')
def approve_reject_request(request_id : int, approval : bool,
                            session: Session = Depends(get_session),
                            current_user : Users = Depends(get_current_user())):
     
    request = session.get(Requests, request_id)
    if not request:
          raise HTTPException(status_code = status.HTTP_404_NOT_FOUND,
                             detail="Request not found")
     
    if not approval:
          request.status = "rejected"
          request.is_accepted = False
          
    request.status = "approved"
    request.is_accepted = True
    
    session.commit()
    
    state = "approved" if approval else "rejected"
    send_push_notifications(session, request.user_id, f"Your request to become a creator has been {state}")    
    
    
    return {'message' : 'Request status updated'}

@router.post('/admin_play_video')
def play_video(video_id : int, 
               session: Session = Depends(get_session),
               current_user : Users = Depends(get_current_user())):
    
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not na admin")
    
    video = session.get(Videos, video_id)
    if not video or video.status != "available":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "Video not found or not available")
            
    return video

@router.post('/admin_pause_video')
def pause_video(video_id : int, 
               session: Session = Depends(get_session),
               current_user : Users = Depends(get_current_user())):
      
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not an admin")      
      
    video = session.get(Videos, video_id)
    if not video or video.status != "available":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "Video not found or not available")
    
    return {"message": "Video paused"} 
        
@router.post('/admin_resume_video')
def resume_video(video_id : int, 
               session: Session = Depends(get_session),
               current_user : Users = Depends(get_current_user())):

    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not an admin")

    video = session.get(Videos, video_id)
    if not video or video.status != "available":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "Video not found or not available")
 
    session.commit()    
    
    return {"message": "Video resumed"}  
    
@router.post('/admin_end_video')
def end_video(video_id : int,
               session: Session = Depends(get_session),
               current_user : Users = Depends(get_current_user())):
      
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = "You are not an admin")      
      
    video = session.get(Videos, video_id)
    if not video or video.status != "available":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "Video not found or not available")

    return {"message": "Video ended"} 

async def send_notification(email:str, message:str):
    #print(f"Sending notification to {email}: {message}")
    if email in active_connections:
        await active_connections[email].send_json({
            "message": message
        })     