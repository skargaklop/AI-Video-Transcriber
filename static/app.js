/* ────────────────────────────────────────────────────────────
   AI Video Transcriber · app.js
   ──────────────────────────────────────────────────────────── */

class VideoTranscriber {
  constructor() {
    this.currentTaskId  = null;
    this.currentTask    = null;
    this.eventSource    = null;
    this.apiBase        = '/api';
    this.currentLang    = 'en';
    this.uiLanguages    = ['en', 'ru', 'uk'];
    this.langLabels     = { en: 'English', ru: 'Русский', uk: 'Українська' };
    this.htmlLangs      = { en: 'en', ru: 'ru', uk: 'uk' };

    /* Smart progress simulation */
    this.sp = {
      enabled: false, current: 0, target: 15,
      lastServer: 0, interval: null, startTime: null, stage: 'preparing'
    };

    this.i18n = {
      en: {
        title:                   'AI Video Transcriber',
        subtitle:                'Supports automatic transcription and AI summary for 30+ platforms',
        video_url_placeholder:   'Paste YouTube, Tiktok, Bilibili or other platform video URLs...',
        start_transcription:     'Transcribe',
        ai_settings:             'AI Settings',
        groq_transcription:      'Groq Transcription',
        groq_api_key:            'Groq API Key',
        groq_api_key_placeholder:'gsk_...',
        groq_model:              'Groq Whisper Model',
        groq_language:           'Input Language',
        groq_language_placeholder:'auto',
        groq_prompt:             'Groq Prompt',
        groq_prompt_placeholder: 'Names, topic, spelling...',
        include_timecodes:       'Include time codes',
        copy_text:               'Copy text',
        copied_text:             'Copied',
        save_text:               'Save',
        summary_provider:        'Summary Provider',
        model_base_url:          'Model API Base URL',
        model_base_url_placeholder: 'https://openrouter.ai/api/v1',
        api_key:                 'API Key',
        api_key_placeholder:     'sk-...',
        fetch_models:            'Fetch',
        model_select:            'Model',
        model_default:           '— use server default —',
        reasoning_effort:        'Reasoning',
        reasoning_auto:          'Auto',
        reasoning_none:          'None',
        reasoning_minimal:       'Minimal',
        reasoning_low:           'Low',
        reasoning_medium:        'Medium',
        reasoning_high:          'High',
        reasoning_xhigh:         'Extra high',
        summary_language:        'Summary Language',
        summary_prompt_label:    'Summary Prompt',
        summary_prompt_placeholder: 'Optional: tell the model how to summarize, e.g. "focus on action items and risks".',
        processing_progress:     'Processing',
        preparing:               'Preparing…',
        transcript_text:         'Transcript',
        intelligent_summary:     'AI Summary',
        translation:             'Translation',
        download_transcript:     'Transcript',
        download_translation:    'Translation',
        download_summary:        'Summary',
        download_summary_md:     'Summary MD',
        download_summary_html:   'Summary HTML',
        download_summary_txt:    'Summary TXT',
        output_format:           'Output Format',
        format_markdown:         'Markdown',
        format_html:             'HTML',
        format_txt:              'TXT',
        format_both:             'Markdown + HTML',
        generate_summary:        'Generate Summary',
        summary_waiting:         'Transcript is ready. Generate the summary when you want to send it to the summary provider.',
        generating_summary_btn:  'Generating...',
        empty_hint:              'Paste a video URL above and let AI do the heavy lifting.',
        processing:              'Processing…',
        downloading_video:       'Resolving audio URL…',
        parsing_video:           'Parsing video info…',
        transcribing_audio:      'Transcribing audio…',
        optimizing_transcript:   'Optimizing transcript…',
        generating_summary:      'Generating summary…',
        detecting_subtitles:     'Detecting subtitles…',
        subtitle_found:          'Subtitles found! Processing text…',
        no_subtitle:             'No subtitles found, resolving audio URL for Groq…',
        mode_subtitle:           '⚡ Subtitle',
        mode_whisper:            'Groq URL',
        mode_groq:               'Groq URL',
        completed:               'Done!',
        error_invalid_url:       'Please enter a valid video URL',
        error_processing_failed: 'Processing failed: ',
        error_no_download:       'No file available for download',
        error_download_failed:   'Download failed: ',
        fetching_models:         'Fetching models…',
        models_loaded:           (n) => `${n} models loaded`,
        models_error:            'Failed to fetch models',
      },
      ru: {
        title:                   'AI видео транскрибатор',
        subtitle:                'Автоматическая транскрибация и AI-сводки для 30+ платформ',
        video_url_placeholder:   'Вставьте ссылку на YouTube, TikTok, Bilibili или другое видео...',
        start_transcription:     'Транскрибировать',
        ai_settings:             'Настройки AI',
        groq_transcription:      'Транскрибация Groq',
        groq_api_key:            'Groq API Key',
        groq_api_key_placeholder:'gsk_...',
        groq_model:              'Модель Groq Whisper',
        groq_language:           'Язык аудио',
        groq_language_placeholder:'auto',
        groq_prompt:             'Промпт Groq',
        groq_prompt_placeholder: 'Имена, тема, термины...',
        include_timecodes:       'Добавить таймкоды',
        copy_text:               'Копировать текст',
        copied_text:             'Скопировано',
        save_text:               'Сохранить',
        summary_provider:        'Провайдер сводки',
        model_base_url:          'Base URL API модели',
        model_base_url_placeholder: 'https://openrouter.ai/api/v1',
        api_key:                 'API Key',
        api_key_placeholder:     'sk-...',
        fetch_models:            'Загрузить',
        model_select:            'Модель',
        model_default:           '-- использовать модель сервера --',
        reasoning_effort:        'Рассуждение',
        reasoning_auto:          'Авто',
        reasoning_none:          'Нет',
        reasoning_minimal:       'Минимальное',
        reasoning_low:           'Низкое',
        reasoning_medium:        'Среднее',
        reasoning_high:          'Высокое',
        reasoning_xhigh:         'Очень высокое',
        summary_language:        'Язык сводки',
        summary_prompt_label:    'Промпт сводки',
        summary_prompt_placeholder: 'Необязательно: укажите, как делать сводку, например "сфокусируйся на действиях и рисках".',
        processing_progress:     'Обработка',
        preparing:               'Подготовка...',
        transcript_text:         'Транскрипт',
        intelligent_summary:     'AI-сводка',
        translation:             'Перевод',
        download_transcript:     'Транскрипт',
        download_translation:    'Перевод',
        download_summary:        'Сводка',
        download_summary_md:     'Сводка MD',
        download_summary_html:   'Сводка HTML',
        download_summary_txt:    'Сводка TXT',
        output_format:           'Формат вывода',
        format_markdown:         'Markdown',
        format_html:             'HTML',
        format_txt:              'TXT',
        format_both:             'Markdown + HTML',
        generate_summary:        'Создать сводку',
        summary_waiting:         'Транскрипт готов. Создайте сводку, когда будете готовы отправить его провайдеру.',
        generating_summary_btn:  'Создание...',
        empty_hint:              'Вставьте ссылку на видео выше, и AI обработает его.',
        processing:              'Обработка...',
        downloading_video:       'Получение аудио URL...',
        parsing_video:           'Разбор информации о видео...',
        transcribing_audio:      'Транскрибация аудио...',
        optimizing_transcript:   'Оптимизация транскрипта...',
        generating_summary:      'Создание сводки...',
        detecting_subtitles:     'Поиск субтитров...',
        subtitle_found:          'Субтитры найдены, обрабатываю текст...',
        no_subtitle:             'Субтитры не найдены, получаю аудио URL для Groq...',
        mode_subtitle:           'Субтитры',
        mode_whisper:            'Groq URL',
        mode_groq:               'Groq URL',
        completed:               'Готово!',
        error_invalid_url:       'Введите корректную ссылку на видео',
        error_processing_failed: 'Ошибка обработки: ',
        error_no_download:       'Нет файла для скачивания',
        error_download_failed:   'Ошибка скачивания: ',
        fetching_models:         'Загрузка моделей...',
        models_loaded:           (n) => `${n} моделей загружено`,
        models_error:            'Не удалось загрузить модели',
      },
      uk: {
        title:                   'AI відео транскрибатор',
        subtitle:                'Автоматична транскрибація та AI-зведення для 30+ платформ',
        video_url_placeholder:   'Вставте посилання на YouTube, TikTok, Bilibili або інше відео...',
        start_transcription:     'Транскрибувати',
        ai_settings:             'Налаштування AI',
        groq_transcription:      'Транскрибація Groq',
        groq_api_key:            'Groq API Key',
        groq_api_key_placeholder:'gsk_...',
        groq_model:              'Модель Groq Whisper',
        groq_language:           'Мова аудіо',
        groq_language_placeholder:'auto',
        groq_prompt:             'Промпт Groq',
        groq_prompt_placeholder: 'Імена, тема, терміни...',
        include_timecodes:       'Додати таймкоди',
        copy_text:               'Копіювати текст',
        copied_text:             'Скопійовано',
        save_text:               'Зберегти',
        summary_provider:        'Провайдер зведення',
        model_base_url:          'Base URL API моделі',
        model_base_url_placeholder: 'https://openrouter.ai/api/v1',
        api_key:                 'API Key',
        api_key_placeholder:     'sk-...',
        fetch_models:            'Завантажити',
        model_select:            'Модель',
        model_default:           '-- використовувати модель сервера --',
        reasoning_effort:        'Міркування',
        reasoning_auto:          'Авто',
        reasoning_none:          'Немає',
        reasoning_minimal:       'Мінімальне',
        reasoning_low:           'Низьке',
        reasoning_medium:        'Середнє',
        reasoning_high:          'Високе',
        reasoning_xhigh:         'Дуже високе',
        summary_language:        'Мова зведення',
        summary_prompt_label:    'Промпт зведення',
        summary_prompt_placeholder: 'Необовʼязково: вкажіть, як створити зведення, наприклад "зосередься на діях і ризиках".',
        processing_progress:     'Обробка',
        preparing:               'Підготовка...',
        transcript_text:         'Транскрипт',
        intelligent_summary:     'AI-зведення',
        translation:             'Переклад',
        download_transcript:     'Транскрипт',
        download_translation:    'Переклад',
        download_summary:        'Зведення',
        download_summary_md:     'Зведення MD',
        download_summary_html:   'Зведення HTML',
        download_summary_txt:    'Зведення TXT',
        output_format:           'Формат виводу',
        format_markdown:         'Markdown',
        format_html:             'HTML',
        format_txt:              'TXT',
        format_both:             'Markdown + HTML',
        generate_summary:        'Створити зведення',
        summary_waiting:         'Транскрипт готовий. Створіть зведення, коли будете готові надіслати його провайдеру.',
        generating_summary_btn:  'Створення...',
        empty_hint:              'Вставте посилання на відео вище, і AI обробить його.',
        processing:              'Обробка...',
        downloading_video:       'Отримання аудіо URL...',
        parsing_video:           'Розбір інформації про відео...',
        transcribing_audio:      'Транскрибація аудіо...',
        optimizing_transcript:   'Оптимізація транскрипту...',
        generating_summary:      'Створення зведення...',
        detecting_subtitles:     'Пошук субтитрів...',
        subtitle_found:          'Субтитри знайдено, обробляю текст...',
        no_subtitle:             'Субтитри не знайдено, отримую аудіо URL для Groq...',
        mode_subtitle:           'Субтитри',
        mode_whisper:            'Groq URL',
        mode_groq:               'Groq URL',
        completed:               'Готово!',
        error_invalid_url:       'Введіть коректне посилання на відео',
        error_processing_failed: 'Помилка обробки: ',
        error_no_download:       'Немає файлу для завантаження',
        error_download_failed:   'Помилка завантаження: ',
        fetching_models:         'Завантаження моделей...',
        models_loaded:           (n) => `${n} моделей завантажено`,
        models_error:            'Не вдалося завантажити моделі',
      },
      zh: {
        title:                   'AI 视频转录器',
        subtitle:                '粘贴 YouTube、TikTok 或任意公开视频链接，获取转录文本和 AI 摘要。',
        video_url_placeholder:   '请输入视频链接…',
        start_transcription:     '开始转录',
        ai_settings:             'AI 设置',
        groq_transcription:      'Groq 转录',
        groq_api_key:            'Groq API Key',
        groq_api_key_placeholder:'gsk_...',
        groq_model:              'Groq Whisper 模型',
        groq_language:           '输入语言',
        groq_language_placeholder:'auto',
        groq_prompt:             'Groq 提示词',
        groq_prompt_placeholder: '名称、主题、拼写...',
        summary_provider:        '摘要模型',
        model_base_url:          'Model API 地址',
        model_base_url_placeholder: 'https://openrouter.ai/api/v1',
        api_key:                 'API Key',
        api_key_placeholder:     'sk-...',
        fetch_models:            '获取',
        model_select:            '模型',
        model_default:           '— 使用服务器默认 —',
        reasoning_effort:        '推理强度',
        reasoning_auto:          '自动',
        reasoning_none:          '无',
        reasoning_minimal:       '最小',
        reasoning_low:           '低',
        reasoning_medium:        '中',
        reasoning_high:          '高',
        reasoning_xhigh:         '超高',
        summary_language:        '摘要语言',
        summary_prompt_label:    '摘要提示词',
        summary_prompt_placeholder: '可选：告诉模型如何摘要，例如“重点总结行动项和风险”。',
        processing_progress:     '处理进度',
        preparing:               '准备中…',
        transcript_text:         '转录文本',
        intelligent_summary:     '智能摘要',
        translation:             '翻译',
        download_transcript:     '转录',
        download_translation:    '翻译',
        download_summary:        '摘要',
        download_summary_md:     '摘要 MD',
        download_summary_html:   '摘要 HTML',
        download_summary_txt:    '摘要 TXT',
        output_format:           '输出格式',
        format_markdown:         'Markdown',
        format_html:             'HTML',
        format_txt:              'TXT',
        format_both:             'Markdown + HTML',
        generate_summary:        '生成摘要',
        summary_waiting:         '转录已完成。确认后再发送给摘要模型。',
        generating_summary_btn:  '生成中...',
        empty_hint:              '在上方粘贴视频链接，让 AI 来处理一切。',
        processing:              '处理中…',
        downloading_video:       '正在解析音频 URL…',
        parsing_video:           '正在解析视频信息…',
        transcribing_audio:      '正在转录音频…',
        optimizing_transcript:   '正在优化转录文本…',
        generating_summary:      '正在生成摘要…',
        detecting_subtitles:     '正在检测字幕…',
        subtitle_found:          '字幕获取成功！正在处理文本…',
        no_subtitle:             '未找到字幕，正在解析 Groq 音频 URL…',
        mode_subtitle:           '⚡ 字幕模式',
        mode_whisper:            'Groq URL',
        mode_groq:               'Groq URL',
        completed:               '处理完成！',
        error_invalid_url:       '请输入有效的视频链接',
        error_processing_failed: '处理失败：',
        error_no_download:       '没有可下载的文件',
        error_download_failed:   '下载失败：',
        fetching_models:         '正在获取模型列表…',
        models_loaded:           (n) => `已加载 ${n} 个模型`,
        models_error:            '获取模型失败',
      }
    };

    this._initElements();
    this._bindEvents();
    this._loadSettings();
    this._switchLang(this._savedUiLang || 'en');
    this._updateReasoningAvailability();
  }

