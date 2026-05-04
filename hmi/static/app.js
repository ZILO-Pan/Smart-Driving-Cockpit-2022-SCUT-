(function () {
    const CANVAS_W = 3840;
    const CANVAS_H = 590;

    function scaleCanvas() {
        const canvas = document.getElementById('canvas');
        if (!canvas) return;
        const scaleX = window.innerWidth / CANVAS_W;
        const scaleY = window.innerHeight / CANVAS_H;
        const scale = Math.min(scaleX, scaleY);
        canvas.style.transform = `translate(-50%, -50%) scale(${scale})`;
    }

    // Unity overlay toggle — click logo to open/close
    const logoBtn = document.getElementById('car-logo-btn');
    const overlay = document.getElementById('unity-overlay');
    let unityLoaded = false;

    logoBtn.addEventListener('click', () => {
        const isOpen = overlay.classList.toggle('active');
        logoBtn.classList.toggle('active', isOpen);
        if (isOpen && !unityLoaded) {
            loadUnity();
            unityLoaded = true;
        }
    });

    // Unity loading
    function loadUnity() {
        if (typeof createUnityInstance === 'undefined') {
            const loading = document.getElementById('unity-loading');
            const textEl = loading.querySelector('.unity-loading-text');
            textEl.textContent = 'Unity Build not found. Place files in /static/unity/ai-car-scene/Build/';
            return;
        }

        const buildUrl = '/static/unity/ai-car-scene/Build';
        const config = {
            dataUrl: buildUrl + '/AI4HMI.data.gz',
            frameworkUrl: buildUrl + '/AI4HMI.framework.js.gz',
            codeUrl: buildUrl + '/AI4HMI.wasm.gz',
            streamingAssetsUrl: '/static/unity/ai-car-scene/StreamingAssets',
            companyName: 'DefaultCompany',
            productName: 'AI4HMI',
            productVersion: '1.0',
        };

        const unityCanvas = document.getElementById('unity-canvas');
        const loading = document.getElementById('unity-loading');
        const progressBar = document.getElementById('unity-progress-bar');

        createUnityInstance(unityCanvas, config, (progress) => {
            progressBar.style.width = (progress * 100) + '%';
        }).then((instance) => {
            window.unityInstance = instance;
            loading.classList.add('hidden');
            setTimeout(() => loading.remove(), 600);
            setupHMIBridge(instance);
        }).catch((err) => {
            console.error('Unity load failed:', err);
            const textEl = loading.querySelector('.unity-loading-text');
            textEl.textContent = 'Failed to load 3D scene';
        });
    }

    function setupHMIBridge(instance) {
        window.HMI = {
            sendCommand(action, target, params) {
                if (!instance) return;
                const cmd = {
                    action: action,
                    target: target || '',
                    paramsJson: params ? JSON.stringify(params) : ''
                };
                instance.SendMessage('HMIController', 'ExecuteCommand', JSON.stringify(cmd));
            },
            switchCamera(view) { this.sendCommand('switchCamera', view); },
            togglePart(partId) { this.sendCommand('togglePart', partId); },
            openPart(partId) { this.sendCommand('openPart', partId); },
            closePart(partId) { this.sendCommand('closePart', partId); },
            rotateCarTo(angle) { this.sendCommand('rotateCar', 'absolute', { angle }); },
            rotateCarBy(angle) { this.sendCommand('rotateCar', 'relative', { angle }); },
            resetCarRotation() { this.sendCommand('rotateCar', 'reset'); },
            getState() { this.sendCommand('getState', 'all'); },
        };

        window.HMIBus = {
            listeners: [],
            on(fn) { this.listeners.push(fn); },
            emit(evt) { this.listeners.forEach(fn => fn(evt)); }
        };
    }

    // Audio
    const audioHello = new Audio('/static/videos/Hello.mp3');
    const audioBye = new Audio('/static/videos/Bye.mp3');
    let currentView = 'default';

    window.OnUnityEvent = function (jsonStr) {
        try {
            const evt = JSON.parse(jsonStr);
            console.log('[Unity Event]', evt);
            if (window.HMIBus) window.HMIBus.emit(evt);

            if (evt.eventType === 'cameraTransitionStart') {
                if (currentView === 'astronaut' && evt.target !== 'astronaut') {
                    audioBye.currentTime = 0;
                    audioBye.play();
                }
            }

            if (evt.eventType === 'cameraTransitionEnd') {
                currentView = evt.target;
                if (evt.target === 'astronaut') {
                    audioHello.currentTime = 0;
                    audioHello.play();
                }
            }
        } catch (e) {
            console.error('Failed to parse Unity event:', e);
        }
    };

    function init() {
        scaleCanvas();
        window.addEventListener('resize', scaleCanvas);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
