const DOM = {
    form: document.getElementById('clone-form'),
    urlInput: document.getElementById('url-input'),
    optionsToggle: document.getElementById('options-toggle'),
    optionsPanel: document.getElementById('options-panel'),
    submitBtn: document.getElementById('submit-btn'),
    progressSection: document.getElementById('progress-section'),
    progressFill: document.getElementById('progress-fill'),
    progressPercent: document.getElementById('progress-percent'),
    stepText: document.getElementById('step-text'),
    logsContainer: document.getElementById('logs'),
    resultSection: document.getElementById('result-section'),
    errorMessage: document.getElementById('error-message'),
    errorText: document.getElementById('error-text'),
    resultUrl: document.getElementById('result-url'),
    resultDir: document.getElementById('result-dir'),
    resultTime: document.getElementById('result-time'),
    resultAssets: document.getElementById('result-assets'),
    resultRewrites: document.getElementById('result-rewrites'),
    resultSize: document.getElementById('result-size'),
    groqSummary: document.getElementById('groq-summary'),
    groqContent: document.getElementById('groq-content'),
    resetBtn: document.getElementById('reset-btn'),
    openDirBtn: document.getElementById('open-dir-btn'),
    openPageBtn: document.getElementById('open-page-btn'),
    notification: document.getElementById('notification'),
};

let cloneName = null;
let ws = null;
let isCloning = false;
const IS_RENDER = !['localhost', '127.0.0.1'].includes(window.location.hostname);

function getOptions() {
    return {
        max_pages: parseInt(document.getElementById('opt-max-pages').value, 10) || 1,
        enable_interactions: document.getElementById('opt-interactions').checked,
        save_api: document.getElementById('opt-save-api').checked,
        summarize: document.getElementById('opt-summarize').checked,
        stealth: document.getElementById('opt-stealth').checked,
        wait_strategy: document.getElementById('opt-wait-strategy').value,
        scroll_steps: parseInt(document.getElementById('opt-scroll-steps').value, 10) || 5,
        page_timeout: (parseInt(document.getElementById('opt-page-timeout').value, 10) || 60) * 1000,
        clone_mode: document.getElementById('opt-clone-mode').value,
    };
}

function addLog(message, type = 'info') {
    const entry = document.createElement('div');
    entry.className = `log-entry log-${type}`;
    entry.textContent = message;
    DOM.logsContainer.appendChild(entry);
    DOM.logsContainer.scrollTop = DOM.logsContainer.scrollHeight;
}

function setProgress(percent, step) {
    DOM.progressFill.style.width = `${Math.min(percent, 100)}%`;
    DOM.progressPercent.textContent = `${Math.round(percent)}%`;
    if (step) DOM.stepText.textContent = step;
}

function showError(message) {
    DOM.errorText.textContent = message;
    DOM.errorMessage.classList.add('active');
}

function hideError() {
    DOM.errorMessage.classList.remove('active');
}

function showNotification(message, type = 'success') {
    DOM.notification.textContent = message;
    DOM.notification.className = `notification visible ${type}`;
    setTimeout(() => DOM.notification.classList.remove('visible'), 2500);
}

function validateUrl(url) {
    if (!url.trim()) {
        DOM.urlInput.classList.add('error');
        return false;
    }
    try {
        new URL(url.startsWith('http') ? url : `https://${url}`);
        DOM.urlInput.classList.remove('error');
        return true;
    } catch {
        DOM.urlInput.classList.add('error');
        return false;
    }
}

