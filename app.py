import openai
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
import pyaudio
import wave
import time
import speech_recognition as sr
import pandas as pd
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)
openai.api_key = 'api_key'  

def get_glassdoor_link(company, role):
    query = f"{company} {role} interview questions"
    search_url = f"https://www.google.com/search?q={query}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36'
    }
    
    response = requests.get(search_url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    for g in soup.find_all('a'):
        href = g.get('href')
        if href and "glassdoor.com" in href:
            return href.split('&')[0]  
    
    return None

def scrape_glassdoor_questions(link, driver_path):
    service = Service(executable_path=driver_path)
    driver = webdriver.Firefox(service=service)
    
    driver.get(link)
    
    time.sleep(3)  
    
    questions_list = []
    
    try:
        for i, elem in enumerate(driver.find_elements(By.CLASS_NAME, 'interview-details_interviewText__YH2ZO'), start=1):
            question = elem.find_element(By.TAG_NAME, 'p').text
            questions_list.append({"Question Number": i, "Question": question})
    except Exception as e:
        print(f"Error while scraping questions: {e}")
    finally:
        driver.quit()  
    
    return pd.DataFrame(questions_list)  

def summarize_questions(questions):
    question_text = "\n".join(questions)
    
    prompt = f"Here are some interview questions:\n\n{question_text}\n\nGenerate a list of similar interview questions based on the provided ones."
    
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200
    )
    
    generated_questions = response['choices'][0]['message']['content']
    question_list = generated_questions.split("\n")
    
    return [q.strip() for q in question_list if q.strip()]

def record_audio(filename, duration=5):
    chunk = 1024  
    format = pyaudio.paInt16  
    channels = 1  
    rate = 44100  
    audio = pyaudio.PyAudio()  
    stream = audio.open(format=format, channels=channels, rate=rate, input=True, frames_per_buffer=chunk)
    
    print("Recording... Speak now!")
    frames = []
    for _ in range(0, int(rate / chunk * duration)):
        data = stream.read(chunk)
        frames.append(data)

    print("Finished recording.")

    stream.stop_stream()
    stream.close()
    audio.terminate()
    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(audio.get_sample_size(format))
        wf.setframerate(rate)
        wf.writeframes(b''.join(frames))

def transcribe_audio(audio_file):
    recognizer = sr.Recognizer()
    with sr.AudioFile(audio_file) as source:
        audio_data = recognizer.record(source)
        try:
            transcription = recognizer.recognize_google(audio_data)
            return transcription
        except sr.UnknownValueError:
            return None  # No clear audio detected
        except sr.RequestError as e:
            return f"Error with Google Speech Recognition: {e}"

def get_feedback(question, user_response):
    if not user_response:
        return "It seems like there was an issue with the audio in the question. Moving on to the next question."
    
    prompt = f"Question: {question}\nResponse: {user_response}\nFeedback:"
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=150
    )
    return response['choices'][0]['message']['content']

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/interview', methods=['POST'])
def interview():
    data = request.json
    company = data['company']
    role = data['role']
    
    driver_path = "/Users/samanvitha/Downloads/geckodriver 5"  
    glassdoor_link = get_glassdoor_link(company, role)
    
    if glassdoor_link:
        questions_df = scrape_glassdoor_questions(glassdoor_link, driver_path)
        summarized_questions = summarize_questions(questions_df['Question'])
        
        return jsonify({'success': True, 'questions': summarized_questions})
    else:
        return jsonify({'success': False, 'message': 'No Glassdoor link found.'})

@app.route('/ask_question', methods=['POST'])
def ask_question():
    data = request.json
    question = data['question']
    
    # Record the user's response
    audio_file = 'user_response.wav'
    record_audio(audio_file, duration=30)  
    user_response = transcribe_audio(audio_file)
    
    feedback = get_feedback(question, user_response)
    
    return jsonify({'response': user_response, 'feedback': feedback})

if __name__ == "__main__":
    app.run(debug=True)
