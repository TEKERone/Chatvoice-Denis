#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# GPL 3.0
# User module for ahorrin chatbot
# Eduardo Contreras Chavez - Francisco Ruben Frias Valderrama
# Verano de investigacion AMC 2018 - Delfin 2018 
# IIMAS-UNAM Dr. Ivan Vladimir Meza Ruiz

import os
import hashlib
import pyaudio
from datetime import datetime, timedelta
import time
from tinydb import TinyDB, Query
from gtts import gTTS
import pyttsx3
import webrtcvad
import wave
import numpy as np
from array import array
from struct import pack
from subprocess import DEVNULL, Popen, PIPE, STDOUT
from collections import deque
import speech_recognition as sr
from socketIO_client import SocketIO, BaseNamespace

class StateNamespace(BaseNamespace):
    pass

# setting
db = TinyDB('audios.json')
Audio = Query()
engine_local = pyttsx3.init('espeak');
voices = engine_local.getProperty('voices')
for voice in voices:
    if voice.languages[0] == b'\x05es':
        engine_local.setProperty('voice', voice.id)
        break
audio = pyaudio.PyAudio()
vad = webrtcvad.Vad()
stream= None
socket_state=None

samplerate=16000
block_duration=10
padding_duration=1000
FRAMES_PER_BUFFER=samplerate*block_duration/1000
NUM_PADDING_CHUNKS=int(padding_duration/block_duration)
NUM_WINDOW_CHUNKS=int(400/block_duration)
ring_buffer=deque(maxlen=NUM_PADDING_CHUNKS)
ring_buffer_flags = [0] * NUM_WINDOW_CHUNKS
ring_buffer_index=0

AUDIOS=[]
DIRAUDIOS='rec_voice_audios'
rec = sr.Recognizer()

# 0 - not connected
# 1 - connected
# 2 - listening silence
# 3 - listening voice
# 4 - stop listening
STATE={
    "main":0,
    "time_start_listening":None
}

def clear_audios():
    AUDIOS=[]

# TTS
if not os.path.exists(os.path.join(os.getcwd(), 'audios')):
    os.mkdir(os.path.join(os.getcwd(), 'audios'))

def tts_local(msg):
    engine_local.say(msg)
    engine_local.runAndWait() ;

def tts_google(msg,lang='es-us'):
    hashing = hashlib.md5(msg.encode('utf-8')).hexdigest()
    res = db.search((Audio.hash == hashing) & (Audio.type=='google'))
    if len(res)>0:
        p = Popen(['mpg321',os.path.join(os.getcwd(),'audios',res[0]['mp3'])], stdout=DEVNULL, stderr=STDOUT)
        p.communicate()
        assert p.returncode == 0
        return None
    mp3_filename=os.path.join(os.getcwd(), 'audios', '{}_{}.mp3'.format(hashing,'google'))
    tts = gTTS(msg, 'es-us')
    tts.save(mp3_filename)
    p = Popen(['mpg321',mp3_filename], stdout=DEVNULL, stderr=STDOUT)
    p.communicate()
    assert p.returncode == 0
    db.insert({'hash':hashing,'type':'google','mp3':'{}_{}.mp3'.format(hashing,'google')})


# Vad
def vad_aggressiveness(a):
    vad.set_mode(a)

# Monitoring
def audio_devices():
    devices=[]
    for i in range(audio.get_device_count()):
        info=audio.get_device_info_by_index(i)
        devices.append('{0} -> {1}'.format(i,"\n".join(["   {0}:{1}".format(x, y) for x,y in info.items()])))

    return devices

