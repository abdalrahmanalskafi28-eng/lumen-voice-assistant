import os
import re
import sys
import time
import uuid
import tempfile
import datetime
import subprocess
import threading
import webbrowser
import urllib.parse
from difflib import SequenceMatcher

import speech_recognition as sr
from gtts import gTTS
from playsound import playsound
from groq import Groq

# مكتبة الصوت الأنثوي الناعم (pip install edge-tts). إذا مش منصّبة بيرجع لصوت Google
import asyncio

try:
    import edge_tts
except ImportError:
    # مش منصّبة: ننصّبها لحالنا أول مرة (بدك إنترنت)
    print("[عم أنصّب مكتبة الصوت edge-tts... استنى شوي]")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "edge-tts"])
        import edge_tts
    except Exception as e:
        print(f"[ما قدرت أنصّب edge-tts] {type(e).__name__}: {e}")
        edge_tts = None

# ---------------------------------------------------------------
# إعدادات الترميز (عشان العربي يطلع صح بالـ cmd)
# ---------------------------------------------------------------
# لما يشتغل بالخلفية (pythonw) ما في شاشة: منحوّل كل الطباعة لملف عشان نشوف الأخطاء إذا صار شي
HEADLESS = sys.stdout is None
if HEADLESS:
    _log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_output.log")
    sys.stdout = sys.stderr = open(_log_path, "w", encoding="utf-8", buffering=1)

if os.name == "nt" and not HEADLESS:
    os.system("chcp 65001 > nul")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ---------------------------------------------------------------
# الإعدادات
# ---------------------------------------------------------------
# حط مفتاح Groq هون بين علامتي التنصيص.
# أو (أسهل): اعمل ملف نصي اسمو groq_key.txt جنب هالملف وحط المفتاح فيه بس، وخلّي السطر هيك.
GROQ_API_KEY = "ضع_المفتاح_هنا"

# اسم المساعد (الكلمة السحرية). غيّرو من هون وبيتغير بكل مكان
ASSISTANT_NAME = "لومين"

# كل الأشكال اللي ممكن التعرف الصوتي يكتب فيها الاسم
WAKE_WORDS = ["لومين", "لومن", "لومان", "لومينا", "لومنن", "لومي",
              "lumen", "lumin", "lumine", "lumene", "loomen", "loomin"]

# بعد ما تناديه، كم ثانية يضل صاحي يسمع أسئلة بدون ما تعيد الاسم
WAKE_WINDOW = 20

# مدى التسامح مع الأخطاء بسماع الاسم (من 0 لـ 1). كل ما قلّ الرقم صار يلقط أشكال أكتر
# بس ممكن يصحى بالغلط. لو كتير بيصحى لحالو زوّدو (0.8)، ولو ما بيلقط الاسم نزّلو (0.6)
WAKE_SIMILARITY = 0.7

# ملف بيسجل فيه كل شي سمعو (افتحو بـ Notepad لتشوف شو بيكتب التعرف الصوتي)
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "heard.log")

# ملف الملاحظات الصوتية
NOTES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notes.txt")

# مدينتك (للطقس)
CITY = "عمان"

# الموديلات المفضلة (بالترتيب). البرنامج بيفحص شو متاح بحسابك فعلاً ويختار منهم
PREFERRED_MODELS = ["openai/gpt-oss-20b", "allam-2-7b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"]

# لغة التعرف على الصوت: ar-JO عربي أردني، وفيك تغيرها لـ ar-SA أو en-US
SPEECH_LANG = "ar-JO"

# ---------- إعدادات الصوت ----------
# صوت أنثوي أردني. لتشوف كل الأصوات العربية: اكتب بالـ cmd:  edge-tts --list-voices | findstr ar-
TTS_VOICE = "ar-SY-AmanyNeural"
# الرقم السالب بيبطّئ الكلام شوي وبيخليه أنعم (جرّب 0% أو -10%)
TTS_RATE = "+0%"
# النبرة: خليها 0 لصوت نقي. التعديل الكبير بيخلي الصوت أغمق ويضيف تشويش
TTS_PITCH = "+0Hz"
# مستوى الصوت: خليه 0 عشان ما يصير فيه تشويش
TTS_VOLUME = "+0%"

# اللهجة المدنية الناعمة: كل قاف (ق) بتنقرى همزة بالصوت بس (بقدر ← بأدر، قال ← آل)
# الشاشة بتضل تكتب الكلام الأصلي. اقفلها (False) إذا بدك القاف تنقرى عادي.
SOFT_QAF = False

# استثناءات: كلمات بتنقرى زي ما هي حتى مع SOFT_QAF (مثلاً كلمات دينية أو أسماء)
KEEP_QAF = ["القرآن", "قرآن", "قرءان"]

# كلمات بتنقرى بنطق معيّن (بتتطبق قبل قاعدة القاف). زيد عليها اللي بدك
PRONUNCIATION = {
    "بقدر": "بأدر",
    "بتقدر": "بتأدر",
    "تقدر": "تأدر",
    "قدرت": "أدرت",
    "قلي": "ألي",
    "قلّي": "ألّي",
}

