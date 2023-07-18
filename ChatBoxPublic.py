#!/usr/bin/env python
#coding: utf8

# zum automatischen Ausführen beim booten Service AutoRunChatBox in /etc/systemd/system/ anlegen

import RPi.GPIO as GPIO

# Zählweise der Pins festlegen
GPIO.setmode(GPIO.BOARD)
# Warnungen ausschalten
GPIO.setwarnings(False)
# Pin 8 (GPIO 14) als Eingang festlegen, keinen internen pull up/down Widerstand setzen
GPIO.setup(8, GPIO.IN)
# Pin 32 aus Ausgang für grüne LED festlegen
GPIO.setup(32, GPIO.OUT)
GPIO.output(32, GPIO.LOW)
# Pin 36 aus Ausgang für rote LED festlegen
GPIO.setup(36, GPIO.OUT)
GPIO.output(36, GPIO.LOW)
# globale Flanken Variable EDGE definieren
EDGE=False

import os
import time
import asyncio
# Für AWS Polly ggf. AWS SDK Boto3 für Python mit 'pip install boto3' instalieren
import boto3
# Für ChatGPT ggf. OpenAI API mit 'pip install openai' installieren
import openai
# Für AWS Transcribe ggf. 'aiofile' mit `pip install aiofile` für asysncrone Dateizugriffe installieren
import aiofile

# Für AWS Transcribe ggf. auch Phyton SDK für AWS Transcribe mit 'python3 -m pip install amazon-transcribe' installieren
from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent
from amazon_transcribe.utils import apply_realtime_delay

# Für ChatGPT OpenAI Konto erstellen und Schlüssel unter 'https://platform.openai.com/account/api-keys' generieren
openai.api_key = "MyKeyMyKeyMyKey"

# Für AWS Transcribe und AWS Polly AWS Konto auf https://aws.amazon.com/de/ erstellen und Schlüssel generieren 
# Ggf. mit 'export' AWS_ACCESS_KEY_ID und AWS_SECRET_ACCESS_KEY als Shell Umgebungsvariable definieren oder dauerhaft in /etc/profile oder /etc/bash.bashrc speichern


# Settings für asynchrone Transkription
SAMPLE_RATE = 44100
BYTES_PER_SAMPLE = 2
CHANNEL_NUMS = 1
AUDIO_PATH = "/home/pi/record.wav"
CHUNK_SIZE = 1024 * 8
REGION = "eu-central-1" #Frankfurt

# Liste für 'Transcribe' Ergebnisse
RESULT=[]

# Event Handler definieren
class MyEventHandler(TranscriptResultStreamHandler):
    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        results = transcript_event.transcript.results
        # Alle Transkriptionsergebnisse in Liste schreiben
        for result in results:
            for alt in result.alternatives:
                RESULT.append(alt.transcript)


async def basic_transcribe():
    # Client aufsetzen
    client = TranscribeStreamingClient(region=REGION)

    stream = await client.start_stream_transcription(
        language_code="de-DE",
        media_sample_rate_hz=SAMPLE_RATE,
        media_encoding="pcm",
    )

    async def write_chunks():
        async with aiofile.AIOFile(AUDIO_PATH, "rb") as afp:
            reader = aiofile.Reader(afp, chunk_size=CHUNK_SIZE)
            await apply_realtime_delay(
                stream, reader, BYTES_PER_SAMPLE, SAMPLE_RATE, CHANNEL_NUMS
            )
        await stream.input_stream.end_stream()

    # Handler instanziieren
    handler = MyEventHandler(stream.output_stream)
    await asyncio.gather(write_chunks(), handler.handle_events())

# AWS Polly session starten
polly_client = boto3.Session(region_name='eu-central-1').client('polly')
    
# Endlosschleife
while 1:

    # Default Zustand ist HIGH bei offenem Taster
    if GPIO.input(8) == GPIO.HIGH and EDGE==False:
        time.sleep(0.05)
        # nachdem Taste stabil ist nochmal abfragen
        if GPIO.input(8) == GPIO.HIGH and EDGE==False:
        # grüne LED an und rote LED aus, bereit zur Aufnahme
            GPIO.output(32, GPIO.HIGH)
            GPIO.output(36, GPIO.LOW)

    # HIGH-LOW Flanke detektieren
    if GPIO.input(8) == GPIO.LOW and EDGE==False:
        time.sleep(0.05)
        # nachdem Taste stabil ist nochmal abfragen
        if GPIO.input(8) == GPIO.LOW and EDGE==False:
            # grüne LED aus und rote LED an, Verarbeitung läuft
            GPIO.output(32, GPIO.LOW)
            GPIO.output(36, GPIO.HIGH)

            # Dauerhaft im Hintergrund aufnehmen bis der Prozess gekillt wird
            os.system("arecord --device=hw:1,0 --format S16_LE --rate 44100 -c1 -q /home/pi/record.wav &")

            # Flankenflag setzen
            EDGE=True

    # LOW-HIGH Flanke detektieren
    if GPIO.input(8) == GPIO.HIGH and EDGE==True:
        time.sleep(0.05)
        # nachdem Taste stabil ist nochmal abfragen
        if GPIO.input(8) == GPIO.HIGH and EDGE==True:
            # arecord beenden
            os.system("pkill arecord")

            # transkribieren...
            # Wartetext ansagen
            # Ggf. 'sox' mit 'sudo apt-get install sox' installieren
            # Ggf. mp3 library mit 'sudo apt-get install libsox-fmt-mp3' installieren
            os.system("play -q -v 2 '/home/pi/BitteWartenNeural.mp3' -t alsa &")
            #print ("Transcrption ongoing...")
            loop = asyncio.get_event_loop()
            loop.run_until_complete(basic_transcribe())
            #print(RESULT[-1])

            if len(RESULT) > 0:
                # ChatGPT session starten und Frage stellen...
                #print ("Waiting for Chat GPT...")
                # Wartetext ansagen
                os.system("play -q -v 2 '/home/pi/BitteWartenNeural.mp3' -t alsa &")
                
                completion = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "user", "content": RESULT[-1]}
                    ]   
                )
                GPT_out=completion.choices[0].message.content
                #print(GPT_out)

                # Antwort mit AWS Polly ausgeben...
                #print ("Text to Speach ongoing...")

                # Verfügbare deutsche Stimmen sind: 'Marlene', 'Vicki', 'Hans' und 'Daniel' für die 'standard' engine
                # Für die 'neural' engine mt besserer Sprachqualität ist nur 'Vicki' und 'Daniel' verfügbar
                # Ausgabe Formate sind: 'ogg_vorbis', 'json', 'mp3' und 'pcm'

                response = polly_client.synthesize_speech(VoiceId='Daniel',
                        OutputFormat='mp3',
                        Text = GPT_out,
                        Engine = 'neural')

                file = open('/home/pi/speech.mp3', 'wb')
                file.write(response['AudioStream'].read())
                file.close()

                # Vorlesen der MP3 Datei
                os.system("play -q -v 2 '/home/pi/speech.mp3' -t alsa")

            # FlankenFlag zurücksetzen
            EDGE=False
            # RESULT löschen
            RESULT=[]