def audio_connect(device=None,samplerate=16000,block_duration=10,padding_duration=1000, host=None, port=None, channels=1, activate=True):
    if not activate:
        return
    global socket_state
    if host:
        socket = SocketIO(host,port)
        socket_state = socket.define(StateNamespace, '/state')

    samplerate=samplerate
    FRAMES_PER_BUFFER=int(samplerate*block_duration/1000)
    NUM_PADDING_CHUNKS=int(padding_duration/block_duration)
    NUM_WINDOW_CHUNKS=int(250/block_duration)
    ring_buffer=deque(maxlen=NUM_PADDING_CHUNKS)
    ring_buffer_flags = [0] * NUM_WINDOW_CHUNKS
    ring_buffer_index=0
    stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=samplerate,
            frames_per_buffer=FRAMES_PER_BUFFER,
            input=True,
            start=False,
            stream_callback=callback
        )
    stream.start_stream()
    STATE['main']="1"


voiced_buffer=np.array([],dtype='Int16')
ring_buffer=np.array([],dtype='Int16')
wave_file=None
filename_wav="tmp.wav"
# Audio capturing
def callback(in_data, frame_count, time_info, status):
    global ring_buffer_index, ring_buffer_flags,triggered, voiced_buffer, ring_buffer, wave_file, DIRAUDIOS, filename_wav, STATE, socket_state
    if socket_state:
        socket_state.emit('audio',STATE)
    if STATE['main']==1 or STATE['main']==4:
        ring_buffer_index=0
        voiced_buffer=np.array([],dtype='Int16')
        ring_buffer=np.array([],dtype='Int16')
        return (in_data,pyaudio.paContinue)
    is_speech = vad.is_speech(in_data, 16000)
    in_data_ = np.fromstring(in_data, dtype='Int16')
    in_data_ = in_data_/32767.0
    ring_buffer_flags[ring_buffer_index] = 1 if is_speech else 0
    ring_buffer_index += 1
    ring_buffer_index %= NUM_WINDOW_CHUNKS
    if STATE['main']==2:
        ring_buffer=np.concatenate((ring_buffer,in_data_))
        num_voiced = sum(ring_buffer_flags)
        if num_voiced > 0.5 * NUM_WINDOW_CHUNKS:
            STATE['main'] = 3
            filename_wav = "{}/{}.wav".format(DIRAUDIOS,datetime.now().strftime("%Y%m%d_%H%M%S"))
            wave_file = wave.open(filename_wav, 'wb')
            wave_file.setnchannels(1)
            wave_file.setsampwidth(2)
            wave_file.setframerate(samplerate)
            voiced_buffer=np.array(ring_buffer)
            ring_buffer=np.array([],dtype="Int16")
    else:
        voiced_buffer=np.concatenate((voiced_buffer,in_data_))
        num_unvoiced = NUM_WINDOW_CHUNKS - sum(ring_buffer_flags)
        if len(voiced_buffer)>0 and num_unvoiced > 0.90 * NUM_WINDOW_CHUNKS:
            STATE['main'] = 2
            if wave_file:
                in_data_ = np.int16(voiced_buffer*32767)
                wave_file.writeframes(in_data_.tostring())
                wave_file.close()
                AUDIOS.append((datetime.now(),filename_wav))
            voiced_buffer=np.array([],dtype="Int16")
    return (in_data,pyaudio.paContinue)

def pull_latest():
    now=datetime.now()
    while len(AUDIOS)==0 or AUDIOS[-1][0]+timedelta(milliseconds=400)<= now:
        return None
    return AUDIOS[-1][1]

def audio_state():
    return STATE

def start_listening():
    STATE['main']=2

def stop_listening():
    STATE['main']=4

def set_audio_dirname(dir):
    DIRAUDIOS=dir

def audio_close():
    if stream:
        stream.close()
    audio.terminate()

# Speech recogniser
def sr_google(filename):
    with sr.AudioFile(filename) as source:
        audio = rec.record(source)  # read the entire audio file

    # recognize speech using Google Speech Recognition
    try:
        # for testing purposes, we're just using the default API key
        # to use another API key, use `r.recognize_google(audio, key="GOOGLE_SPEECH_RECOGNITION_API_KEY")`
        # instead of `r.recognize_google(audio)`
        return rec.recognize_google(audio, language='es-mx')
    except sr.UnknownValueError:
        return 'UNK'
    except sr.RequestError as e:
        print("Could not request results from Google Speech Recognition service; {0}".format(e))