  /* ── Elements ─────────────────────────────────────────── */
  _initElements() {
    this.form               = document.getElementById('videoForm');
    this.videoUrlInput      = document.getElementById('videoUrl');
    this.submitBtn          = document.getElementById('submitBtn');
    this.summaryLangSel     = document.getElementById('summaryLanguage');
    this.langSwitcher       = document.getElementById('langSwitcher');
    this.langToggle         = document.getElementById('langToggle');
    this.langText           = document.getElementById('langText');
    this.langMenu           = document.getElementById('langMenu');
    this.langOptions        = Array.from(document.querySelectorAll('.lang-option'));
    this.errorBanner        = document.getElementById('errorBanner');
    this.errorMsg           = document.getElementById('errorMsg');
    this.emptyState         = document.getElementById('emptyState');
    this.progressPanel      = document.getElementById('progressPanel');
    this.modeBadge          = document.getElementById('modeBadge');
    this.progressStatus     = document.getElementById('progressStatus');
    this.progressFill       = document.getElementById('progressFill');
    this.progressMessage    = document.getElementById('progressMessage');
    this.resultsPanel       = document.getElementById('resultsPanel');
    this.scriptContent      = document.getElementById('scriptContent');
    this.copyTranscriptTop  = document.getElementById('copyTranscriptTop');
    this.copyTranscriptBottom = document.getElementById('copyTranscriptBottom');
    this.saveTranscriptTop  = document.getElementById('saveTranscriptTop');
    this.saveTranscriptBottom = document.getElementById('saveTranscriptBottom');
    this.saveTranscriptFormatTop = document.getElementById('saveTranscriptFormatTop');
    this.saveTranscriptFormatBottom = document.getElementById('saveTranscriptFormatBottom');
    this.summaryContent     = document.getElementById('summaryContent');
    this.summaryPrompt      = document.getElementById('summaryPrompt');
    this.summaryActionsTop  = document.getElementById('summaryActionsTop');
    this.summaryActionsBottom = document.getElementById('summaryActionsBottom');
    this.copySummaryTop     = document.getElementById('copySummaryTop');
    this.copySummaryBottom  = document.getElementById('copySummaryBottom');
    this.saveSummaryTop     = document.getElementById('saveSummaryTop');
    this.saveSummaryBottom  = document.getElementById('saveSummaryBottom');
    this.saveSummaryFormatTop = document.getElementById('saveSummaryFormatTop');
    this.saveSummaryFormatBottom = document.getElementById('saveSummaryFormatBottom');
    this.translationContent = document.getElementById('translationContent');
    this.dlTranslation      = document.getElementById('downloadTranslation');
    this.dlSummary          = document.getElementById('downloadSummary');
    this.dlSummaryHtml      = document.getElementById('downloadSummaryHtml');
    this.dlSummaryTxt       = document.getElementById('downloadSummaryTxt');
    this.generateSummaryBtn = document.getElementById('generateSummary');
    this.summaryFormatSel   = document.getElementById('summaryFormat');
    this.summaryPromptInput = document.getElementById('summaryPromptInput');
    this.translationTabBtn  = document.getElementById('translationTabBtn');
    this.tabBtns            = document.querySelectorAll('.tab-btn');
    this.tabPanes           = document.querySelectorAll('.tab-pane');
    // settings
    this.settingsToggle     = document.getElementById('settingsToggle');
    this.settingsBody       = document.getElementById('settingsBody');
    this.modelBaseUrl       = document.getElementById('modelBaseUrl');
    this.apiKeyInput        = document.getElementById('apiKeyInput');
    this.groqApiKeyInput    = document.getElementById('groqApiKeyInput');
    this.groqModelSelect    = document.getElementById('groqModelSelect');
    this.groqLanguageInput  = document.getElementById('groqLanguageInput');
    this.groqPromptInput    = document.getElementById('groqPromptInput');
    this.includeTimecodesInput = document.getElementById('includeTimecodesInput');
    this.fetchModelsBtn     = document.getElementById('fetchModelsBtn');
    this.fetchStatus        = document.getElementById('fetchStatus');
    this.modelSelect        = document.getElementById('modelSelect');
    this.reasoningEffortSelect = document.getElementById('reasoningEffortSelect');
    this.fetchIcon          = document.getElementById('fetchIcon');
  }

