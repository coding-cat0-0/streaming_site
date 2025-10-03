from sqlmodels.tables_schema import WacthVideos, Videos, Trending
from .celery import celery_app
from sqlmodel import SQLModel, Session, func, select, desc
from database.structure import get_session , engine
import os
from fastapi import Depends
from push_notify.push_func import send_push_notifications

@celery_app.task()
def calculate_trending():
    
    with Session(engine) as session:
        # build subquery with score and totals
        subq = (
            select(
                WacthVideos.video_id,
                WacthVideos.creator_id,
                func.count(WacthVideos.id).label("view_count"),
                func.sum(WacthVideos.duration).label("total_duration"),
                (func.count(WacthVideos.id) + func.sum(WacthVideos.duration) / 60).label("score"),
            )
            .group_by(WacthVideos.video_id, WacthVideos.creator_id)
            .subquery()
        )

        # get max score
        max_score = select(func.max(subq.c.score))

        # select videos whose score >= 80% of max
        query = (
            select(subq)
            .where(subq.c.score >= 0.8 * max_score.scalar_subquery())
            .order_by(subq.c.score.desc())
        )

        results = session.exec(query).all()

        for video_id, creator_id, view_count, total_duration, score in results:
            video = session.exec(select(Videos).where(Videos.video_id == video_id)).first()
            if not video:
                continue

            trending = Trending(
                creator_id=creator_id,
                video=video.original_url,
                views=view_count,
                duration=total_duration,
            )

            send_push_notifications(
                session, creator_id, f"Congratulations! your {video.title} video is now trending"
            )

            session.add(trending)

        session.commit()

"""  
with Session(engine) as session:
        
        subq = session.exec(select(WacthVideos.video_id,
                            WacthVideos.creator_id,
                             func.count(WacthVideos.id).label("view_count"
                            ), func.sum(WacthVideos.duration)).label("total_duration"
                            ),(func.count(WacthVideos.id) + func.sum(WacthVideos.duration)/60).lable("score"
                            )).group_by(WacthVideos.video_id, WacthVideos.creator_id).order_by(desc("score"
                            ).subquery())
        max_score = select(func.max(subq.c.score))       # example highest score is 100
        query = (select(subq).where(subq.c.score >= 0.8 * max_score.scalar_subquery())) # 0.8 x 100 = 80  
        # use scalar_subquery() so that sql model doesnt confuse that we're mixing a table column with a query object        
        results = session.exec(query).all()
        
        for video_id , creator_id, view_count,total_duration, score in results:
            query = session.exec(select(Videos).where(Videos.video_id == video_id)).first()
            trending = Trending(
                creator_id = creator_id,
                video = query.original_url,
                views = view_count,
                duration = total_duration
            )
            send_push_notifications(session, creator_id, f"Congratulations! your {query.title} video is now trending")
            session.add(trending)
        session.commit() 
        """

    