# كلمات الإغلاق
# إغلاق البرنامج بالكامل (بعدها لازم تشغّلو من جديد)
EXIT_WORDS = ["خروج", "exit", "quit"]
EXIT_PHRASES = ["اقفل البرنامج", "سكر البرنامج", "اغلاق البرنامج"]

# توديع: بتودّعك وبترجع تنام، بس البرنامج بيضل شغال وبتقدر تناديها بأي وقت
SLEEP_WORDS = ["باي", "bye", "goodbye"]
SLEEP_PHRASES = ["مع السلامة", "الى اللقاء", "نشوفك"]

SYSTEM_PROMPT = (
    f"أنتِ {ASSISTANT_NAME}، صديقة ذكية بتحكي مع صاحبها بالصوت، بصوت أنثوي ناعم ودافي. "
    "احكي متل بنت أردنية طبيعية بتحكي مع صديقها: لهجة عفوية ودافية، بدون فصحى وبدون كلام رسمي. "
    "استخدمي كلمات متل: شو، كيف، هلأ، هيك، كتير، بدك، بتحب، منيح، تمام، أكيد، يلا، ولا يهمك. "
    "ممنوع تستخدمي كلمات رسمية متل: ماذا، يمكنني، هل تود، بتفضل. "
    "مثلاً بدل (شو بتفضل) قولي (شو بتحب)، وبدل (كيف يمكنني مساعدتك) قولي (شو بدك). "
    "إذا سألك شو بدنا نعمل أو شو رأيك، جاوبي برأيك واقترحي شي حلو بدل ما ترجعي السؤال عليه. "
    "جاوبي بشكل ذكي ومختصر: جملة أو جملتين، ولا تزيدي عن ثلاثين كلمة إلا إذا طلب شرحاً مفصلاً. "
    "احكي عن نفسك بصيغة المؤنث. مهما كانت لغة المستخدم ردّي بالعربية. "
    "لا تستخدمي رموز أو ماركداون أو قوائم لأن ردك رح يتحول لصوت."
)

# كلمات رسمية بتتبدّل تلقائياً بردود الذكاء الاصطناعي (بتنكتب وبتنقرى بدالها كلمة أحلى)
# زيد عليها اللي بدك: "الكلمة الرسمية": "الكلمة الأحلى"
DIALECT_FIXES = {
    "شو بتفضل": "شو بتحب",
    "ماذا تفضل": "شو بتحب",
    "بتفضل": "بتحب",
    "ماذا": "شو",
    "يمكنني": "بقدر",
    "أود": "بدي",
    "الآن": "هلأ",
    "جداً": "كتير",
    "جدا": "كتير",
}


# ---------------------------------------------------------------
# تجهيز مفتاح Groq
# ---------------------------------------------------------------
def load_api_key():
    key = GROQ_API_KEY.strip().strip('"').strip("'")
    if not key or key == "ضع_المفتاح_هنا":
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "groq_key.txt")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                key = f.read().strip().strip('"').strip("'")
    return key


api_key = load_api_key()

# فحص سريع للمفتاح (بيطبع بس أول وآخر أحرف، مش المفتاح كامل)
if not api_key.startswith("gsk_") or len(api_key) < 40:
    print("[تنبيه] المفتاح شكلو غلط أو ما انحط: لازم يبدأ بـ gsk_ وطولو حوالي 56 حرف.")
print(f"[المفتاح المستخدم]: {api_key[:8]}...{api_key[-4:]} | الطول: {len(api_key)}")

client = Groq(api_key=api_key)


def pick_models():
    """بيجيب قائمة الموديلات المتاحة بحسابك فعلاً، وبيرتبها حسب الأفضلية."""
    try:
        ids = [m.id for m in client.models.list().data]
    except Exception as e:
        print(f"[MODELS LIST ERROR] {type(e).__name__}: {e}")
        return PREFERRED_MODELS

    skip = ("whisper", "tts", "guard", "orpheus", "playai", "embed")
    chat_models = [i for i in ids if not any(s in i.lower() for s in skip)]
    ordered = [m for m in PREFERRED_MODELS if m in chat_models]
    ordered += [m for m in chat_models if m not in ordered]
    return ordered or PREFERRED_MODELS


MODELS = pick_models()
print(f"[الموديلات اللي رح أستخدمها]: {MODELS}")

# ذاكرة المحادثة (عشان يتذكر شو حكيتو قبل شوي)
history = [{"role": "system", "content": SYSTEM_PROMPT}]
MAX_HISTORY = 12


# ---------------------------------------------------------------
# معالجة النص (الكلمة السحرية والإغلاق)
# ---------------------------------------------------------------
def normalize(text):
    """بيوحّد شكل الكلام: بيشيل التشكيل وعلامات الترقيم وبيوحّد الهمزات."""
    text = text.lower()
    text = re.sub(r"[\u064B-\u065F\u0670]", "", text)
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه")):
        text = text.replace(a, b)
    text = re.sub(r"[^\w\s]", " ", text)
    return text


