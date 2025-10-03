
# import subprocess
# import boto3
# from .celery import celery_app
# from sqlmodel import Session, select
# from database.structure import engine
# from sqlmodels.tables_schema import Videos
# import os
# import tempfile

# s3 = boto3.client('s3')

# RESOLUTIONS = {
#     "1080p": ("1920x1080", "url_1080p"),
#     "720p": ("1280x720", "url_720p"),
#     "480p": ("854x480", "url_480p"),
#     "360p": ("640x360", "url_360p"),
#     "144p": ("256x144", "url_144p")
# }



# @celery_app.task(bind=True, max_retries=3)
# def process_video(self, file_key: str, bucket: str, video_id: int):
#     temp_output = []
#     thumbnail_path = None  # Initialize

#     # Use NamedTemporaryFile and immediately close it for Windows
#     with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_input:
#         local_input = temp_input.name
#     temp_input.close()  # <-- important on Windows

#     try:
#         session = Session(engine)

#         # Download from S3
#         s3.download_file(bucket, file_key, local_input)
#         # Check if file downloaded properly
#         if os.path.getsize(local_input) == 0:
#             raise ValueError(f"Downloaded file {local_input} is empty")

        
#         input_height = get_video_quality(local_input)


#         valid_resolution = {
#             name: (size, db_field)
#             for name, (size, db_field) in RESOLUTIONS.items()
#             if int(size.split("x")[1]) <= input_height
#         }
#         print("RESOLUTIONS:", RESOLUTIONS)
#         print("valid_resolution:", valid_resolution)
#         if not valid_resolution:
#             raise ValueError("No valid resolution for this input")

#         for name, (size, db_field) in valid_resolution.items():
#             with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_out:
#                 local_output = temp_out.name
#             temp_out.close()  # <-- important on Windows
#             temp_output.append(local_output)

#             processed_key = f"processed/{name}_{file_key}"

#             with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_thumb:
#                 thumbnail_path = temp_thumb.name
#             temp_thumb.close()  # <-- important on Windows

#             # Convert video
#             cmd = [
#                 "ffmpeg",
#                 "-i", local_input,
#                 "-s", size,
#                 "-c:a", "copy",
#                 local_output
#             ]
#             subprocess.run(cmd, check=True)

#             # Upload processed video
#             with open(local_output, "rb") as f:
#                 s3.upload_fileobj(f, bucket, processed_key, ExtraArgs={"ACL": "public-read"})

#             public_url = f"https://{bucket}.s3.amazonaws.com/{processed_key}"
#             video = session.get(Videos, video_id)
#             setattr(video, db_field, public_url)

#         # Create thumbnail
#         cmd_thumbnail = [
#             "ffmpeg",
#             "-i", local_input,
#             "-ss", "00:00:02.000",
#             "-vframes", "1",
#             thumbnail_path
#         ]
#         subprocess.run(cmd_thumbnail, check=True)

#         thumb_key = f"thumbnail/{video_id}.jpg"
#         with open(thumbnail_path, "rb") as thumb_file:
#             s3.upload_fileobj(thumb_file, bucket, thumb_key, ExtraArgs={"ACL": "public-read"})

#         video.thumbnail_url = f"https://{bucket}.s3.amazonaws.com/{thumb_key}"

#         if hasattr(video, "status"):
#             video.status = "completed"

#         video.status = "complete"
#         session.commit()


#     except Exception as e:
#         raise self.retry(exc=e, countdown=30)

#     finally:
#         if session:
#             session.close()

#         # Cleanup all temp files
#         if os.path.exists(local_input):
#             os.remove(local_input)
#         for output_file in temp_output:
#             if os.path.exists(output_file):
#                 os.remove(output_file)
#         if thumbnail_path and os.path.exists(thumbnail_path):
#             os.remove(thumbnail_path)

#     return "Processing complete"

import subprocess
import boto3
from .celery import celery_app
from sqlmodel import Session
from database.structure import engine
from sqlmodels.tables_schema import Videos, Users
import os
import tempfile
import shutil
from sqlmodel import Session, select, func, desc
from .server import download_from_s3
from ws_router.websockets import active_connections
import asyncio
s3 = boto3.client("s3")

# Resolutions for HLS (resolution: (scale, video_bitrate))
HLS_RESOLUTIONS = {
    "1080p": ("1920x1080", "5000k"),
    "720p": ("1280x720", "3000k"),
    "480p": ("854x480", "1500k"),
    "360p": ("640x360", "800k"),
    "144p": ("256x144", "400k"),
}

AUDIO_BITRATE = "128k"  # Encode audio once

import shutil

