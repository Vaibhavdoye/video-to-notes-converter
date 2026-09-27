import os
import re
import sqlite3
import speech_recognition as sr
from flask import Flask, render_template, request, jsonify
from moviepy import VideoFileClip
from pydub import AudioSegment

app = Flask(__name__)
UPLOAD_DIR = 'uploads'
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 1. SQLite Database Setup
def init_db():
    conn = sqlite3.connect('notes.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            transcript TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# 2. NLP Highlights & Structuring Logic
def summarize_to_notes(text):
    if not text or len(text.strip()) < 5:
        return "Video se clear aawaz recognize nahi ho saki."

    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if len(s.strip()) > 8]
    if not sentences:
        sentences = [text.strip()]

    # Keywords to detect highlights
    highlight_keywords = [
        'important', 'remember', 'main', 'key', 'concept', 
        'definition', 'note', 'always', 'rule', 'exam', 'focus', 'primary'
    ]

    highlights = []
    regular_points = []

    for s in sentences[1:-1]:
        if any(re.search(r'\b' + re.escape(word) + r'\b', s, re.IGNORECASE) for word in highlight_keywords):
            highlights.append(f"⭐ [HIGHLIGHT] {s}")
        else:
            regular_points.append(s)

    if not highlights and regular_points:
        highlights = [f"⭐ [HIGHLIGHT] {pt}" for pt in regular_points[:2]]
        regular_points = regular_points[2:]

    key_points = regular_points[:4] if regular_points else sentences[1:min(len(sentences), 4)]
    points_bullet = "\n".join([f"• {p}" for p in key_points]) if key_points else "• " + sentences[0]
    highlights_bullet = "\n".join(highlights[:4]) if highlights else "• " + sentences[0]

    intro = sentences[0]
    summary = sentences[-1] if len(sentences) > 2 else sentences[0]

    formatted_notes = f"""📌 INTRODUCTION:
{intro}.

🌟 KEY HIGHLIGHTS & CRITICAL TAKEAWAYS:
{highlights_bullet}.

📌 CORE CONCEPTS & IMPORTANT POINTS:
{points_bullet}.

📌 SUMMARY:
{summary}."""

    return formatted_notes

# 3. Audio Chunker & Speech-to-Text
def process_audio_file(wav_path):
    sound = AudioSegment.from_file(wav_path).set_channels(1)
    recognizer = sr.Recognizer()
    
    chunk_length_ms = 45 * 1000
    chunks = [sound[i:i + chunk_length_ms] for i in range(0, len(sound), chunk_length_ms)]
    
    full_transcript = []
    
    for idx, chunk in enumerate(chunks):
        chunk_file = os.path.join(UPLOAD_DIR, f"temp_chunk_{idx}.wav")
        chunk.export(chunk_file, format="wav")
        
        try:
            with sr.AudioFile(chunk_file) as source:
                audio_data = recognizer.record(source)
                text = recognizer.recognize_google(audio_data)
                if text:
                    full_transcript.append(text)
        except Exception:
            pass
        finally:
            if os.path.exists(chunk_file):
                os.remove(chunk_file)

    return " ".join(full_transcript)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process-video', methods=['POST'])
def process_video():
    if 'video' not in request.files:
        return jsonify({'error': 'Video file missing'}), 400

    video = request.files['video']
    if video.filename == '':
        return jsonify({'error': 'Koi video select nahi ki gayi'}), 400

    original_name = video.filename
    temp_video = os.path.join(UPLOAD_DIR, "input_video.mp4")
    temp_wav = os.path.join(UPLOAD_DIR, "extracted_audio.wav")

    video.save(temp_video)

    try:
        clip = VideoFileClip(temp_video)
        clip.audio.write_audiofile(temp_wav, codec='pcm_s16le', logger=None)
        clip.close()

        transcript = process_audio_file(temp_wav)

        if not transcript.strip():
            return jsonify({'error': 'Audio me koi boli hui aawaz recognize nahi hui'}), 400

        notes = summarize_to_notes(transcript)

        conn = sqlite3.connect('notes.db')
        c = conn.cursor()
        c.execute('INSERT INTO notes (filename, transcript, notes) VALUES (?, ?, ?)',
                  (original_name, transcript, notes))
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'notes': notes})

    except Exception as e:
        return jsonify({'error': f"Processing Error: {str(e)}"}), 500

    finally:
        for f in [temp_video, temp_wav]:
            if os.path.exists(f):
                os.remove(f)

if __name__ == '__main__':
    app.run(debug=True, port=5000)