function formatSize(bytes) {
    if (bytes < 1024) return `${bytes} o`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

function startCloning(url) {
    if (isCloning) return;
    isCloning = true;
    cloneName = null;
    hideError();

    const options = getOptions();

    DOM.submitBtn.disabled = true;
    DOM.submitBtn.classList.add('loading');

    DOM.progressSection.classList.add('active');
    DOM.resultSection.classList.remove('active');
    DOM.logsContainer.innerHTML = '';

    setProgress(0, 'Connexion au serveur...');
    addLog('Connexion au serveur...', 'info');

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        addLog('Connecté au serveur', 'success');
        ws.send(JSON.stringify({ url, options }));
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        switch (data.type) {
            case 'progress':
                setProgress(data.percent, data.step);
                break;

            case 'log':
                addLog(data.message, data.level || 'info');
                break;

            case 'complete':
                isCloning = false;
                cloneName = data.clone_name;
                DOM.submitBtn.disabled = false;
                DOM.submitBtn.classList.remove('loading');
                setProgress(100, 'Terminé !');
                showResult(data);
                break;

            case 'error':
                isCloning = false;
                DOM.submitBtn.disabled = false;
                DOM.submitBtn.classList.remove('loading');
                showError(data.message);
                addLog(`Erreur : ${data.message}`, 'error');
                break;
        }
    };

    ws.onerror = () => {
        isCloning = false;
        DOM.submitBtn.disabled = false;
        DOM.submitBtn.classList.remove('loading');
        showError('Erreur de connexion au serveur');
        addLog('Erreur de connexion', 'error');
    };

    ws.onclose = () => {
        if (isCloning) {
            isCloning = false;
            DOM.submitBtn.disabled = false;
            DOM.submitBtn.classList.remove('loading');
            showError('Connexion interrompue');
            addLog('Connexion interrompue', 'error');
        }
    };
}

function showResult(data) {
    const s = data.summary;
    DOM.resultUrl.textContent = data.url;
    DOM.resultDir.textContent = data.output_dir;
    DOM.resultTime.textContent = `${s.duration.toFixed(1)}s`;
    DOM.resultAssets.textContent = `${s.resources_saved}`;
    DOM.resultRewrites.textContent = `${s.pages_cloned}`;
    DOM.resultSize.textContent = formatSize(s.total_size);

    document.getElementById('result-framework').textContent = s.framework || 'Aucun';
    document.getElementById('result-api-calls').textContent = `${s.api_calls_saved}`;

    DOM.resultSection.classList.add('active');

    if (s.groq_summary) {
        DOM.groqContent.textContent = s.groq_summary;
        DOM.groqSummary.classList.add('active');
    }

    DOM.openDirBtn.textContent = IS_RENDER
        ? '📥 Télécharger le ZIP'
        : '📂 Ouvrir le dossier';

    DOM.resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

DOM.form.addEventListener('submit', (e) => {
    e.preventDefault();
    const url = DOM.urlInput.value.trim();
    if (validateUrl(url)) {
        startCloning(url);
    }
});

DOM.urlInput.addEventListener('input', () => {
    DOM.urlInput.classList.remove('error');
});

DOM.optionsToggle.addEventListener('click', () => {
    const isOpen = DOM.optionsPanel.classList.toggle('open');
    DOM.optionsToggle.classList.toggle('open');
});

document.querySelectorAll('.option-checkbox').forEach((el) => {
    el.addEventListener('click', () => {
        const checkbox = el.querySelector('input');
        checkbox.checked = !checkbox.checked;
        el.classList.toggle('active');
    });
});

document.querySelector('.toggle-switch').addEventListener('click', function () {
    this.classList.toggle('active');
    document.getElementById('opt-summarize').checked = this.classList.contains('active');
});

DOM.resetBtn.addEventListener('click', () => {
    DOM.urlInput.value = '';
    DOM.progressSection.classList.remove('active');
    DOM.resultSection.classList.remove('active');
    DOM.groqSummary.classList.remove('active');
    DOM.logsContainer.innerHTML = '';
    setProgress(0, '');
    cloneName = null;
    DOM.urlInput.focus();
    window.scrollTo({ top: 0, behavior: 'smooth' });
});

DOM.openPageBtn.addEventListener('click', () => {
    if (cloneName) {
        window.open(`/preview/${cloneName}`, '_blank');
    } else {
        showNotification('Aucun clone à afficher', 'error');
    }
});

DOM.openDirBtn.addEventListener('click', () => {
    if (!cloneName) {
        showNotification('Aucun clone à télécharger', 'error');
        return;
    }
    if (IS_RENDER) {
        window.location.href = `/download/${cloneName}`;
        showNotification('Téléchargement du ZIP...', 'info');
    } else {
        const dir = DOM.resultDir.textContent;
        if (dir) {
            navigator.clipboard.writeText(dir).then(() => {
                showNotification('Chemin copié dans le presse-papier !');
            }).catch(() => {
                showNotification(`Dossier : ${dir}`, 'info');
            });
        }
    }
});

DOM.urlInput.focus();