WAKE_SET = {normalize(w).strip() for w in WAKE_WORDS}
FILLER_SET = {"يا", "هاي", "هلا", "هلو", "اهلا"}
EXIT_SET = {normalize(w).strip() for w in EXIT_WORDS}
EXIT_PHRASES_N = [normalize(p).strip() for p in EXIT_PHRASES]
SLEEP_SET = {normalize(w).strip() for w in SLEEP_WORDS}
SLEEP_PHRASES_N = [normalize(p).strip() for p in SLEEP_PHRASES]


def is_wake_word(word):
    """بيقارن الكلمة مع الاسم، وبيتسامح مع أخطاء السمع الصغيرة."""
    w = normalize(word).strip()
    if len(w) < 3:
        return False
    if w in WAKE_SET:
        return True
    return any(SequenceMatcher(None, w, k).ratio() >= WAKE_SIMILARITY for k in WAKE_SET)


def strip_wake_word(text):
    """بيرجع (انتادى الاسم؟، الكلام بعد شيل الاسم)."""
    words = text.split()
    found = any(is_wake_word(w) for w in words)
    if not found:
        return False, text.strip()
    remaining = [
        w for w in words
        if not is_wake_word(w) and normalize(w).strip() not in FILLER_SET
    ]
    return True, " ".join(remaining).strip()


def is_exit(text):
    norm = normalize(text)
    if set(norm.split()) & EXIT_SET:
        return True
    return any(p in norm for p in EXIT_PHRASES_N)


def is_sleep(text):
    norm = normalize(text)
    if set(norm.split()) & SLEEP_SET:
        return True
    return any(p in norm for p in SLEEP_PHRASES_N)


# ---------------------------------------------------------------
# الصوت
# ---------------------------------------------------------------
def soften(text):
    """بيبدّل كلمات معينة بنطقها الناعم (للصوت بس، مش للشاشة)."""
    # لما SOFT_QAF مقفول بتنقرى الكلمات زي ما هي بدون أي تبديل
    if not SOFT_QAF:
        return text

    for word, soft in PRONUNCIATION.items():
        text = re.sub(rf"\b{re.escape(word)}\b", soft, text)

    if SOFT_QAF:
        # نحمي الكلمات المستثناة، نبدّل كل قاف بهمزة، وبعدين نرجّع المحميات
        keep = {}
        for i, w in enumerate(KEEP_QAF):
            token = f"\u0001{i}\u0001"
            keep[token] = w
            text = text.replace(w, token)
        text = text.replace("ق", "أ")
        for token, w in keep.items():
            text = text.replace(token, w)
    return text


def speak(text):
    print(f"\n{ASSISTANT_NAME}: {text}")
    audio_file = os.path.join(tempfile.gettempdir(), f"assistant_{uuid.uuid4().hex}.mp3")
    voice_text = soften(text)
    try:
        saved = False
        if edge_tts is not None:
            try:
                communicate = edge_tts.Communicate(
                    voice_text, TTS_VOICE, rate=TTS_RATE, pitch=TTS_PITCH, volume=TTS_VOLUME
                )
                asyncio.run(communicate.save(audio_file))
                saved = True
            except Exception as e:
                print(f"[EDGE-TTS ERROR] {type(e).__name__}: {e} (برجع لصوت Google)")
        if not saved:
            gTTS(text=voice_text, lang="ar", slow=False).save(audio_file)
        playsound(audio_file)
    except Exception as e:
        print(f"[AUDIO ERROR] {type(e).__name__}: {e}")
    finally:
        try:
            if os.path.exists(audio_file):
                os.remove(audio_file)
        except Exception:
            pass


recognizer = sr.Recognizer()
# كم ثانية سكوت بعد ما تخلص حكي قبل ما تبدأ تفهم (الافتراضي 0.8). أقل = أسرع، بس لا تنزلو عن 0.5
recognizer.pause_threshold = 0.6


def listen(source, awake):
    if awake:
        print("\n[صاحي وسامعك... احكي]")
    else:
        print(".", end="", flush=True)

    try:
        audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
    except sr.WaitTimeoutError:
        return ""
    except Exception as e:
        print(f"\n[MIC ERROR] {type(e).__name__}: {e}")
        return ""

    try:
        command = recognizer.recognize_google(audio, language=SPEECH_LANG)
        print(f"\nانت قلت: {command}")
        print(f"   [للتشخيص] {ascii(command)}")
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%H:%M:%S')}  {command}\n")
        except Exception:
            pass
        return command
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        print(f"\n[SPEECH SERVICE ERROR] {e}")
        return ""
    except Exception as e:
        print(f"\n[RECOGNIZE ERROR] {type(e).__name__}: {e}")
        return ""


