from flask import Flask, render_template, request, send_file, jsonify
import yt_dlp
import os
import threading
import uuid
from pathlib import Path

app = Flask(__name__)
DOWNLOAD_FOLDER = Path("/tmp/downloads")
DOWNLOAD_FOLDER.mkdir(exist_ok=True)

progress = {}

def download_task(url, fmt, task_id):
    try:
        progress[task_id] = {"status": "downloading", "percent": 0}

        output_template = DOWNLOAD_FOLDER / '%(title)s.%(ext)s'

        ydl_opts = {
            'outtmpl': str(output_template),
            'progress_hooks': [lambda d: update_progress(d, task_id)],
            'quiet': True,
        }

        if fmt == "audio":
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        else:
            ydl_opts['format'] = 'bestvideo+bestaudio/best'

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if fmt == "audio":
                filename = str(Path(filename).with_suffix('.mp3'))
            
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

@app.route('/download', methods=['POST'])
def start_download():
    url = request.form.get('url')
    fmt = request.form.get('format', 'video')
    task_id = str(uuid.uuid4())
    
    thread = threading.Thread(target=download_task, args=(url, fmt, task_id))
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
    return "文件未就绪或已过期", 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)