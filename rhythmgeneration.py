import librosa
import librosa.beat as beat
import librosa.display as rosadisp
import matplotlib.pyplot as plt
import matplotlib
import numpy as np

import lstm
import collections

#Round to 16th notes looses some precision but the feature detection for librosa
#doesn't work well enough on rap to be more precise anyway
BEAT_DIVISIONS = 4

RAP_SPEED = 'fast' #fast, slow, or mixed views input beat with tempo as either close to 60bpm or close to 120bpm
NUM_FAST_SECTIONS = 5 #Number of sections where the rap is sped up if RAP_SPEED is set to mixed
LEN_FAST_SECTIONS = 24 #Number of beats that rap is sped up for if RAP_SPEED is set to mixed

#Only quality audio file with only rap vocals from good artists I could find so far will
#potentially add more to training data later (Fast Life by Kool G Rap ft. Nas)
x, sr = librosa.load('FastLifeVocals.mp3')
o_env = librosa.onset.onset_strength(x, sr=sr)
times = librosa.frames_to_time(np.arange(len(o_env)), sr=sr)
onset_frames = librosa.onset.onset_detect(onset_envelope=o_env, sr=sr)

onset_times = times[onset_frames]

tempo, beat_times = librosa.beat.beat_track(x, sr=sr, start_bpm=120, units='time')

#Plot audio
#
#librosa.display.waveplot(x, alpha=0.6)
#plt.vlines(times[onset_frames], -1, o_env.max(), color='g', alpha=0.9)
#plt.vlines(beat_times, -1, 1, color='r')
#plt.ylim(-1, 1)
#plt.show()


onset_beats = np.zeros((len(beat_times), BEAT_DIVISIONS))
currentbeat = 0
timeinterval = (beat_times[1] - beat_times[0]) / BEAT_DIVISIONS
for currentonset in range(len(onset_times)):
    if (onset_times[currentonset] < beat_times[0] or onset_times[currentonset] > beat_times[len(beat_times) - 1]):
        continue
    while onset_times[currentonset] >= beat_times[currentbeat + 1] - 0.5*timeinterval:
        currentbeat += 1
        if (currentbeat >= beat_times.shape[0] - 1):
            break
        timeinterval = (beat_times[currentbeat + 1] - beat_times[currentbeat]) / BEAT_DIVISIONS
    if (currentbeat >= beat_times.shape[0] - 1):
        break
    t = (onset_times[currentonset] - beat_times[currentbeat]) / timeinterval
    onset_beats[currentbeat, int(round(t))] = 1

#Remove entire measures of 0s (4 beats)
i = 0
while i < onset_beats.shape[0] - 4:
    if np.all(onset_beats[i] + onset_beats[i + 1] + onset_beats[i + 2] + onset_beats[i + 3] == 0):
        onset_beats = np.delete(onset_beats, np.s_[i:i+4], 0)
    else:
        i += 1

data = tuple([tuple(beat) for beat in onset_beats])
counter = collections.Counter(data)
count_pairs = sorted(counter.items(), key=lambda x: (-x[1], x[0]))

words, _ = list(zip(*count_pairs))
word_to_id = dict(zip(words, range(len(words))))

#For now just test rhythmic generation on the instrumentals for Betrayal by Gang Starr
x1, sr1 = librosa.load('BetrayalInstrumental.mp3')
ebpm = 60
if RAP_SPEED == 'fast':
    ebpm = 120
tempo, beat_times = librosa.beat.beat_track(x1, sr=sr1, start_bpm=ebpm, units='time')

#Take NUM_FAST_SECTIONS sections of beat_times and add an extra beat between every beat in this section to
#give this section double tempo. This code is probably very inefficient I just wrote it up real quick to see
#if it would work and sound cool
if RAP_SPEED == 'mixed':
    prevfastindex = 0
    nextfastindex = beat_times.shape[0] // NUM_FAST_SECTIONS - LEN_FAST_SECTIONS // 2
    modified_beat_times = beat_times[:nextfastindex]
    for i in range(NUM_FAST_SECTIONS):
        if i != 0:
            modified_beat_times = np.append(modified_beat_times, beat_times[prevfastindex+LEN_FAST_SECTIONS:nextfastindex])
        fastsection = np.zeros(2*LEN_FAST_SECTIONS)
        fastsection[::2] = beat_times[nextfastindex:nextfastindex + LEN_FAST_SECTIONS]
        for j in range((fastsection.shape[0])//2):
            fastsection[2*j + 1] = (beat_times[nextfastindex + j + 1] + beat_times[nextfastindex + j])/2
        modified_beat_times = np.append(modified_beat_times, fastsection)

        prevfastindex = nextfastindex
        nextfastindex = (i+1) * (beat_times.shape[0] // NUM_FAST_SECTIONS) - LEN_FAST_SECTIONS // 2
    modified_beat_times = np.append(modified_beat_times, beat_times[prevfastindex+LEN_FAST_SECTIONS:])
else:
    modified_beat_times = beat_times

num_beats = modified_beat_times.shape[0] - 3
prefix = [(0,0,0,0), (0,0,0,0)] #prefix to feed lstm - just some silence for now
data = np.array([word_to_id[word] for word in data if word in word_to_id])
output = lstm.run(data, np.array([word_to_id[word] for word in prefix]), len(word_to_id), num_beats)

#Convert the raw beat data into actual rhythmic timing
rhythm_times = []
for currentbeat in range(len(output)):
    raw_beat = words[output[currentbeat]]
    timeinterval = (modified_beat_times[currentbeat + 1] - modified_beat_times[currentbeat]) / BEAT_DIVISIONS
    for i in range(len(raw_beat)):
        if raw_beat[i] == 1:
            rhythm_times.append(modified_beat_times[currentbeat] + i*timeinterval)

#For now write dummy clicks in rhythm pattern to see how it sounds will add lyrics later
clicks = librosa.clicks(times=rhythm_times, sr=sr1, length=len(x))

#No easy way to add numpy arrays of different sizes so done below:
x1np = np.array(x1)
clicksnp = np.array(clicks)
if len(clicksnp) < len(x1np):
    outputaudio = x1np.copy()
    outputaudio[:len(clicksnp)] += clicksnp
else:
    outputaudio = clicksnp.copy()
    outputaudio[:len(x1np)] += x1np
librosa.output.write_wav('clicks-fast.wav', outputaudio, sr1)