# ---------------------------------------------------------------
# الذكاء الاصطناعي
# ---------------------------------------------------------------
def fix_dialect(text):
    """بيبدّل الكلمات الرسمية بكلمات أحلى بلهجة عفوية."""
    for formal, casual in DIALECT_FIXES.items():
        text = re.sub(rf"(?<!\w){re.escape(formal)}(?!\w)", casual, text)
    return text


def ask_assistant(prompt):
    history.append({"role": "user", "content": prompt})

    for model in MODELS:
        try:
            # موديلات gpt-oss بتفكر قبل ما ترد، فنخلّي التفكير خفيف عشان ترد أسرع
            extra = {"extra_body": {"reasoning_effort": "low"}} if "gpt-oss" in model else {}
            completion = client.chat.completions.create(
                messages=history,
                model=model,
                max_tokens=400,
                **extra,
            )
            reply = fix_dialect((completion.choices[0].message.content or "").strip())
            if not reply:
                raise ValueError("الموديل رجّع رد فاضي")
            history.append({"role": "assistant", "content": reply})

            # نحافظ على حجم الذاكرة (نبقي رسالة النظام + آخر المحادثات)
            if len(history) > MAX_HISTORY + 1:
                del history[1:len(history) - MAX_HISTORY]
            return reply
        except Exception as e:
            print(f"\n[GROQ ERROR] model={model} | {type(e).__name__}: {e}")

    # فشلت كل الموديلات: نشيل آخر رسالة للمستخدم من الذاكرة
    history.pop()
    return "آسفة، صار خطأ بالاتصال. شوف الخطأ المكتوب بالشاشة."


# ---------------------------------------------------------------
# الأوامر (بتتنفذ على الجهاز بدون ما تروح للذكاء الاصطناعي)
# ---------------------------------------------------------------
IS_WIN = os.name == "nt"
timers = []

VK_VOLUME_MUTE, VK_VOLUME_DOWN, VK_VOLUME_UP = 0xAD, 0xAE, 0xAF
VK_MEDIA_NEXT, VK_MEDIA_PREV, VK_MEDIA_PLAY_PAUSE = 0xB0, 0xB1, 0xB3

DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
MONTHS = ["كانون الثاني", "شباط", "آذار", "نيسان", "أيار", "حزيران",
          "تموز", "آب", "أيلول", "تشرين الأول", "تشرين الثاني", "كانون الأول"]

OPEN_VERBS = ["افتح", "افتحلي", "فتح", "شغل", "شغلي", "وديني", "روح", "اطلع", "طلعلي"]
PLAY_VERBS = ["شغل", "شغلي", "play", "سمعني", "سمعيني"]

# المواقع (الترتيب مهم: الأخص قبل الأعم)
SITES = [
    (["خرائط", "الخرائط", "maps"], "https://www.google.com/maps", "خرائط جوجل"),
    (["جيميل", "gmail", "ايميل"], "https://mail.google.com", "جيميل"),
    (["يوتيوب", "يوتوب", "youtube"], "https://www.youtube.com", "يوتيوب"),
    (["فيسبوك", "فيس بوك", "facebook"], "https://www.facebook.com", "فيسبوك"),
    (["انستغرام", "انستقرام", "انستا", "instagram"], "https://www.instagram.com", "انستغرام"),
    (["واتساب", "واتس اب", "واتس", "whatsapp"], "https://web.whatsapp.com", "واتساب"),
    (["تويتر", "twitter"], "https://x.com", "تويتر"),
    (["تيك توك", "تيكتوك", "tiktok"], "https://www.tiktok.com", "تيك توك"),
    (["لينكدان", "لينكد ان", "linkedin"], "https://www.linkedin.com", "لينكد إن"),
    (["تلغرام", "تيليجرام", "telegram"], "https://web.telegram.org", "تلغرام"),
    (["نتفلكس", "netflix"], "https://www.netflix.com", "نتفلكس"),
    (["سبوتيفاي", "spotify"], "https://open.spotify.com", "سبوتيفاي"),
    (["ريديت", "reddit"], "https://www.reddit.com", "ريديت"),
    (["ويكيبيديا", "wikipedia"], "https://ar.wikipedia.org", "ويكيبيديا"),
    (["تشات جي بي تي", "chatgpt"], "https://chatgpt.com", "تشات جي بي تي"),
    (["كلود", "claude"], "https://claude.ai", "كلود"),
    (["جوجل", "قوقل", "غوغل", "google"], "https://www.google.com", "جوجل"),
]