  /* ── Events ───────────────────────────────────────────── */
  _bindEvents() {
    this.form.addEventListener('submit', (e) => { e.preventDefault(); this._startTranscription(); });

    this.langToggle.addEventListener('click', (e) => {
      e.stopPropagation();
      this._toggleLangMenu();
    });
    this.langOptions.forEach(option => {
      option.addEventListener('click', (e) => {
        e.stopPropagation();
        this._switchLang(option.dataset.lang);
        this._saveSettings();
        this._closeLangMenu();
        this.langToggle.focus();
      });
    });
    document.addEventListener('click', (e) => {
      if (!this.langSwitcher.contains(e.target)) this._closeLangMenu();
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') this._closeLangMenu();
    });

    // Settings toggle
    this.settingsToggle.addEventListener('click', () => {
      const open = this.settingsBody.classList.toggle('open');
      this.settingsToggle.classList.toggle('open', open);
    });

    // Fetch models
    this.fetchModelsBtn.addEventListener('click', () => this._fetchModels());
    this.modelSelect.addEventListener('change', () => this._updateReasoningAvailability());

    // Auto-fetch when both fields filled (debounced)
    const debouncedFetch = this._debounce(() => {
      if (this.modelBaseUrl.value.trim() && this.apiKeyInput.value.trim()) this._fetchModels();
    }, 900);
    this.modelBaseUrl.addEventListener('input', debouncedFetch);
    this.apiKeyInput.addEventListener('input', debouncedFetch);

    // Persist settings
    [
      this.modelBaseUrl,
      this.apiKeyInput,
      this.modelSelect,
      this.reasoningEffortSelect,
      this.summaryLangSel,
      this.groqApiKeyInput,
      this.groqModelSelect,
      this.groqLanguageInput,
      this.groqPromptInput,
      this.includeTimecodesInput,
      this.summaryFormatSel,
      this.summaryPromptInput,
    ].forEach(el => {
      el.addEventListener('change', () => this._saveSettings());
    });

    // Tabs
    this.tabBtns.forEach(btn => {
      btn.addEventListener('click', () => this._switchTab(btn.dataset.tab));
    });

    // Downloads
    this.dlTranslation.addEventListener('click', () => this._downloadFile('translation'));
    this.dlSummary.addEventListener('click',     () => this._downloadFile('summary_md'));
    this.dlSummaryHtml.addEventListener('click', () => this._downloadFile('summary_html'));
    this.dlSummaryTxt.addEventListener('click',  () => this._downloadFile('summary_txt'));
    this.generateSummaryBtn.addEventListener('click', () => this._generateSummary());
    this.copyTranscriptTop.addEventListener('click', () => this._copyTranscriptText(this.copyTranscriptTop));
    this.copyTranscriptBottom.addEventListener('click', () => this._copyTranscriptText(this.copyTranscriptBottom));
    this.saveTranscriptTop.addEventListener('click', () => this._saveTranscript(this.saveTranscriptFormatTop.value));
    this.saveTranscriptBottom.addEventListener('click', () => this._saveTranscript(this.saveTranscriptFormatBottom.value));
    this.copySummaryTop.addEventListener('click', () => this._copySummaryText(this.copySummaryTop));
    this.copySummaryBottom.addEventListener('click', () => this._copySummaryText(this.copySummaryBottom));
    this.saveSummaryTop.addEventListener('click', () => this._saveSummary(this.saveSummaryFormatTop.value));
    this.saveSummaryBottom.addEventListener('click', () => this._saveSummary(this.saveSummaryFormatBottom.value));
    this.saveTranscriptFormatTop.addEventListener('change', () => {
      this.saveTranscriptFormatBottom.value = this.saveTranscriptFormatTop.value;
      this._saveSettings();
    });
    this.saveTranscriptFormatBottom.addEventListener('change', () => {
      this.saveTranscriptFormatTop.value = this.saveTranscriptFormatBottom.value;
      this._saveSettings();
    });
    this.saveSummaryFormatTop.addEventListener('change', () => {
      this.saveSummaryFormatBottom.value = this.saveSummaryFormatTop.value;
      this._saveSettings();
    });
    this.saveSummaryFormatBottom.addEventListener('change', () => {
      this.saveSummaryFormatTop.value = this.saveSummaryFormatBottom.value;
      this._saveSettings();
    });
  }

