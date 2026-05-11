from flask import Flask, render_template, request, send_file, jsonify
import yt_dlp
import os
import threading
import uuid
from pathlib import Path

app = Flask(__name__)
DOWNLOAD_FOLDER = Path("/tmp/downloads")
COOKIES_PATH = Path("/tmp/cookies.txt")
DOWNLOAD_FOLDER.mkdir(exist_ok=True)

progress = {}

@app.route('/info', methods=['POST'])
def get_video_info():
    url = request.form.get('url')
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        if COOKIES_PATH.exists():
            ydl_opts['cookiefile'] = str(COOKIES_PATH)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            formats = []
            seen = set()
            
            for f in info.get('formats', []):
                format_id = f.get('format_id')
                if format_id in seen:
                    continue
                seen.add(format_id)
                
                height = f.get('height') or 0
                ext = f.get('ext', 'mp4')
                
                # 优先显示有视频和音频的格式
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                    quality = f"{height}p" if height else f.get('format_note', '未知')
                    formats.append({
                        'itag': format_id,
                        'quality': quality,
                        'ext': ext,
                        'type': 'video'
                    })
            
            # 如果没找到，添加音频格式
            if not formats:
                formats.append({'itag': 'bestaudio', 'quality': '音频 (MP3)', 'ext': 'mp3', 'type': 'audio'})
            
            return jsonify({
                "success": True,
                "title": info.get('title', '未知标题'),
                "formats": formats[:20]
            })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

def download_task(url, format_id, task_id):
    try:
        progress[task_id] = {"status": "downloading", "percent": 0}

        ydl_opts = {
            'outtmpl': str(DOWNLOAD_FOLDER / '%(title)s.%(ext)s'),
            'progress_hooks': [lambda d: update_progress(d, task_id)],
            'quiet': True,
        }

        if COOKIES_PATH.exists():
            ydl_opts['cookiefile'] = str(COOKIES_PATH)

        if format_id == 'bestaudio':
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]
        else:
            ydl_opts['format'] = format_id

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            progress[task_id] = {
                "status": "finished", 
                "filename": os.path.basename(filename), 
                "path": filename
            }
    except Exception as e:
        progress[task_id] = {"status": "error", "error": str(e)}

def update_progress(d, task_id):
    if d['status'] == 'downloading' and d.get('total_bytes'):
        percent = (d['downloaded_bytes'] / d['total_bytes']) * 100
        progress[task_id]["percent"] = round(percent, 1)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload_cookies', methods=['POST'])
def upload_cookies():
    if 'cookies' not in request.files:
        return jsonify({"error": "没有上传文件"})
    file = request.files['cookies']
    if file.filename == '':
        return jsonify({"error": "没有选择文件"})
    file.save(COOKIES_PATH)
    return jsonify({"success": True, "message": "✅ Cookies 上传成功！"})

@app.route('/download', methods=['POST'])
def start_download():
    url = request.form.get('url')
    format_id = request.form.get('format_id')
    task_id = str(uuid.uuid4())
    
    thread = threading.Thread(target=download_task, args=(url, format_id, task_id))
    thread.daemon = True
    thread.start()
    
    return jsonify({"task_id": task_id})

@app.route('/progress/<task_id>')
def get_progress(task_id):
    return jsonify(progress.get(task_id, {"status": "not_found"}))

@app.route('/getfile/<task_id>')
def get_file(task_id):
    info = progress.get(task_id)
    if info and info.get("status") == "finished" and os.path.exists(info["path"]):
        return send_file(info["path"], as_attachment=True, download_name=info["filename"])
    return "文件未就绪", 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