# البرامج
APPS = [
    (["حاسبة", "الآلة الحاسبة", "calculator", "calc"], "calc.exe", "الآلة الحاسبة"),
    (["مفكرة", "نوت باد", "notepad"], "notepad.exe", "المفكرة"),
    (["رسام", "paint"], "mspaint.exe", "الرسام"),
    (["مدير المهام", "task manager"], "taskmgr.exe", "مدير المهام"),
    (["اعدادات", "إعدادات", "settings"], "ms-settings:", "الإعدادات"),
    (["كاميرا", "camera"], "microsoft.windows.camera:", "الكاميرا"),
    (["وورد", "word"], "winword.exe", "وورد"),
    (["اكسل", "excel"], "excel.exe", "إكسل"),
    (["باوربوينت", "powerpoint"], "powerpnt.exe", "باوربوينت"),
    (["كروم", "chrome"], "chrome.exe", "كروم"),
    (["ايدج", "edge"], "msedge.exe", "إيدج"),
    (["سطر الاوامر", "cmd"], "cmd.exe", "سطر الأوامر"),
    (["مستكشف الملفات", "explorer"], "explorer.exe", "مستكشف الملفات"),
]

# المجلدات
FOLDERS = [
    (["تنزيلات", "تحميلات", "downloads"], "shell:Downloads", "التنزيلات"),
    (["مستندات", "وثائق", "documents"], "shell:Personal", "المستندات"),
    (["سطح المكتب", "desktop"], "shell:Desktop", "سطح المكتب"),
    (["صور", "pictures"], "shell:My Pictures", "الصور"),
]

NUM_WORDS = {
    "واحد": 1, "واحده": 1, "اثنين": 2, "اتنين": 2, "اثنان": 2,
    "ثلاث": 3, "ثلاثه": 3, "تلات": 3, "تلاته": 3, "اربع": 4, "اربعه": 4,
    "خمس": 5, "خمسه": 5, "ست": 6, "سته": 6, "سبع": 7, "سبعه": 7,
    "ثمان": 8, "ثمانيه": 8, "تمان": 8, "تمانيه": 8, "تسع": 9, "تسعه": 9,
    "عشر": 10, "عشره": 10, "عشرين": 20, "ثلاثين": 30, "تلاتين": 30,
    "اربعين": 40, "خمسين": 50, "ستين": 60,
}


def press_key(vk, times=1):
    """بيضغط زر من أزرار الكيبورد الخاصة (صوت / ميديا)."""
    if not IS_WIN:
        return False
    import ctypes
    for _ in range(times):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
        time.sleep(0.02)
    return True


def press_ctrl_w():
    """بيضغط Ctrl+W عشان يسكّر التاب الشغال بالمتصفح."""
    if not IS_WIN:
        return False
    import ctypes
    VK_CONTROL, VK_W = 0x11, 0x57
    u = ctypes.windll.user32
    u.keybd_event(VK_CONTROL, 0, 0, 0)
    u.keybd_event(VK_W, 0, 0, 0)
    u.keybd_event(VK_W, 0, 2, 0)
    u.keybd_event(VK_CONTROL, 0, 2, 0)
    return True


def launch(target):
    """بيفتح برنامج أو مجلد على ويندوز."""
    if not IS_WIN:
        return False
    try:
        if target.startswith("shell:"):
            subprocess.Popen(["explorer.exe", target])
        else:
            os.startfile(target)
        return True
    except Exception as e:
        print(f"[LAUNCH ERROR] {target}: {type(e).__name__}: {e}")
        return False


def words_of(text):
    norm = " ".join(normalize(text).split())
    words = set(norm.split())
    words |= {w[2:] for w in list(words) if w.startswith("ال") and len(w) > 4}
    return norm, words


def has(norm, words, *keys):
    """هل النص فيه وحدة من هالكلمات أو العبارات؟"""
    for k in keys:
        kn = " ".join(normalize(k).split())
        if " " in kn:
            if f" {kn} " in f" {norm} ":
                return True
        elif kn in words:
            return True
    return False


def rest_after(text, triggers, max_index=None):
    """بيرجع الكلمات اللي بعد أول كلمة تطابق وحدة من triggers (أو None)."""
    trig = {normalize(t).strip() for t in triggers}
    parts = text.split()
    for i, w in enumerate(parts):
        if max_index is not None and i > max_index:
            break
        if normalize(w).strip() in trig:
            return parts[i + 1:]
    return None


def clean_query(parts, noise):
    """بيشيل كلمات الحشو من أول الجملة بس (عشان ما نخرّب كلام الباحث)."""
    noise_n = {normalize(n).strip() for n in noise}
    i = 0
    while i < len(parts) and normalize(parts[i]).strip() in noise_n:
        i += 1
    return " ".join(parts[i:]).strip()


def parse_duration(norm):
    """بيحوّل 'خمس دقايق' أو '10 دقائق' أو 'نص ساعة' لثواني."""
    for k, v in {
        "خمسه عشر": "15", "خمسطعش": "15", "خمستعش": "15",
        "نص ساعه": "30 دقيقه", "نصف ساعه": "30 دقيقه", "ربع ساعه": "15 دقيقه",
        "ساعتين": "2 ساعه", "دقيقتين": "2 دقيقه", "ثانيتين": "2 ثانيه",
    }.items():
        norm = norm.replace(k, v)

    toks = norm.split()
    total, found = 0, False
    for i, t in enumerate(toks):
        if t.startswith("ساع"):
            unit = 3600
        elif t.startswith(("دقيق", "دقا")):
            unit = 60
        elif t.startswith(("ثاني", "ثوان")):
            unit = 1
        else:
            continue
        val = 1
        if i > 0:
            prev = toks[i - 1]
            if prev.isdigit():
                val = int(prev)
            elif prev in NUM_WORDS:
                val = NUM_WORDS[prev]
        total += val * unit
        found = True
    return total if found else 0


