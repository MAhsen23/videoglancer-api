import base64
import os
import re
import shutil
from flask import Flask, request, jsonify
from flask_cors import CORS
import cv2
from pytubefix import YouTube
from fpdf import FPDF
from PIL import Image
import logging

app = Flask(__name__)
CORS(app, resources={r"/pdf": {"origins": "*"}})
logging.basicConfig(level=logging.INFO)

def sanitize_filename(file_name):
    return re.sub(r'[<>:"/\\|?*]', '_', file_name)

def extract_frames(video_path, output_folder, minutes):
    video_capture = cv2.VideoCapture(video_path)
    frame_rate = int(video_capture.get(cv2.CAP_PROP_FPS))
    total_frames = int(video_capture.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_interval = int((frame_rate * 60) * int(minutes))

    if frame_interval == 0:
        frame_interval = 1

    for i in range(0, total_frames, frame_interval):
        video_capture.set(cv2.CAP_PROP_POS_FRAMES, i)
        success, image = video_capture.read()

        if success:
            frame_path = os.path.join(output_folder, f'frame_{i}.jpg')
            cv2.imwrite(frame_path, image)
    video_capture.release()

def create_pdf_from_frames(output_folder):
    pdf = FPDF(format='A4')
    for root, _, files in os.walk(output_folder):
        image_files = [file for file in files if file.endswith('.jpg')]
        image_files.sort()

        for image_file in image_files:
            image_path = os.path.join(root, image_file)
            with Image.open(image_path) as img:
                img_width, img_height = img.size

            pdf_width, pdf_height = pdf.w, pdf.h
            scale = min(pdf_width / img_width, pdf_height / img_height)
            new_width = img_width * scale
            new_height = img_height * scale
            center_x = (pdf_width - new_width) / 2
            center_y = (pdf_height - new_height) / 2

            pdf.add_page()
            pdf.image(image_path, x=center_x, y=center_y, w=new_width, h=new_height)

    pdf_file_name = f'{output_folder}_frames.pdf'
    pdf.output(pdf_file_name)
    return pdf_file_name

@app.route('/pdf', methods=['GET'])
def convert_video_to_pdf():
    youtube_url = request.args.get('url')
    minutes = request.args.get('minutes', '1')
    
    if not youtube_url:
        return jsonify({'error': 'YouTube URL is required'}), 400
    try:
        minutes = int(minutes)
        if minutes <= 0 or minutes > 120:
            return jsonify({'error': 'Minutes should be between 1 and 120'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid minutes value'}), 400
    video_folder = None
    pdf_file = None

    try:
        yt = YouTube(youtube_url)
        video_length = yt.length / 60

        if video_length > 120:
            return jsonify({'error': 'Video length exceeds 120 minutes limit'}), 400

        sanitized_video_id = sanitize_filename(yt.video_id)
        video_folder = f'video_{sanitized_video_id}'
        os.makedirs(video_folder, exist_ok=True)

        video = yt.streams.filter(file_extension='mp4').first()
        if not video:
            return jsonify({'error': 'No downloadable video found'}), 404

        video_extension = video.mime_type.split('/')[-1]
        video_file_name = f'video.{video_extension}'
        video_path = os.path.join(video_folder, video_file_name)
        video.download(output_path=video_folder, filename=video_file_name)

        extract_frames(video_path, video_folder, minutes)
        pdf_file = create_pdf_from_frames(video_folder)

        with open(pdf_file, "rb") as f:
            pdf_base64 = base64.b64encode(f.read()).decode('utf-8')
        return jsonify({'pdf': pdf_base64, 'message': 'PDF created successfully'}), 200

    except Exception as e:
        logging.error(f"Error processing video: {str(e)}")
        return jsonify({'error': 'An error occurred while processing the video'}), 500

    finally:
        if video_folder and os.path.exists(video_folder):
            shutil.rmtree(video_folder)
        if pdf_file and os.path.exists(pdf_file):
            os.remove(pdf_file)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)