    width=135, height=240, x_offset=53, y_offset=40
)
backlight = digitalio.DigitalInOut(board.D22)
backlight.switch_to_output(value=True)

try:
    font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16
    )
except OSError:
    font = ImageFont.load_default()


def show(lines, status, colour="gray", light_on=True):
    """Draw up to three text lines, a status message, and a light."""
    image = Image.new("RGB", (240, 135), "black")
    draw = ImageDraw.Draw(image)
    for i, line in enumerate(lines):
        draw.text((10, 8 + i * 25), line, font=font, fill="white")
    draw.line((10, 92, 230, 92), fill="gray")
    draw.ellipse((10, 106, 26, 122),
                 fill=colour if light_on else "#202020")
    draw.text((36, 103), status, font=font, fill="white")
    display.image(image, 90)


def speak(text):
    """Use the same Piper model and audio format as the Bash script."""
    with tempfile.TemporaryFile() as audio:
        subprocess.run([
            sys.executable, "-m", "piper",
            "--model", "en_US-lessac-medium",
            "--data-dir", str(VOICES_DIR),
            "--output-raw", "--", text
        ], stdout=audio, check=True, cwd=BASE)
        audio.seek(0)
        subprocess.run([
            "aplay", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-"
        ], stdin=audio, check=True)


def recognise(filename):
    # Read all segments here so transcription finishes in the worker.
    segments, info = model.transcribe(
        str(filename), language="en", beam_size=1, vad_filter=True
    )
    return " ".join(segment.text.strip() for segment in segments).strip()


def transcribe(filename):
    """Transcribe in the background so the screen can keep blinking."""
    with ThreadPoolExecutor(max_workers=1) as worker:
        result = worker.submit(recognise, filename)
        light_on = True
        while not result.done():
            show(["Processing your", "answer..."],
                 "Processing", "lime", light_on)
            light_on = not light_on
            time.sleep(0.4)
        return result.result()


def ask(question, lines, filename):
    # Finish speaking before starting the microphone.
    show(lines, "Please listen")
    speak(question)
    show(lines, "Now recording", "lime")
    subprocess.run([
        "arecord", "-d", str(RECORD_SECONDS), "-f", "S16_LE",
        "-c", "1", "-r", "16000", str(filename)
    ], check=True)
    answer = transcribe(filename)
    print(question, "->", answer, flush=True)
    if not answer:
        raise RuntimeError("No speech detected. Please run again and speak clearly.")
    return answer


try:
    show(["Loading speech model", "Please wait..."], "Starting")
    model = WhisperModel("tiny.en", device="cpu", compute_type="int8")

    name = ask("Welcome. What is the name of the person you are visiting?",
               ["Who are you", "visiting?", "Say their name."],
               BASE / "occupant_name.wav")

    floor = ask("What floor do they live on?",
                ["What floor do", "they live on?", "Say the floor number."],
                BASE / "occupant_floor.wav")

    print("\nOccupant:", name, "\nFloor:", floor)

    # Demo stand-in for sending a request and receiving a phone reply.
    # No real request is sent. The transcripts remain in the terminal.
    show(["Waiting for", "confirmation", "Phone approval demo"],
         "Waiting", "red")
    speak("Thank you. Please wait for confirmation.")
    decision = input("\nDEMO occupant approval: y = allow, n = deny: ")
    while decision.strip().lower() not in ("y", "n"):
        decision = input("Please type y or n: ")

    if decision.strip().lower() == "y":
        show(["Access granted", "You may enter.", "Demo only"],
             "Approved", "lime")
        speak("Your visit has been approved. You may enter.")
    else:
        show(["Access not approved", "Please contact", "your friend."],
             "Not approved", "red")
        speak("Your visit was not approved. Please contact your friend.")

    input("Press Enter to close the demo.")
except (KeyboardInterrupt, EOFError):
    print("\nDemo stopped.")
except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
    show(["Something went wrong", "Check the terminal."], "Error", "red")
    print("Error:", error, file=sys.stderr)
    time.sleep(3)
    sys.exit(1)
finally:
    backlight.value = False
    backlight.deinit()
    dc.deinit()
    cs.deinit()
    spi.deinit()