def unit_label(n, one, two, few, many):
    """صيغة العدد بالعربي: دقيقة / دقيقتين / 5 دقائق / 12 دقيقة."""
    if n == 1:
        return one
    if n == 2:
        return two
    if 3 <= n <= 10:
        return f"{n} {few}"
    return f"{n} {many}"


def format_duration(seconds):
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(unit_label(h, "ساعة", "ساعتين", "ساعات", "ساعة"))
    if m:
        parts.append(unit_label(m, "دقيقة", "دقيقتين", "دقائق", "دقيقة"))
    if s:
        parts.append(unit_label(s, "ثانية", "ثانيتين", "ثواني", "ثانية"))
    return " و ".join(parts)


def start_timer(seconds):
    label = format_duration(seconds)

    def done():
        speak(f"انتهى المؤقت. مرّت {label}.")

    t = threading.Timer(seconds, done)
    t.daemon = True
    t.start()
    timers.append(t)


def play_music(parts):
    q = clean_query(parts, ["اغنية", "اغاني", "موسيقى", "فيديو", "مقطع",
                            "لي", "على", "علي", "يوتيوب", "من", "ع"])
    if not q:
        return "شو بدك أشغّلك؟"
    webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote(q))
    return f"فتحتلك نتائج {q} على يوتيوب. اختار اللي بدك ياه."


