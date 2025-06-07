import os
import uuid
import tempfile
import random
import shutil
import glob
import time
from django.shortcuts import render
from django.core.cache import cache
from django.http import JsonResponse
import yt_dlp
from moviepy.editor import VideoFileClip, CompositeVideoClip
from moviepy.audio.fx.volumex import volumex

def make_progress_hook(task_id):
    def hook(d):
        cache.set(f'dl_progress_{task_id}', d, timeout=600)
    return hook

def cleanup_old_shorts(folder='media/shorts', max_age_hours=24):
    now = time.time()
    cutoff = now - max_age_hours * 3600
    for filename in os.listdir(folder):
        filepath = os.path.join(folder, filename)
        if os.path.isfile(filepath):
            if os.path.getmtime(filepath) < cutoff:
                try:
                    os.remove(filepath)
                except Exception as e:
                    print(f"Could not delete {filepath}: {e}")

def download_video(url, task_id, output_dir='media/shorts', clip_length=30):
    cleanup_old_shorts(output_dir, max_age_hours=24)
    temp_dir = output_dir or tempfile.mkdtemp()
    # Make output template UNIQUE for each download
    outtmpl = os.path.join(temp_dir, f'{task_id}_%(title)s.%(ext)s')
    # Get video info for random start
    info_dict = yt_dlp.YoutubeDL().extract_info(url, download=False)
    duration = info_dict.get('duration', 60)
    if duration > clip_length:
        start = random.randint(0, duration - clip_length)
    else:
        start = 0
    ydl_opts = {
        'outtmpl': outtmpl,
        'format': 'bestvideo[height=720]+bestaudio/best[height=720]',
        'merge_output_format': 'mp4',
        'quiet': True,
        'noplaylist': True,
        'progress_hooks': [make_progress_hook(task_id)],
        'download_sections': f"*{start}-{start+clip_length}",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    # Only return files with THIS task_id in their name (safety!)
    mp4_files = sorted(
        [f for f in glob.glob(os.path.join(temp_dir, '*.mp4')) if task_id in os.path.basename(f)],
        key=os.path.getmtime, reverse=True
    )
    if not mp4_files:
        raise Exception("Download failed: No MP4 file found.")
    return mp4_files[0], temp_dir

def create_short_from_random_timestamp(video_path, output_path, clip_length=30):
    target_width, target_height = 720, 1280
    clips = []
    temp_video_path = os.path.join(output_path, f'temp_{uuid.uuid4()}.mp4')
    shutil.copy(video_path, temp_video_path)
    video = VideoFileClip(temp_video_path)
    duration = int(video.duration)
    try:
        start = 0 if duration <= clip_length else random.randint(0, duration - clip_length)
        end = min(start + clip_length, duration)
        subclip = video.subclip(start, end)
        if subclip.audio:
            def stereo_imbalance(get_frame, t):
                frame = get_frame(t)
                if frame.ndim == 2 and frame.shape[1] == 2:
                    frame[:, 0] *= 0.85
                    frame[:, 1] *= 1.05
                return frame
            audio = subclip.audio.fl(stereo_imbalance)
            audio = volumex(audio, 0.9)
            subclip = subclip.set_audio(audio)
        resized = subclip.resize(width=target_width)
        final = CompositeVideoClip(
            [resized.set_position(("center", "center"))],
            size=(target_width, target_height)
        )
        short_id = str(uuid.uuid4())
        output_file = os.path.join(output_path, f'short_{short_id}.mp4')
        final.write_videofile(
            output_file,
            codec="libx264",
            audio_codec="aac",
            fps=24,
            threads=4,
            logger=None
        )
        clips.append(f'/media/shorts/short_{short_id}.mp4')
        subclip.close()
        final.close()
    finally:
        video.close()
        # Always delete temp
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)
    return clips

def home(request):
    if request.method == "POST":
        url = request.POST.get("url")
        task_id = request.POST.get("task_id") or str(uuid.uuid4())
        os.makedirs('media/shorts', exist_ok=True)
        try:
            video_path, _ = download_video(url, task_id, output_dir='media/shorts')
            short_clips = create_short_from_random_timestamp(video_path, 'media/shorts')
            # DELETE original downloaded video (not short)
            if os.path.exists(video_path):
                try:
                    os.remove(video_path)
                except Exception as cleanup_err:
                    print(f"Failed to delete original video: {cleanup_err}")
            return JsonResponse({
                "success": True,
                "short_url": short_clips[0],
                "task_id": task_id,
            })
        except Exception as e:
            return JsonResponse({
                "success": False,
                "msg": f"Error: {str(e)}"
            })
    return render(request, 'core/home.html')

def download_progress(request):
    task_id = request.GET.get('task_id')
    data = cache.get(f'dl_progress_{task_id}', {})
    return JsonResponse(data)