  /* ── i18n ─────────────────────────────────────────────── */
  t(key) {
    const active = this.i18n[this.currentLang] || this.i18n.en;
    return active[key] || this.i18n.en[key] || key;
  }

  _switchLang(lang) {
    if (!this.uiLanguages.includes(lang)) lang = 'en';
    this.currentLang = lang;
    this.langText.textContent = this.langLabels[lang] || this.langLabels.en;
    document.documentElement.lang = this.htmlLangs[lang] || 'en';
    document.title = this.t('title');

    document.querySelectorAll('[data-i18n]').forEach(el => {
      const v = this.t(el.dataset.i18n);
      if (typeof v === 'string') {
        el.textContent = v;
      }
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      const v = this.t(el.dataset.i18nPlaceholder);
      if (typeof v === 'string') el.placeholder = v;
    });
    this._syncLangMenu();
  }

  _toggleLangMenu() {
    if (this.langMenu.hidden) this._openLangMenu();
    else this._closeLangMenu();
  }

  _openLangMenu() {
    this._syncLangMenu();
    this.langMenu.hidden = false;
    this.langToggle.setAttribute('aria-expanded', 'true');
  }

  _closeLangMenu() {
    this.langMenu.hidden = true;
    this.langToggle.setAttribute('aria-expanded', 'false');
  }

  _syncLangMenu() {
    this.langOptions.forEach(option => {
      const active = option.dataset.lang === this.currentLang;
      option.classList.toggle('active', active);
      option.setAttribute('aria-selected', active ? 'true' : 'false');
    });
  }

  /* ── Settings persistence ─────────────────────────────── */
  _saveSettings() {
    const s = {
      uiLang:   this.currentLang,
      baseUrl:  this.modelBaseUrl.value,
      apiKey:   this.apiKeyInput.value,
      model:    this.modelSelect.value,
      reasoningEffort: this.reasoningEffortSelect.value,
      summaryLang: this.summaryLangSel.value,
      groqApiKey: this.groqApiKeyInput.value,
      groqModel: this.groqModelSelect.value,
      groqLanguage: this.groqLanguageInput.value,
      groqPrompt: this.groqPromptInput.value,
      includeTimecodes: this.includeTimecodesInput.checked,
      summaryFormat: this.summaryFormatSel.value,
      summaryPrompt: this.summaryPromptInput.value,
      transcriptSaveFormat: this.saveTranscriptFormatTop.value,
      summarySaveFormat: this.saveSummaryFormatTop.value,
    };
    try { localStorage.setItem('vt_settings', JSON.stringify(s)); } catch (_) {}
  }

  _loadSettings() {
    try {
      const raw = localStorage.getItem('vt_settings');
      if (!raw) return;
      const s = JSON.parse(raw);
      if (this.uiLanguages.includes(s.uiLang)) this._savedUiLang = s.uiLang;
      if (s.baseUrl)     this.modelBaseUrl.value = s.baseUrl;
      if (s.apiKey)      this.apiKeyInput.value  = s.apiKey;
      if (s.reasoningEffort) this.reasoningEffortSelect.value = s.reasoningEffort;
      if (s.summaryLang) this.summaryLangSel.value = s.summaryLang;
      if (s.groqApiKey)  this.groqApiKeyInput.value = s.groqApiKey;
      if (s.groqModel)   this.groqModelSelect.value = s.groqModel;
      if (s.groqLanguage) this.groqLanguageInput.value = s.groqLanguage;
      if (s.groqPrompt)  this.groqPromptInput.value = s.groqPrompt;
      this.includeTimecodesInput.checked = Boolean(s.includeTimecodes);
      if (s.summaryFormat) this.summaryFormatSel.value = s.summaryFormat;
      if (s.summaryPrompt) this.summaryPromptInput.value = s.summaryPrompt;
      if (['md', 'txt', 'pdf'].includes(s.transcriptSaveFormat)) {
        this.saveTranscriptFormatTop.value = s.transcriptSaveFormat;
        this.saveTranscriptFormatBottom.value = s.transcriptSaveFormat;
      }
      if (['md', 'txt', 'pdf'].includes(s.summarySaveFormat)) {
        this.saveSummaryFormatTop.value = s.summarySaveFormat;
        this.saveSummaryFormatBottom.value = s.summarySaveFormat;
      }
      // Model options will be restored after fetching
      this._savedModel = s.model || '';

      // Auto-open settings if credentials were saved
      if (s.baseUrl || s.apiKey || s.groqApiKey) {
        this.settingsBody.classList.add('open');
        this.settingsToggle.classList.add('open');
        // Attempt to re-fetch model list silently
        if (s.baseUrl && s.apiKey) {
          setTimeout(() => this._fetchModels(true), 400);
        }
      }
    } catch (_) {}
  }

