# Chatterboxes

**NAMES OF COLLABORATORS HERE**

[![Watch the video](https://user-images.githubusercontent.com/1128669/135009222-111fe522-e6ba-46ad-b6dc-d1633d21129c.png)](https://www.youtube.com/embed/Q8FWzLMobx0?start=19)

In this lab, we want you to design interaction with a speech-enabled device — something that listens and talks to you. This device can do anything *but* control lights (since we already did that in Lab 1). First, we want you to storyboard what you imagine the conversational interaction to be like. Then you will use wizarding techniques to elicit examples of what people might say, ask, or respond. We then want you to use the examples collected from at least two other people to inform the redesign of the device.

We will focus on **audio** as the main modality for interaction to start; these general techniques can be extended to **video**, **haptics** or other interactive mechanisms in the second part of the Lab.

A note on what you are building with. Speech interfaces are usually taught as two boxes — speech-in, speech-out — and that framing hides the part that actually determines whether an interaction works. Between listening and speaking sits the question of **whose turn it is**: when does the device decide you have finished talking, and how long does it make you wait before it answers? This lab gives you direct control over both, and we will ask you to notice what changes when you move them.

## Prep for Part 1: Get the Latest Content and Pick up Additional Parts

Please check instructions in [prep.md](prep.md) and complete the setup.

### Pick up Web Camera If You Don't Have One

Students who have not already received a web camera will receive their Webcam and at the beginning of lab. If you cannot make it to class this week, please contact the TAs to ensure you get these.

### Get the Latest Content

As always, pull updates from the class Interactive-Lab-Hub to both your Pi and your own GitHub repo.

**\[recommended\]** Option 1: On the Pi, `cd` to your `Interactive-Lab-Hub`, pull the updates from upstream (class lab-hub) and push the updates back to your own GitHub repo. You will need the *personal access token* for this.

```
pi@ixe00:~$ cd Interactive-Lab-Hub
pi@ixe00:~/Interactive-Lab-Hub $ git pull upstream Fall2026
pi@ixe00:~/Interactive-Lab-Hub $ git add .
pi@ixe00:~/Interactive-Lab-Hub $ git commit -m "get lab3 updates"
pi@ixe00:~/Interactive-Lab-Hub $ git push
```

Option 2: On your own GitHub repo, create a pull request to get updates from the class Interactive-Lab-Hub. After you have the latest updates online, go to your Pi, `cd` to your `Interactive-Lab-Hub` and use `git pull`.

---

# Part 1

## Setup

Create and activate a virtual environment for this lab:

```
pi@ixe00:~$ cd Interactive-Lab-Hub/Lab\ 3
pi@ixe00:~/Interactive-Lab-Hub/Lab 3 $ python3 -m venv .venv
pi@ixe00:~/Interactive-Lab-Hub/Lab 3 $ source .venv/bin/activate
(.venv) pi@ixe00:~/Interactive-Lab-Hub/Lab 3 $
```

Install the Python dependencies:

```
(.venv) $ pip install -r requirements.txt
```

This takes a few minutes. If you would like it to take considerably less time, [`uv`](https://docs.astral.sh/uv/) is a drop-in replacement for `pip` that is dramatically faster on the Pi:

```
(.venv) $ pip install uv && uv pip install -r requirements.txt
```

Then run the setup script, which installs the classic speech synthesizers, downloads the voice activity detection model, and pre-fetches a neural voice and a speech recognition model so you are not waiting on downloads during lab:

```
(.venv):~$ cd speech-scripts
(.venv) $ ./setup.sh
```

Check your audio devices before going further. `arecord -l` lists capture devices and `aplay -l` lists playback devices; if your webcam microphone or Bluetooth speaker does not appear, fix that first — every script below assumes the system defaults are the ones you want.

## A. Text to Speech

Your Pi can speak in several quite different ways, and the differences are audible in a way that matters for design. In `speech-scripts/` there are shell scripts for each.

### The classic engines

```
(.venv) $ cd speech-scripts

(.venv) $ sudo apt update
(.venv) $ sudo apt install -y espeak festival festvox-kallpc16k

(.venv) $ ./espeak_demo.sh
(.venv) $ ./festival_demo.sh
```

You can run these `.sh` files by typing `./filename`, and read one with `cat filename`. You can also play audio files directly with `aplay filename` — try `aplay lookdave.wav`.

These are all decades-old technology and they sound like it. `espeak-ng` is a *formant synthesizer*: it generates speech from an acoustic model of the vocal tract, which is why it sounds robotic but also why the whole thing fits in a couple of megabytes and responds instantly. `festival` is *concatenative*: they stitch together recorded fragments of a real speaker, which sounds more human but breaks audibly at the seams.

### Neural TTS with Piper

Note that the Piper command line changed in version 1.x — voices are now downloaded explicitly with `python3 -m piper.download_voices`, and you invoke it as `python3 -m piper`. Tutorials you find online may show the old `echo ... | piper --model ...` form, which no longer works. Browse the [voice samples](https://rhasspy.github.io/piper-samples) and download a different one if you'd like:

```
(.venv) $ python3 -m piper.download_voices en_US-lessac-medium
```

[Piper](https://github.com/OHF-Voice/piper1-gpl) synthesizes speech with a small neural network, runs comfortably on the Pi 5, and sounds markedly better than the above.

```
(.venv) $ ./piper_demo.sh
```

The demo script also shows `--output-raw`, which streams audio to the speaker as it is generated rather than writing a file first. Listen for the difference in how quickly speech begins. In a conversational system this gap is the thing your user experiences as responsiveness.

\*\***Write your own shell file to use your favorite of these TTS engines to have your Pi greet you by name.**\*\*

The shell file used to greet myself using 'Neural' TTS is saved as the following file [Greet.sh](https://github.com/TonyW755/Interactive-Lab-Hub/blob/Fall2026/Lab%203/speech-scripts/Greet.sh)

\*\***Then answer: Is the same greeting, in these different voices, the same greeting? Describe one concrete way the voice changed what the utterance seemed to mean or who seemed to be speaking.**\*\*
The greeting differed between the three voices, even though the greeting phrase were identical. Firstly, with 'espeak', the voice sounded very robotic and the rate of speech was extremely fast. On the other hand, the neural Piper voice sounded much more natural, which made the greeting feel warmer. Finally, 'festival' was in between these two voices as it uses recorded fragments of a real speaker making it a little more human. However, the overall speech still felt unnatural as the recorded pieces were stitched together and lacked Continuity. Therefore, Neural Piper was my favourite voice as it sounded much smoother and natural which made the greeting feel personal. 


## B. Speech to Text

We use [faster-whisper](https://github.com/SYSTRAN/faster-whisper), a reimplementation of OpenAI's Whisper model that runs several times faster on CPU and does not require PyTorch. All processing happens on the Pi; nothing is sent to a server.

```
(.venv) $ python transcribe.py lookdave.wav
```

The transcript is not the interesting output here — the timings are. Run it again with a larger model and compare:

```
(.venv) $ python transcribe.py lookdave.wav --model base.en
(.venv) $ python transcribe.py lookdave.wav --model small.en
#  noted that the first run may take longer because the model is downloaded, and that the HF unauthenticated-request warning is expected and not an error.
```

Available sizes, smallest first: `tiny.en`, `base.en`, `small.en`, `medium.en`. The `.en` variants are English-only and faster than their multilingual counterparts at the same size.

\*\***Record a few seconds of your own speech (`arecord -d 5 -f cd -c 1 -r 16000 test.wav`) and transcribe it with at least two model sizes. Report the real-time factor for each. At what point does the accuracy improvement stop being worth the delay, for a system that has to answer you?**\*\*
<img width="2776" height="617" alt="image" src="https://github.com/user-attachments/assets/9f09c195-7580-491c-8656-4a74087e07a3" />

For the 5 second recording, I test two models tiny.en and base.en as shown in the figure above. According to the data, the transcription was 1.02s for the tiny.en model and had a real-time factor of 0.20×, while the transcription of base.en was 2.06s with a real-time factor of 0.41×. In this example, both models produced identical transcripts, hence the larger model did not explicitly express an improvement in accuracy, while taking about twice as long to process. For a system that requires immediate response, tiny.en would be more suited because trade-off between delay and high precision is not worthwhile. However, for a noisy surrounding or speech, base.en and larger model would be more suitable as accuracy improvement is necessary and could have a huge impact on the output.


\*\***Write your own script that verbally asks for a numerical input (a phone number, zipcode, number of pets) and records the answer the respondent provides.**\*\* 

The following script asks for a phone number and records the input [phone.sp](https://github.com/TonyW755/Interactive-Lab-Hub/blob/Fall2026/Lab%203/speech-scripts/phone.sh) 

## C. Turn-taking: knowing when someone has stopped talking

Everything so far has worked on fixed audio files. A real conversational device does not get told when to start and stop recording — it has to decide. This is the problem that makes speech interfaces hard, and it is mostly not a speech recognition problem.

We use a **voice activity detector** (VAD) to segment the microphone stream into utterances. `listen.py` runs Silero VAD continuously and hands each detected utterance to faster-whisper:

```
(.venv) $ cd speech-scripts
(.venv) $ python listen.py
```

Speak, pause, and watch it transcribe. Now change the endpointing threshold — the amount of silence the system requires before it decides your turn is over:

```
(.venv) $ python listen.py --min-silence 0.2
(.venv) $ python listen.py --min-silence 1.5
```

\*\***Try both extremes, and something in between. Describe what each one feels like to talk to. Note specifically: at 0.2s, what kinds of normal speech get cut off? At 1.5s, what does the delay make the system seem like?**\*\*
<img width="881" height="188" alt="Screenshot 2026-09-27 at 18 47 16" src="https://github.com/user-attachments/assets/9e21ede9-f103-4999-9259-9316606f1072" />

With an end pointing threshold of 0.2 s, the system felt very responsive, but the system was a bitt too sensitive to short pauses. Normal pauses between phrases and brief hesitations caused the speech to be split into separate sentences.

<img width="905" height="165" alt="Screenshot 2026-09-27 at 18 46 56" src="https://github.com/user-attachments/assets/bd1618b4-5a8b-4970-a0c1-9e6a9e18cd9d" />

With an end pointing threshold of 1.5 s, the system allowed more natural pauses and speeches were less likely to cut-off. However, the long waiting period after individual speeches made the system feel slightly unresponsive.

There is no correct value. A system that takes drink orders and a system that listens to someone think out loud want very different thresholds, and the right one depends on what your users are doing with their pauses.

### The complete loop

`echo_bot.py` puts the pieces together: it listens, endpoints, transcribes, and speaks a reply through Piper. The dialogue policy is deliberately trivial — it repeats what you said — so that everything you notice is a property of the timing rather than the content.

```
(.venv) $ python echo_bot.py
```

## D. Storyboard

Storyboard and/or use a Verplank diagram to design a speech-enabled device. (Stuck? Make a device that talks for dogs. If that is too stupid, find an application that is better than that.)

\*\***Post your storyboard and diagram here.**\*\*

<img width="1536" height="1024" alt="image" src="https://github.com/user-attachments/assets/79d0da91-1816-4801-b2da-012b0f3dddd4" />


Write out what you imagine the dialogue to be. Use cards, post-its, or whatever method helps you develop alternatives or group responses.

\*\***Please describe and document your process.**\*\*

<img width="351" height="649" alt="Screenshot 2026-09-27 at 21 01 41" src="https://github.com/user-attachments/assets/55d2d242-9ace-4811-9214-9d67497ad8b7" />


Your script should include the pauses. Where does your device wait, and for how long? You now know from Part C that this is a parameter you have to choose, not something that happens for free.

## E. Acting out the dialogue

Find a partner, and *without sharing the script with your partner* try out the dialogue you've designed, where you (as the device designer) act as the device you are designing. Please record this interaction (for example, using Zoom's record feature).

\*\***Describe if the dialogue seemed different than what you imagined when it was acted out, and how.**\*\*


---

# Lab 3 Part 2

For Part 2, you will redesign the interaction with the speech-enabled device using the data collected, as well as feedback from part 1.

## Prep for Part 2

1. What are concrete things that could use improvement in the design of your device? For example: wording, timing, anticipation of misunderstandings.
Better timing: The device should finish speaking before it starts listening and a short sound and a screen message can tell the visitor when to speak.
Check the answer: Speech recognition may confuse similar names or miss interpret names due to accent. Hence, before sending the request, the device should confirm with a screen message display about the name and floor of the occupant. For example, "You’re visiting Maya Chen on floor eight. Is that correct?".
Help with mistakes: If the answer is unclear, ask for the missing part again: “I didn’t catch the floor number. Please say it again.”
2. What are other modes of interaction *beyond speech* that you might also use to clarify how to interact? In particular: how does someone know when the device is listening, and when it is thinking? You have a screen and an LED.
The screen and LED should clearly show what the device is doing through simple messages, light patterns, and colours. When the device is recording the visitor’s voice, the LED stays green and the screen shows “Now recording.” Once recording is complete, the LED begins to blink and the screen shows “Processing your request.” After the request is sent to the occupant, the LED turns red and the screen shows “Waiting for confirmation.” Only when the occupant approves the visit, the LED turns green again and the screen shows “Access granted” or else the LED remains red and shows "Access denied".
4. Make a new storyboard, diagram and/or script based on these reflections.
   <img width="1536" height="1024" alt="image" src="https://github.com/user-attachments/assets/6d6549e7-4c37-474f-9284-49efd38a96b8" />

6. (optional) Integrate [input devices](inputs.md) in the system

## Prototype your system

The system should:
* use the Raspberry Pi
* use one or more sensors
* require participants to speak to it

*Document how the system works.*

The code is generated with the support of chatgpt and is saved in the following file [visitor.py](https://github.com/TonyW755/Interactive-Lab-Hub/blob/Fall2026/Lab%203/visitor.py)

Screen capture of the system
<img width="1488" height="1212" alt="image" src="https://github.com/user-attachments/assets/a7b53a23-ee23-415e-bb01-2e253ef574b5" />

Screen capture of the controller on the phone
<img width="1800" height="1150" alt="image" src="https://github.com/user-attachments/assets/9d69f5f2-bc5b-4d89-a119-57f3612f9135" />


Video of the interaction 

https://github.com/user-attachments/assets/19c1ab51-1fb7-47e3-8169-d7bfd3dfffeb



*Include videos or screencaptures of both the system and the controller.*

## Test the system

Try to get at least two people to interact with your system. (Ideally, you would inform them that there is a wizard *after* the interaction, but we recognize that can be hard.)

Answer the following:

### What worked well about the system and what didn't?
\*\**your answer here*\*\*

### What worked well about the controller and what didn't?
\*\**your answer here*\*\*

### What lessons can you take away from the WoZ interactions for designing a more autonomous version of the system?
\*\**your answer here*\*\*

### How could you use your system to create a dataset of interaction? What other sensing modalities would make sense to capture?
\*\**your answer here*\*\*

<details>
  <summary><strong>Submission Cleanup Reminder (Click to Expand)</strong></summary>

  **Before submitting your README.md:**
  - This readme.md file has a lot of extra text for guidance.
  - Remove all instructional text and example prompts from this file.
  - You may either delete these sections or use the toggle/hide feature in VS Code to collapse them for a cleaner look.
  - Your final submission should be neat, focused on your own work, and easy to read for grading.
</details>
