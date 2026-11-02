"""Local VoxCPM2 output locales exposed by this build."""

LOCALES = {
    'vi-VN': ('Việt Nam', 'Xin chào, đây là giọng đọc mặc định của Film Studio.'),
    'en-US': ('Hoa Kỳ', 'Hello, this is the default voice of Film Studio.'),
    'th-TH': ('Thái Lan', 'สวัสดี นี่คือเสียงเริ่มต้นของฟิล์มสตูดิโอ'),
    'id-ID': ('Indonesia', 'Halo, ini adalah suara bawaan Film Studio.'),
    'fil-PH': ('Philippines', 'Kumusta, ito ang karaniwang boses ng Film Studio.'),
    'ms-MY': ('Malaysia', 'Hai, ini ialah suara lalai Film Studio.'),
    'hi-IN': ('Ấn Độ', 'नमस्ते, यह फ़िल्म स्टूडियो की डिफ़ॉल्ट आवाज़ है।'),
    'ja-JP': ('Nhật Bản', 'こんにちは、これはフィルムスタジオの標準音声です。'),
    'ko-KR': ('Hàn Quốc', '안녕하세요. 이것은 필름 스튜디오의 기본 음성입니다.'),
    'ar-SA': ('Ả Rập Xê Út', 'مرحباً، هذا هو الصوت الافتراضي لاستوديو الأفلام.'),
    'es-ES': ('Tây Ban Nha', 'Hola, esta es la voz predeterminada de Film Studio.'),
    'es-MX': ('Mexico', 'Hola, esta es la voz predeterminada de Film Studio.'),
    'de-DE': ('Đức', 'Hallo, dies ist die Standardstimme von Film Studio.'),
    'fr-FR': ('Pháp', 'Bonjour, voici la voix par défaut de Film Studio.'),
    'pt-BR': ('Brazil', 'Olá, esta é a voz padrão do Film Studio.'),
    'ru-RU': ('Nga', 'Здравствуйте, это голос по умолчанию Film Studio.'),
    'tr-TR': ('Thổ Nhĩ Kỳ', 'Merhaba, bu Film Studio varsayılan sesidir.'),
}

VOICE_PREVIEW_TEXT = {
    'vi-VN': 'Xin chào, đây là giọng mẫu của AI Film Studio. Mời bạn nghe thử chất giọng và nhịp đọc này.',
    'en-US': 'Hello, this is a sample voice from AI Film Studio. Please listen to the tone and pacing.',
    'th-TH': 'สวัสดี นี่คือตัวอย่างเสียงจาก AI Film Studio เชิญฟังน้ำเสียงและจังหวะการพูดนี้ได้เลย',
    'id-ID': 'Halo, ini contoh suara dari AI Film Studio. Silakan dengarkan warna suara dan tempo bicaranya.',
    'fil-PH': 'Kumusta, ito ang sample na boses mula sa AI Film Studio. Pakinggan ang tono at bilis ng pagsasalita.',
    'ms-MY': 'Helo, ini contoh suara daripada AI Film Studio. Dengarkan nada dan rentak pertuturannya.',
    'hi-IN': 'नमस्ते, यह AI Film Studio की आवाज़ का नमूना है। कृपया इसकी आवाज़ और बोलने की गति सुनें।',
    'ja-JP': 'こんにちは、AI Film Studioの音声サンプルです。声の雰囲気と話す速さをお聴きください。',
    'ko-KR': '안녕하세요, AI Film Studio 음성 샘플입니다. 목소리의 느낌과 말하는 속도를 들어 보세요.',
    'ar-SA': 'مرحباً، هذا نموذج صوت من AI Film Studio. استمع إلى نبرة الصوت وسرعة التحدث.',
    'es-ES': 'Hola, esta es una muestra de voz de AI Film Studio. Escucha el tono y el ritmo al hablar.',
    'es-MX': 'Hola, esta es una muestra de voz de AI Film Studio. Escucha el tono y el ritmo al hablar.',
    'de-DE': 'Hallo, dies ist eine Stimmprobe von AI Film Studio. Achte auf Klangfarbe und Sprechtempo.',
    'fr-FR': 'Bonjour, voici un échantillon vocal d’AI Film Studio. Écoutez le timbre et le rythme de la voix.',
    'pt-BR': 'Olá, esta é uma amostra de voz do AI Film Studio. Ouça o timbre e o ritmo da fala.',
    'ru-RU': 'Здравствуйте, это образец голоса AI Film Studio. Послушайте тембр и темп речи.',
    'tr-TR': 'Merhaba, bu AI Film Studio ses örneğidir. Ses tonunu ve konuşma hızını dinleyin.',
}


def default_sample(locale):
    return LOCALES[locale][1]


def voice_preview_sample(locale):
    return VOICE_PREVIEW_TEXT[locale]


def default_style(locale):
    if locale == 'es-MX':
        return '(A warm, clear adult voice speaking Mexican Spanish with a natural Mexican accent) '
    return '(A warm, clear adult voice with a calm and steady pace) '