def try_command(text):
    """بيرجع ردّ لو الكلام أمر وانفّذ، أو None لو لازم يروح للذكاء الاصطناعي."""
    norm, words = words_of(text)
    tokens = norm.split()

    # ---------- الجهاز: إغلاق / إعادة تشغيل / قفل ----------
    if has(norm, words, "الغي الاغلاق", "الغ الاغلاق", "الغاء الاغلاق",
           "الغي الاطفاء", "وقف الاغلاق", "cancel shutdown"):
        if IS_WIN:
            subprocess.run(["shutdown", "/a"], capture_output=True)
        return "تمام، ألغيت الإغلاق."

    if has(norm, words, "اطفي الجهاز", "اطفي الكمبيوتر", "اطفي اللابتوب", "اطفي الابتوب",
           "اطفئ الجهاز", "اغلاق الجهاز", "شات داون", "shutdown"):
        if IS_WIN:
            subprocess.Popen(["shutdown", "/s", "/t", "30"])
        return "رح أطفي الجهاز بعد ثلاثين ثانية. إذا غيّرت رأيك قول: الغي الإغلاق."

    if has(norm, words, "اعد تشغيل الجهاز", "اعمل ريستارت", "ريستارت", "restart"):
        if IS_WIN:
            subprocess.Popen(["shutdown", "/r", "/t", "30"])
        return "رح أعيد تشغيل الجهاز بعد ثلاثين ثانية. إذا غيّرت رأيك قول: الغي الإغلاق."

    if has(norm, words, "اقفل الجهاز", "قفل الجهاز", "اقفل الشاشة", "قفل الشاشة", "lock"):
        if IS_WIN:
            subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"])
        return "تمام، قفلت الجهاز."

    # ---------- سكّر برنامج أو موقع ----------
    if has(norm, words, "سكر", "سكري", "اغلق", "اغلقي", "اقفل", "اقفلي"):
        # برنامج معيّن: بنطلب منو يسكّر بلطف (إذا في ملف مش محفوظ بيسألك)
        for keys, target, name in APPS:
            if target.endswith(".exe") and target != "explorer.exe" and has(norm, words, *keys):
                if not IS_WIN:
                    return f"ما قدرت أسكّر {name}."
                res = subprocess.run(["taskkill", "/im", target], capture_output=True)
                if res.returncode == 0:
                    return f"تمام، سكرت {name}."
                return f"ما لقيت {name} شغّال."
        # موقع أو تاب: بنسكّر التاب الشغال بالمتصفح
        site_hit = any(has(norm, words, *keys) for keys, _, _ in SITES)
        if site_hit or has(norm, words, "تاب", "التاب", "صفحه", "الصفحه", "موقع", "الموقع"):
            if press_ctrl_w():
                return "تمام، سكرت الصفحة."
            return "ما قدرت أسكّر الصفحة."

    # ---------- لقطة شاشة ----------
    if has(norm, words, "لقطة شاشة", "لقطة للشاشة", "سكرين شوت", "screenshot",
           "صور الشاشة", "خذ لقطة"):
        if launch("ms-screenclip:"):
            return "جاهزة، حددلي المنطقة اللي بدك تصورها."
        return "ما قدرت أفتح أداة لقطة الشاشة."

    # ---------- الصوت ----------
    if has(norm, words, "كتم", "اكتم", "ميوت", "mute", "الغاء الكتم", "فك الكتم"):
        press_key(VK_VOLUME_MUTE)
        return "تمام."

    if "صوت" in words:
        m = re.search(r"\d+", norm)
        times = max(1, min(int(m.group()) // 2, 50)) if m else 5
        if has(norm, words, "ارفع", "رفع", "زيد", "زود", "اعلى", "عالي", "كبر"):
            press_key(VK_VOLUME_UP, times)
            return "رفعت الصوت."
        if has(norm, words, "خفض", "اخفض", "نزل", "وطي", "قلل", "خفف"):
            press_key(VK_VOLUME_DOWN, times)
            return "خفضت الصوت."

    # ---------- التحكم بالموسيقى ----------
    if has(norm, words, "pause", "resume", "بوز", "وقف الموسيقى", "وقف الاغنية",
           "اوقف الموسيقى", "اوقف الاغنية", "ايقاف مؤقت", "كمل الموسيقى",
           "كمل الاغنية", "استئناف"):
        press_key(VK_MEDIA_PLAY_PAUSE)
        return "تمام."
    if has(norm, words, "الاغنية التالية", "الاغنية الجاية", "التالي", "next",
           "غير الاغنية", "بدل الاغنية"):
        press_key(VK_MEDIA_NEXT)
        return "تمام."
    if has(norm, words, "الاغنية السابقة", "السابق", "previous", "رجع الاغنية"):
        press_key(VK_MEDIA_PREV)
        return "تمام."

    # ---------- المؤقت ----------
    if has(norm, words, "الغي المؤقت", "الغاء المؤقت", "الغ المؤقت", "وقف المؤقت",
           "الغي التايمر", "cancel timer"):
        for t in timers:
            t.cancel()
        timers.clear()
        return "ألغيت كل المؤقتات."

    if has(norm, words, "مؤقت", "موقت", "تايمر", "timer", "نبهني", "ذكرني", "منبه"):
        secs = parse_duration(norm)
        if not secs:
            return "قلي المدة، مثلاً: مؤقت خمس دقائق."
        start_timer(secs)
        return f"تمام، رح أنبهك بعد {format_duration(secs)}."

    # ---------- الملاحظات ----------
    if has(norm, words, "ملاحظة") and has(norm, words, "سجل", "سجلي", "اكتب", "دون", "احفظ"):
        parts = rest_after(text, ["ملاحظة"]) or []
        note = clean_query(parts, ["ان", "انو", "هي", "هاي"])
        if not note:
            return "شو بدك أسجل بالملاحظة؟"
        with open(NOTES_PATH, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M')}  {note}\n")
        return "سجلت الملاحظة."

    if words & {"ملاحظاتي", "ملاحظات"}:
        if not os.path.exists(NOTES_PATH):
            return "ما عندك ملاحظات مسجلة."
        with open(NOTES_PATH, encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        if not lines:
            return "ما عندك ملاحظات مسجلة."
        last = [l.split("  ", 1)[-1] for l in lines[-3:]]
        return "آخر ملاحظاتك: " + ". ".join(last)

    # ---------- إدارة المحادثة والمساعدة ----------
    if has(norm, words, "انسى المحادثة", "امسح الذاكرة", "امسح المحادثة",
           "ابدا من جديد", "انسى كل شي"):
        del history[1:]
        return "تمام، بديت صفحة جديدة."

    if has(norm, words, "شو بتقدر تعمل", "شو بتعمل", "شو بتقدر", "ايش بتقدر",
           "شو تقدر تعمل", "الاوامر", "اوامر", "مساعدة", "help"):
        return ("بقدر أفتح مواقع وبرامج ومجلدات، وأبحث بجوجل، وأشغّل أغاني على يوتيوب، "
                "وأتحكم بالصوت والموسيقى، وأحط مؤقت، وأسجل ملاحظات، وأقولك الوقت والتاريخ والطقس، "
                "وأسكّر المواقع والبرامج، وأقفل الجهاز أو أطفيه. وأي سؤال ثاني بجاوبك عليه.")

    # ---------- بحث ----------
    parts = rest_after(text, ["ابحث", "ابحثي", "دور", "فتش", "بحث", "search"], max_index=1)
    if parts is not None:
        on_youtube = has(norm, words, "يوتيوب", "youtube")
        q = clean_query(parts, ["عن", "في", "على", "علي", "ع", "جوجل", "قوقل", "غوغل",
                                "لي", "بجوجل", "يوتيوب", "youtube", "ب"])
        # نشيل "على يوتيوب" / "بجوجل" من آخر الجملة
        q_parts = q.split()
        site_words = {normalize(w).strip() for w in
                      ["يوتيوب", "youtube", "جوجل", "قوقل", "غوغل", "بجوجل", "ليوتيوب"]}
        if q_parts and normalize(q_parts[-1]).strip() in site_words:
            q_parts.pop()
            while q_parts and normalize(q_parts[-1]).strip() in {"على", "علي", "في", "ع", "ب"}:
                q_parts.pop()
        q = " ".join(q_parts).strip()
        if not q:
            return "شو بدك أبحث عنو؟"
        if on_youtube:
            url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(q)
            reply = f"تمام، عم أبحث عن {q} على يوتيوب."
        else:
            url = "https://www.google.com/search?q=" + urllib.parse.quote(q)
            reply = f"تمام، عم أبحث عن {q}."
        webbrowser.open(url)
        return reply

    # ---------- الوقت والتاريخ والطقس ----------
    if has(norm, words, "كم الساعة", "الساعة كم", "شو الساعة", "ايش الساعة", "قديش الساعة",
           "الساعة قديش", "كم الوقت", "شو الوقت", "الوقت كم"):
        now = datetime.datetime.now()
        h12 = now.hour % 12 or 12
        if now.hour < 5:
            period = "ليلاً"
        elif now.hour < 12:
            period = "صباحاً"
        elif now.hour < 17:
            period = "بعد الظهر"
        elif now.hour < 21:
            period = "مساءً"
        else:
            period = "ليلاً"
        if now.minute == 0:
            return f"الساعة الآن {h12} تماماً {period}."
        return f"الساعة الآن {h12} و {now.minute} دقيقة {period}."

    if has(norm, words, "اي يوم", "شو اليوم", "ايش اليوم", "شو التاريخ", "ايش التاريخ",
           "تاريخ اليوم", "التاريخ اليوم", "كم التاريخ"):
        now = datetime.datetime.now()
        return f"اليوم {DAYS[now.weekday()]}، {now.day} {MONTHS[now.month - 1]} {now.year}."

    if "طقس" in words:
        filler = {"شو", "ايش", "كيف", "كيفه", "الطقس", "طقس", "اليوم", "الان", "هلق",
                  "هسا", "بكره", "غدا", "الجو", "جو", "اليوم"}
        extra = [t for t in tokens if t not in filler and t[2:] not in filler]
        q = f"الطقس في {CITY}" if not extra else text
        webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(q))
        return "فتحتلك الطقس بالمتصفح."

    # ---------- تشغيل أغنية ----------
    play_parts = rest_after(text, PLAY_VERBS, max_index=1)
    if play_parts is not None and has(norm, words, "اغنية", "اغاني", "موسيقى", "مقطع", "فيديو"):
        return play_music(play_parts)

    # ---------- فتح مواقع وبرامج ومجلدات ----------
    if has(norm, words, *OPEN_VERBS):
        for keys, url, name in SITES:
            if has(norm, words, *keys):
                webbrowser.open(url)
                return f"تمام، فتحت {name}."
        for keys, target, name in APPS:
            if has(norm, words, *keys):
                if launch(target):
                    return f"تمام، فتحت {name}."
                return f"ما قدرت أفتح {name}، يمكن مش منصّب عندك."
        for keys, target, name in FOLDERS:
            if has(norm, words, *keys):
                if launch(target):
                    return f"تمام، فتحت {name}."
                return f"ما قدرت أفتح {name}."

    # "شغل كذا" وكذا مش موقع ولا برنامج: نبحث عنو بيوتيوب
    if play_parts:
        return play_music(play_parts)

    return None


# ---------------------------------------------------------------
# الحلقة الرئيسية
# ---------------------------------------------------------------
if __name__ == "__main__":
    with sr.Microphone() as mic:
        print("\n[عم أضبط مستوى الضجيج... خليك ساكت ثانيتين]")
        recognizer.adjust_for_ambient_noise(mic, duration=1.5)

        if edge_tts is None:
            print("[تنبيه] مكتبة edge-tts مش منصّبة، رح استخدم صوت Google. نصّبها بـ: pip install edge-tts")
        speak(f"أنا {ASSISTANT_NAME}، كيف بقدر أساعدك؟")
        awake_until = time.time() + WAKE_WINDOW

        while True:
            awake = time.time() < awake_until
            heard = listen(mic, awake)
            if not heard:
                continue

            called, command = strip_wake_word(heard)
            awake = time.time() < awake_until

            # نايم ولا انتادى: نتجاهل الكلام
            if not called and not awake:
                print(f"[نايم] سمعت: {heard}  (ناديني: {ASSISTANT_NAME})")
                continue

            # ناداه بس بدون سؤال
            if not command:
                speak("أيوه، أنا معك.")
                awake_until = time.time() + WAKE_WINDOW
                continue

            if is_exit(command):
                speak("تمام، رح أسكّر. مع السلامة.")
                break

            if is_sleep(command):
                speak("مع السلامة، ناديني لما تحتاجني.")
                awake_until = 0
                continue

            try:
                reply = try_command(command)
            except Exception as e:
                print(f"\n[COMMAND ERROR] {type(e).__name__}: {e}")
                reply = None
            if reply is None:
                reply = ask_assistant(command)
            speak(reply)
            awake_until = time.time() + WAKE_WINDOW