@celery_app.task
def process_video(file_key: str, bucket: str, video_id: int):
    bucket = "my-fastapi-videos"
    workdir = tempfile.mkdtemp()
    hls_dir = os.path.join(workdir, "hls")
    os.makedirs(hls_dir, exist_ok=True)

    try:
        # open SQLModel session
        with Session(engine) as session:
            video = session.get(Videos, video_id)
            if not video:
                return f"Video {video_id} not found"

            # download input
            local_input = download_from_s3(video.original_url, workdir)

            renditions = {}
            # Audio only
            audio_out = os.path.join(hls_dir, "audio.m3u8")
            cmd_audio = [
                "ffmpeg", "-i", local_input,
                "-c:a", "aac", "-b:a", AUDIO_BITRATE,
                "-vn",
                "-f", "hls",
                "-hls_time", "6",
                "-hls_playlist_type", "vod",
                "-hls_segment_filename", f"{hls_dir}/audio_%03d.ts",
                audio_out
            ]
            subprocess.run(cmd_audio, check=True)

            # Video renditions
            for name, (scale, v_bitrate) in HLS_RESOLUTIONS.items():
                video_out = os.path.join(hls_dir, f"{name}.m3u8")
                cmd_video = [
                    "ffmpeg", "-i", local_input,
                    "-vf", f"scale={scale}",
                    "-c:v", "h264", "-profile:v", "main",
                    "-crf", "20", "-sc_threshold", "0",
                    "-g", "48", "-keyint_min", "48",
                    "-b:v", v_bitrate,
                    "-maxrate", v_bitrate,
                    "-bufsize", str(int(v_bitrate.replace("k", "")) * 2) + "k",
                    "-an",
                    "-f", "hls",
                    "-hls_time", "6",
                    "-hls_playlist_type", "vod",
                    "-hls_segment_filename", f"{hls_dir}/{name}_%03d.ts",
                    video_out
                ]
                subprocess.run(cmd_video, check=True)
                renditions[name] = f"https://{bucket}.s3.amazonaws.com/hls/{video_id}/{name}.m3u8"

            # Master playlist
            master_playlist = os.path.join(hls_dir, "master.m3u8")
            with open(master_playlist, "w") as m3u8:
                m3u8.write("#EXTM3U\n#EXT-X-VERSION:3\n")
                m3u8.write('#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="English",DEFAULT=YES,AUTOSELECT=YES,URI="audio.m3u8"\n')
                for name, (scale, v_bitrate) in HLS_RESOLUTIONS.items():
                    bw = int(v_bitrate.replace("k", "")) * 1000 + 128000
                    w, h = scale.split("x")
                    m3u8.write(
                        f'#EXT-X-STREAM-INF:BANDWIDTH={bw},RESOLUTION={w}x{h},CODECS="avc1.4d401f,mp4a.40.2",AUDIO="audio"\n{name}.m3u8\n'
                    )

            # Upload all HLS files
            for root, _, files in os.walk(hls_dir):
                for file in files:
                    path = os.path.join(root, file)
                    key = f"hls/{video_id}/{file}"
                    with open(path, "rb") as f:
                        s3.upload_fileobj(f, bucket, key, ExtraArgs={"ACL": "public-read"})

            # Thumbnail
            thumbnail_path = os.path.join(workdir, "thumbnail.jpg")
            subprocess.run([
                "ffmpeg", "-i", local_input,
                "-ss", "00:00:02.000", "-vframes", "1", thumbnail_path
            ], check=True)

            thumb_key = f"thumbnail/{video_id}.jpg"
            with open(thumbnail_path, "rb") as thumb_file:
                s3.upload_fileobj(thumb_file, bucket, thumb_key, ExtraArgs={"ACL": "public-read"})

            # Update DB fields
            video.hls_url = f"https://{bucket}.s3.amazonaws.com/hls/{video_id}/master.m3u8"
            video.thumbnail_url = f"https://{bucket}.s3.amazonaws.com/{thumb_key}"

            video.url_1080p = renditions.get("1080p")
            video.url_720p = renditions.get("720p")
            video.url_480p = renditions.get("480p")
            video.url_360p = renditions.get("360p")
            video.url_144p = renditions.get("144p")

            video.status = "complete"
            session.add(video)
            session.commit()
            query = session.exec(select(Users).where(Users.id == video.creator_id)).first()
            email = query.email
            if email in active_connections:
                asyncio.create_task(
                    send_notification(
                        email,
                        "Your video has been uploaded successfully"
                    )
                )
        return "HLS processing complete"

    finally:

        shutil.rmtree(workdir, ignore_errors=True)

async def send_notification(email:str, message:str):
    #print(f"Sending notification to {email}: {message}")
    if email in active_connections:
        await active_connections[email].send_json({
            "message": message
        })  