  /* ── Fetch models ─────────────────────────────────────── */
  async _fetchModels(silent = false) {
    const baseUrl = this.modelBaseUrl.value.trim().replace(/\/$/, '');
    const apiKey  = this.apiKeyInput.value.trim();

    if (!baseUrl || !apiKey) {
      if (!silent) this._setFetchStatus('err', this.t('api_key') + ' & URL required');
      return;
    }

    this.fetchModelsBtn.disabled = true;
    this.fetchIcon.className = 'fas fa-spinner fa-spin';
    if (!silent) this._setFetchStatus('', this.t('fetching_models'));

    try {
      const fd = new FormData();
      fd.append('base_url', baseUrl);
      fd.append('api_key',  apiKey);

      const resp = await fetch(`${this.apiBase}/models`, { method: 'POST', body: fd });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }
      const data = await resp.json();
      const models = data.data || data.models || [];

      // Rebuild select options
      this.modelSelect.innerHTML = `<option value="">${this.t('model_default')}</option>`;
      models.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m.id;
        opt.textContent = m.name || m.id;
        this.modelSelect.appendChild(opt);
      });

      // Restore previously selected model
      if (this._savedModel) {
        this.modelSelect.value = this._savedModel;
        this._savedModel = '';
      }
      this._updateReasoningAvailability();

      this._setFetchStatus('ok', typeof this.t('models_loaded') === 'function'
        ? this.t('models_loaded')(models.length)
        : `${models.length} models`);

    } catch (e) {
      console.warn('Model fetch error:', e);
      this._setFetchStatus('err', this.t('models_error') + ': ' + e.message);
    } finally {
      this.fetchModelsBtn.disabled = false;
      this.fetchIcon.className = 'fas fa-sync-alt';
    }
  }

  _setFetchStatus(cls, msg) {
    this.fetchStatus.className = 'fetch-status' + (cls ? ` ${cls}` : '');
    this.fetchStatus.textContent = msg;
  }

  _modelSupportsReasoning(modelId) {
    const id = String(modelId || '').toLowerCase().split('/').pop();
    return id.startsWith('gpt-5') || id.startsWith('o1') || id.startsWith('o3') || id.startsWith('o4');
  }

  _updateReasoningAvailability() {
    if (!this.reasoningEffortSelect) return;
    const modelId = this.modelSelect.value;
    if (!modelId) {
      this.reasoningEffortSelect.disabled = true;
      return;
    }
    const supported = this._modelSupportsReasoning(modelId);
    this.reasoningEffortSelect.disabled = !supported;
    if (!supported) this.reasoningEffortSelect.value = '';
  }

  /* ── Transcription ────────────────────────────────────── */
  async _startTranscription() {
    if (this.submitBtn.disabled) return;

    const url     = this.videoUrlInput.value.trim();
    const sumLang = this.summaryLangSel.value;

    if (!url) { this._showError(this.t('error_invalid_url')); return; }

    this._setLoading(true);
    this._hideError();
    this._showProgress();

    try {
      const fd = new FormData();
      fd.append('url',              url);
      fd.append('summary_language', sumLang);

      const apiKey  = this.apiKeyInput.value.trim();
      const baseUrl = this.modelBaseUrl.value.trim().replace(/\/$/, '');
      const modelId = this.modelSelect.value;
      if (apiKey)  fd.append('api_key',       apiKey);
      if (baseUrl) fd.append('model_base_url', baseUrl);
      if (modelId) fd.append('model_id',       modelId);

      const groqKey = this.groqApiKeyInput.value.trim();
      const groqModel = this.groqModelSelect.value;
      const groqLanguage = this.groqLanguageInput.value.trim();
      const groqPrompt = this.groqPromptInput.value.trim();
      if (groqKey) fd.append('groq_api_key', groqKey);
      if (groqModel) fd.append('groq_model', groqModel);
      if (groqLanguage && !['auto', 'auto-detect', 'autodetect', 'detect'].includes(groqLanguage.toLowerCase())) fd.append('groq_language', groqLanguage);
      if (groqPrompt) fd.append('groq_prompt', groqPrompt);
      fd.append('include_timecodes', this.includeTimecodesInput.checked ? 'true' : 'false');

      const resp = await fetch(`${this.apiBase}/process-video`, { method: 'POST', body: fd });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || 'Request failed');
      }

      const data = await resp.json();
      this.currentTaskId = data.task_id;

      this._initSP();
      this._updateProgress(5, this.t('preparing'), true);
      this._startSSE();
      this._saveSettings();

    } catch (err) {
      this._showError(this.t('error_processing_failed') + err.message);
      this._setLoading(false);
      this._hideProgress();
    }
  }

  /* ── SSE ──────────────────────────────────────────────── */
  _startSSE() {
    if (!this.currentTaskId) return;
    this.eventSource = new EventSource(`${this.apiBase}/task-stream/${this.currentTaskId}`);

    this.eventSource.onmessage = (ev) => {
      try {
        const task = JSON.parse(ev.data);
        if (task.type === 'heartbeat') return;

        this._updateProgress(task.progress, task.message, true);

        if (task.summary_status === 'processing') {
          this.currentTask = task;
          if (this.summaryPrompt) {
            this.summaryPrompt.style.display = 'flex';
            this.summaryPrompt.querySelector('span').textContent = task.message || this.t('generating_summary');
          }
          return;
        }

        if (task.summary_status === 'completed') {
          this._stopSP(); this._stopSSE(); this._setLoading(false); this._hideProgress();
          this._finishSummaryLoading();
          this._showResults(task);
          this._switchTab('summary');
        } else if (task.summary_status === 'error') {
          this._stopSSE();
          this._finishSummaryLoading();
          this._showError(task.summary_error || task.message || 'Summary error');
        } else if (task.status === 'completed') {
          this._stopSP(); this._stopSSE(); this._setLoading(false); this._hideProgress();
          this._showResults(task);
        } else if (task.status === 'error') {
          this._stopSP(); this._stopSSE(); this._setLoading(false); this._hideProgress();
          this._showError(task.error || 'Processing error');
        }
      } catch (_) {}
    };

    this.eventSource.onerror = async () => {
      this._stopSSE();
      try {
        if (this.currentTaskId) {
          const r = await fetch(`${this.apiBase}/task-status/${this.currentTaskId}`);
          if (r.ok) {
            const task = await r.json();
            if (task?.summary_status === 'completed') {
              this._finishSummaryLoading();
              this._showResults(task);
              this._switchTab('summary');
              return;
            }
            if (task?.summary_status === 'error') {
              this._finishSummaryLoading();
              this._showError(task.summary_error || task.message || 'Summary error');
              return;
            }
            if (task?.summary_status === 'processing') {
              this._finishSummaryLoading();
              this._showError(this.t('error_processing_failed') + 'Summary stream disconnected');
              return;
            }
            if (task?.status === 'completed') {
              this._stopSP(); this._setLoading(false); this._hideProgress();
              this._showResults(task);
              return;
            }
          }
        }
      } catch (_) {}
      this._showError(this.t('error_processing_failed') + 'SSE disconnected');
      this._setLoading(false);
    };
  }

  _stopSSE() {
    if (this.eventSource) { this.eventSource.close(); this.eventSource = null; }
  }

  _finishSummaryLoading() {
    if (!this.generateSummaryBtn) return;
    this.generateSummaryBtn.disabled = false;
    this.generateSummaryBtn.innerHTML = this._summaryButtonOriginal || `<i class="fas fa-wand-magic-sparkles"></i> <span>${this.t('generate_summary')}</span>`;
    this._summaryButtonOriginal = null;
  }

  /* ── Progress ─────────────────────────────────────────── */
  _updateProgress(pct, msg, fromServer = false) {
    if (fromServer) {
      this._stopSP();
      this.sp.lastServer = pct;
      this.sp.current    = pct;
      this._renderProgress(pct, msg);
      this._updateStage(pct, msg);
      this._startSP();
    } else {
      this._renderProgress(pct, msg);
    }
  }

  _updateStage(pct, msg) {
    const m = (msg || '').toLowerCase();

    // ── 字幕路径（快速）──────────────────────────────────────
    if (m.includes('获取成功') || m.includes('subtitle found') || m.includes('字幕获取')) {
      this.sp.stage = 'subtitle_found';
      this.sp.target = 55;
      this._setModeBadge('subtitle');
    }
    // ── 无字幕 → 音频下载路径（慢）────────────────────────────
    else if (m.includes('未找到字幕') || m.includes('no subtitle') || m.includes('音频url') || m.includes('groq')) {
      this.sp.stage = 'transcribing';
      this.sp.target = 55;
      this._setModeBadge('groq');
    }
    // ── 通用字幕检测中 ─────────────────────────────────────────
    else if (m.includes('检测') && (m.includes('字幕') || m.includes('subtitle'))) {
      this.sp.stage = 'subtitle';
      this.sp.target = 40;
    }
    // ── 其他阶段 ───────────────────────────────────────────────
    else if (m.includes('解析') || m.includes('pars'))                     { this.sp.stage = 'parsing';       this.sp.target = 60; }
    else if (m.includes('下载') || m.includes('download'))                 { this.sp.stage = 'downloading';   this.sp.target = 60; }
    else if (m.includes('转录') || m.includes('transcrib') || m.includes('whisper') || m.includes('groq')) { this.sp.stage = 'transcribing';  this.sp.target = 80; }
    else if (m.includes('优化') || m.includes('optimiz'))                  { this.sp.stage = 'optimizing';    this.sp.target = 90; }
    else if (m.includes('摘要') || m.includes('summary'))                  { this.sp.stage = 'summarizing';   this.sp.target = 95; }
    else if (m.includes('完成') || m.includes('complet'))                  { this.sp.stage = 'completed';     this.sp.target = 100; }

    if (pct >= this.sp.target) this.sp.target = Math.min(pct + 8, 99);
  }

  _setModeBadge(mode) {
    if (!this.modeBadge) return;
    if (mode === 'subtitle') {
      this.modeBadge.textContent  = this.t('mode_subtitle');
      this.modeBadge.className    = 'mode-badge subtitle';
      this.modeBadge.style.display = 'inline-block';
      if (this.progressFill) this.progressFill.classList.add('subtitle-mode');
    } else if (mode === 'whisper' || mode === 'groq') {
      this.modeBadge.textContent  = this.t('mode_groq');
      this.modeBadge.className    = 'mode-badge groq';
      this.modeBadge.style.display = 'inline-block';
      if (this.progressFill) this.progressFill.classList.remove('subtitle-mode');
    }
  }

  _initSP() {
    this.sp.enabled = false; this.sp.current = 0; this.sp.target = 15;
    this.sp.lastServer = 0;  this.sp.startTime = Date.now(); this.sp.stage = 'preparing';
  }
  _startSP() {
    if (this.sp.interval) clearInterval(this.sp.interval);
    this.sp.enabled   = true;
    this.sp.startTime = this.sp.startTime || Date.now();
    this.sp.interval  = setInterval(() => this._tickSP(), 500);
  }
  _stopSP() {
    if (this.sp.interval) { clearInterval(this.sp.interval); this.sp.interval = null; }
    this.sp.enabled = false;
  }
  _tickSP() {
    if (!this.sp.enabled || this.sp.current >= this.sp.target) return;
    const speeds = { subtitle: .5, parsing: .3, downloading: .18, transcribing: .14, optimizing: .22, summarizing: .28 };
    let inc = speeds[this.sp.stage] || .2;
    const remaining = this.sp.target - this.sp.current;
    if (remaining < 5) inc *= .3;
    const next = Math.min(this.sp.current + inc, this.sp.target);
    if (next > this.sp.current) {
      this.sp.current = next;
      this._renderProgress(next, this._stageMsg());
    }
  }
  _stageMsg() {
    const map = {
      subtitle:       this.t('detecting_subtitles'),
      subtitle_found: this.t('subtitle_found'),
      downloading:    this.t('downloading_video'),
      parsing:        this.t('parsing_video'),
      transcribing:   this.t('transcribing_audio'),
      optimizing:     this.t('optimizing_transcript'),
      summarizing:    this.t('generating_summary'),
      completed:      this.t('completed'),
    };
    return map[this.sp.stage] || this.t('processing');
  }

  _renderProgress(pct, msg) {
    const p = Math.round(pct * 10) / 10;
    this.progressStatus.textContent = `${p}%`;
    this.progressFill.style.width   = `${p}%`;

    // Translate common server messages — more specific checks first
    const m = (msg || '').toLowerCase();
    let label = msg;
    // ── Subtitle path ──────────────────────────────────────────
    if      (m.includes('获取成功') || m.includes('subtitle found'))        label = this.t('subtitle_found');
    else if (m.includes('未找到字幕') || m.includes('no subtitle'))         label = this.t('no_subtitle');
    else if (m.includes('检测') && (m.includes('字幕') || m.includes('subtitle'))) label = this.t('detecting_subtitles');
    // ── Groq URL path ────────────────────────────────────────────
    else if (m.includes('音频url') || m.includes('groq'))  label = this.t('transcribing_audio');
    else if (m.includes('下载') || m.includes('download'))  label = this.t('downloading_video');
    else if (m.includes('解析') || m.includes('pars'))      label = this.t('parsing_video');
    else if (m.includes('转录') || m.includes('transcrib')) label = this.t('transcribing_audio');
    else if (m.includes('优化') || m.includes('optimiz'))   label = this.t('optimizing_transcript');
    else if (m.includes('摘要') || m.includes('summary'))   label = this.t('generating_summary');
    else if (m.includes('完成') || m.includes('complet'))   label = this.t('completed');
    else if (m.includes('准备') || m.includes('prepar'))    label = this.t('preparing');

    this.progressMessage.textContent = label;
  }

  _showProgress() {
    this.emptyState.style.display    = 'none';
    this.resultsPanel.classList.remove('show');
    this.progressPanel.classList.add('show');
    // Reset mode badge & progress bar color for new task
    if (this.modeBadge) { this.modeBadge.style.display = 'none'; this.modeBadge.className = 'mode-badge'; }
    if (this.progressFill) this.progressFill.classList.remove('subtitle-mode');
  }
  _hideProgress() { this.progressPanel.classList.remove('show'); }

  /* ── Results ──────────────────────────────────────────── */
  _showResults(task) {
    this.currentTask = task || {};
    const script = this.currentTask.transcript || this.currentTask.script;
    const summary = this.currentTask.summary;
    const translation = this.currentTask.translation;
    const detectedLang = this.currentTask.detected_language;
    const summaryLang = this.currentTask.summary_language;

    this.scriptContent.innerHTML  = script    ? marked.parse(script)      : '';
    this.summaryContent.innerHTML = summary   ? marked.parse(summary)     : '';

    if (this.summaryPrompt) {
      this.summaryPrompt.style.display = summary ? 'none' : 'flex';
    }
    if (this.summaryActionsTop) {
      this.summaryActionsTop.style.display = summary ? 'flex' : 'none';
    }
    if (this.summaryActionsBottom) {
      this.summaryActionsBottom.style.display = summary ? 'flex' : 'none';
    }
    if (this.dlSummary) {
      this.dlSummary.style.display = (this.currentTask.summary_markdown_path || this.currentTask.summary_path) ? 'inline-flex' : 'none';
    }
    if (this.dlSummaryHtml) {
      this.dlSummaryHtml.style.display = this.currentTask.summary_html_path ? 'inline-flex' : 'none';
    }
    if (this.dlSummaryTxt) {
      this.dlSummaryTxt.style.display = this.currentTask.summary_text_path ? 'inline-flex' : 'none';
    }

    const showTranslation = translation && detectedLang && summaryLang && detectedLang !== summaryLang;
    if (showTranslation) {
      this.translationContent.innerHTML = marked.parse(translation);
      this.translationTabBtn.style.display  = 'inline-block';
      this.dlTranslation.style.display      = 'inline-flex';
    } else {
      this.translationTabBtn.style.display  = 'none';
      this.dlTranslation.style.display      = 'none';
    }

    this.resultsPanel.classList.add('show');
    this._switchTab('script');
    this.resultsPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  async _generateSummary() {
    if (!this.currentTaskId) { this._showError(this.t('error_no_download')); return; }
    if (this.generateSummaryBtn.disabled) return;

    const original = this.generateSummaryBtn.innerHTML;
    this._summaryButtonOriginal = original;
    let waitingForSummary = false;
    this.generateSummaryBtn.disabled = true;
    this.generateSummaryBtn.innerHTML = `<span class="spinner"></span> ${this.t('generating_summary_btn')}`;
    this._hideError();

    try {
      const fd = new FormData();
      fd.append('task_id', this.currentTaskId);
      fd.append('summary_language', this.summaryLangSel.value);
      fd.append('output_format', this.summaryFormatSel.value);
      const summaryPrompt = this.summaryPromptInput.value.trim();
      if (summaryPrompt) fd.append('summary_prompt', summaryPrompt);

      const apiKey  = this.apiKeyInput.value.trim();
      const baseUrl = this.modelBaseUrl.value.trim().replace(/\/$/, '');
      const modelId = this.modelSelect.value;
      const reasoningEffort = this._modelSupportsReasoning(modelId) ? this.reasoningEffortSelect.value : '';
      if (apiKey)  fd.append('api_key', apiKey);
      if (baseUrl) fd.append('model_base_url', baseUrl);
      if (modelId) fd.append('model_id', modelId);
      if (reasoningEffort) fd.append('reasoning_effort', reasoningEffort);

      const resp = await fetch(`${this.apiBase}/summarize-transcript`, { method: 'POST', body: fd });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }

      const task = await resp.json();
      this.currentTask = task;
      this._showResults(task);
      this._switchTab('summary');
      this._saveSettings();

      if (task.summary_status === 'processing') {
        waitingForSummary = true;
        this._startSSE();
        return;
      }
    } catch (e) {
      this._showError(this.t('error_processing_failed') + e.message);
    } finally {
      if (!waitingForSummary) {
        this.generateSummaryBtn.disabled = false;
        this.generateSummaryBtn.innerHTML = original;
        this._summaryButtonOriginal = null;
      }
    }
  }

  _hideResults() { this.resultsPanel.classList.remove('show'); }

  /* ── Tabs ─────────────────────────────────────────────── */
  _switchTab(name) {
    this.tabBtns.forEach(b  => b.classList.toggle('active',  b.dataset.tab === name));
    this.tabPanes.forEach(p => p.classList.toggle('active', p.id === `${name}Tab`));
  }

  _transcriptMarkdown() {
    return String(this.currentTask?.transcript || this.currentTask?.script || '').trim();
  }

  _summaryMarkdown() {
    return String(this.currentTask?.summary || '').trim();
  }

  _markdownToPlainText(markdown) {
    return String(markdown || '')
      .trim()
      .replace(/^#{1,6}\s+/gm, '')
      .replace(/\*\*([^*]+)\*\*/g, '$1')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .replace(/^[ \t]*[-*_]{3,}[ \t]*$/gm, '')
      .replace(/[ \t]+\n/g, '\n')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }

  _transcriptPlainText() {
    return this._markdownToPlainText(this._transcriptMarkdown());
  }

  _summaryPlainText() {
    return this._markdownToPlainText(this._summaryMarkdown());
  }

  async _copyMarkdownText(markdown, button) {
    const text = this._markdownToPlainText(markdown);
    if (!text) { this._showError(this.t('error_no_download')); return; }

    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const area = document.createElement('textarea');
        area.value = text;
        area.setAttribute('readonly', '');
        area.style.position = 'fixed';
        area.style.left = '-9999px';
        document.body.appendChild(area);
        area.select();
        document.execCommand('copy');
        document.body.removeChild(area);
      }
      this._flashCopyButton(button);
    } catch (e) {
      this._showError(`Copy failed: ${e.message}`);
    }
  }

  async _copyTranscriptText(button) {
    return this._copyMarkdownText(this._transcriptMarkdown(), button);
  }

  async _copySummaryText(button) {
    return this._copyMarkdownText(this._summaryMarkdown(), button);
  }

  _flashCopyButton(button) {
    const label = button?.querySelector('span');
    if (!label) return;
    const previous = label.textContent;
    button.classList.add('copied');
    label.textContent = this.t('copied_text');
    setTimeout(() => {
      button.classList.remove('copied');
      label.textContent = previous || this.t('copy_text');
    }, 1200);
  }

  _saveMarkdownFile(markdown, format, prefix) {
    const normalized = format === 'txt' ? 'txt' : format === 'pdf' ? 'pdf' : 'md';
    const title = this.currentTask?.safe_title || 'video';
    const shortId = this.currentTask?.short_id || this.currentTaskId || prefix;
    const filenameBase = `${prefix}_${this._safeFilename(title)}_${this._safeFilename(shortId)}`;

    if (normalized === 'pdf') {
      this._savePdfFromMarkdown(markdown, `${filenameBase}.pdf`);
      return;
    }

    const content = normalized === 'txt' ? this._markdownToPlainText(markdown) : String(markdown || '').trim();
    if (!content) { this._showError(this.t('error_no_download')); return; }

    const filename = `${filenameBase}.${normalized}`;
    const type = normalized === 'txt' ? 'text/plain;charset=utf-8' : 'text/markdown;charset=utf-8';
    const blob = new Blob([`${content}\n`], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  async _savePdfFromMarkdown(markdown, filename) {
    const content = String(markdown || '').trim();
    if (!content) { this._showError(this.t('error_no_download')); return; }
    if (!window.html2canvas || !window.jspdf?.jsPDF) {
      this._showError('PDF export is unavailable in this browser session.');
      return;
    }

    const wrapper = document.createElement('div');
    wrapper.style.position = 'fixed';
    wrapper.style.left = '-20000px';
    wrapper.style.top = '0';
    wrapper.style.width = '820px';
    wrapper.style.padding = '36px 42px';
    wrapper.style.background = '#F4F2EB';
    wrapper.style.color = '#191F2F';
    wrapper.style.fontFamily = "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
    wrapper.style.lineHeight = '1.7';
    wrapper.style.boxSizing = 'border-box';
    wrapper.innerHTML = `
      <style>
        .pdf-markdown { font-size: 14px; color: #191F2F; }
        .pdf-markdown h1 { font-size: 28px; margin: 0 0 16px; }
        .pdf-markdown h2 { font-size: 21px; margin: 28px 0 12px; padding-top: 12px; border-top: 1px solid #B8C2DC; color: #6F7EA4; }
        .pdf-markdown h2:first-child { border-top: 0; padding-top: 0; }
        .pdf-markdown h3 { font-size: 17px; margin: 18px 0 8px; color: #6F7EA4; }
        .pdf-markdown p { margin: 0 0 12px; }
        .pdf-markdown strong { color: #6F7EA4; }
        .pdf-markdown blockquote { margin: 14px 0; padding-left: 12px; border-left: 3px solid #9EABCC; color: #707C9F; }
        .pdf-markdown ul, .pdf-markdown ol { margin: 0 0 14px 20px; }
        .pdf-markdown a { color: #6F7EA4; text-decoration: underline; }
        .pdf-markdown hr { border: 0; border-top: 1px solid #B8C2DC; margin: 16px 0; }
      </style>
      <div class="pdf-markdown">${marked.parse(content)}</div>
    `;
    document.body.appendChild(wrapper);

    try {
      const canvas = await window.html2canvas(wrapper, {
        backgroundColor: '#F4F2EB',
        scale: 2,
        useCORS: true,
      });
      const { jsPDF } = window.jspdf;
      const pdf = new jsPDF({ orientation: 'p', unit: 'mm', format: 'a4' });
      const pageWidth = pdf.internal.pageSize.getWidth();
      const pageHeight = pdf.internal.pageSize.getHeight();
      const margin = 10;
      const usableWidth = pageWidth - margin * 2;
      const usableHeight = pageHeight - margin * 2;
      const imageData = canvas.toDataURL('image/png');
      const imageHeight = (canvas.height * usableWidth) / canvas.width;
      let heightLeft = imageHeight;
      let position = margin;

      pdf.addImage(imageData, 'PNG', margin, position, usableWidth, imageHeight, undefined, 'FAST');
      heightLeft -= usableHeight;

      while (heightLeft > 0) {
        position = margin - (imageHeight - heightLeft);
        pdf.addPage();
        pdf.addImage(imageData, 'PNG', margin, position, usableWidth, imageHeight, undefined, 'FAST');
        heightLeft -= usableHeight;
      }

      pdf.save(filename);
    } catch (e) {
      this._showError(`PDF export failed: ${e.message}`);
    } finally {
      document.body.removeChild(wrapper);
    }
  }

  _saveTranscript(format) {
    return this._saveMarkdownFile(this._transcriptMarkdown(), format, 'transcript');
  }

  _saveSummary(format) {
    return this._saveMarkdownFile(this._summaryMarkdown(), format, 'summary');
  }

  _safeFilename(value) {
    return String(value || 'file').replace(/[<>:"/\\|?*\x00-\x1F]+/g, '_').replace(/\s+/g, '_').slice(0, 90);
  }

  /* ── Download ─────────────────────────────────────────── */
  async _downloadFile(type) {
    if (!this.currentTaskId) { this._showError(this.t('error_no_download')); return; }
    try {
      const r = await fetch(`${this.apiBase}/task-status/${this.currentTaskId}`);
      if (!r.ok) throw new Error('Failed to get task status');
      const task = await r.json();

      let filename;
      if      (type === 'script')       filename = this._filenameFromPath(task.script_path) || `transcript_${task.safe_title||'x'}_${task.short_id||'x'}.md`;
      else if (type === 'summary_md')   filename = this._filenameFromPath(task.summary_markdown_path || task.summary_path);
      else if (type === 'summary_html') filename = this._filenameFromPath(task.summary_html_path);
      else if (type === 'summary_txt')  filename = this._filenameFromPath(task.summary_text_path);
      else if (type === 'translation')  filename = this._filenameFromPath(task.translation_path) || `translation_${task.safe_title||'x'}_${task.short_id||'x'}.md`;
      else throw new Error('Unknown type');
      if (!filename) throw new Error(this.t('error_no_download'));

      const a = document.createElement('a');
      a.href = `${this.apiBase}/download/${encodeURIComponent(filename)}`;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch (e) {
      this._showError(this.t('error_download_failed') + e.message);
    }
  }

  _filenameFromPath(path) {
    if (!path) return '';
    return String(path).split(/[\\/]/).pop();
  }

  /* ── UI helpers ───────────────────────────────────────── */
  _setLoading(on) {
    this.submitBtn.disabled = on;
    this.submitBtn.innerHTML = on
      ? `<span class="spinner"></span> ${this.t('processing')}`
      : `<i class="fas fa-search"></i> <span>${this.t('start_transcription')}</span>`;
  }

  _showError(msg) {
    this.errorMsg.textContent = msg;
    this.errorBanner.classList.add('show');
    this.errorBanner.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    setTimeout(() => this._hideError(), 6000);
  }
  _hideError() { this.errorBanner.classList.remove('show'); }

  _debounce(fn, ms) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  }
}

/* ── Boot ──────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  window.vt = new VideoTranscriber();
});

window.addEventListener('beforeunload', () => {
  if (window.vt?.eventSource) window.vt._stopSSE();
});
